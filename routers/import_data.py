"""
Qomiq API — Router import CSV/XLSX.

Endpoints :
  POST /import/upload                  → parse + détection de type
  POST /import/validate                → remap + validation
  POST /import/save                    → persistance dans UserData
  GET  /import/templates/{data_type}   → template CSV téléchargeable
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.user_data import save_user_data
from routers.auth import get_current_user
from services.import_csv.data_validator import ValidationResult, remap_rows, validate_rows
from services.import_csv.import_service import parse_file

router = APIRouter(prefix="/import", tags=["import"])

_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# ── CSV templates ─────────────────────────────────────────────────────────────

_TEMPLATES: dict[str, str] = {
    "pipeline": (
        "nom,client,montant,date_cloture,statut,date_modification\n"
        "Deal exemple,Acme Corp,15000,2026-12-31,En cours,2026-04-01\n"
    ),
    "ca_mensuel": (
        "mois,ca_realise,objectif\n"
        "2026-04,42000,45000\n"
        "2026-03,38000,40000\n"
    ),
    "contacts": (
        "nom,email,telephone,societe,poste\n"
        "Jean Dupont,jean@exemple.fr,0601020304,Acme Corp,Directeur\n"
    ),
    "budget": (
        "nom,budget,reel\n"
        "Marketing,10000,9500\n"
        "Commercial,25000,26000\n"
    ),
    "produits": (
        "nom,marque,ca,ventes,stock\n"
        "Produit A,MaMarque,12000,150,45\n"
    ),
}


# ── Schémas Pydantic ──────────────────────────────────────────────────────────

class ValidateBody(BaseModel):
    mapping:   dict[str, str]
    data_type: str
    rows:      list[dict[str, Any]]


class SaveBody(BaseModel):
    data_type:      str
    rows:           list[dict[str, Any]]
    merge_strategy: str = "replace"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload", summary="Uploader un fichier CSV ou XLSX")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Parse un fichier CSV ou XLSX et retourne les métadonnées détectées.

    La réponse inclut les lignes brutes pour que le client puisse
    les renvoyer dans /import/validate.
    """
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension non supportée : '{suffix}'. Acceptés : {', '.join(_ALLOWED_EXTENSIONS)}.",
        )

    # Écriture dans un fichier temporaire
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = parse_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result.error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error,
        )

    return {
        "headers":              result.headers,
        "detected_type":        result.detected_type,
        "detection_confidence": result.detection_confidence,
        "suggested_mapping":    result.suggested_mapping,
        "preview_values":       result.preview_values,
        "row_count":            result.row_count,
        "rows":                 result.rows,
    }


@router.post("/validate", summary="Valider les lignes après remappage")
def validate_import(
    body: ValidateBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remappe les colonnes et valide les lignes pour le data_type donné."""
    remapped = remap_rows(body.rows, body.mapping)
    vr: ValidationResult = validate_rows(remapped, body.data_type)
    return {
        "valid_rows":   vr.valid_rows,
        "invalid_rows": vr.invalid_rows,
        "warnings":     vr.warnings,
        "stats":        vr.stats,
    }


@router.post("/save", summary="Sauvegarder les lignes importées")
def save_import(
    body: SaveBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Persiste les lignes dans UserData pour l'utilisateur courant."""
    allowed_strategies = {"upsert", "replace", "append"}
    if body.merge_strategy not in allowed_strategies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"merge_strategy doit être l'un de : {', '.join(allowed_strategies)}.",
        )

    if body.merge_strategy == "append":
        from models.user_data import get_user_data
        existing = get_user_data(db, current_user.id, body.data_type)
        rows = existing + body.rows
    else:
        rows = body.rows

    save_user_data(db, current_user.id, body.data_type, rows, body.merge_strategy)
    return {"imported_count": len(body.rows), "data_type": body.data_type}


@router.get("/templates/{data_type}", summary="Télécharger un template CSV")
def download_template(
    data_type: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Retourne un fichier CSV exemple pour le data_type demandé."""
    template = _TEMPLATES.get(data_type)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pas de template pour '{data_type}'. Disponibles : {', '.join(_TEMPLATES)}.",
        )
    return StreamingResponse(
        iter([template.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={data_type}_template.csv"},
    )
