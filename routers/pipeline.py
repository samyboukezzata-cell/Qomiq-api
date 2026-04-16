"""
Qomiq API — Router Pipeline CRM.

Endpoints :
  GET    /pipeline/             → liste des deals (filtrable)
  GET    /pipeline/stats        → statistiques agrégées
  POST   /pipeline/             → créer un deal
  PUT    /pipeline/{deal_id}    → modifier un deal
  PATCH  /pipeline/{deal_id}/etape → changer l'étape (drag & drop)
  DELETE /pipeline/{deal_id}    → supprimer un deal
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.user_data import get_user_data, save_user_data
from routers.auth import get_current_user

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# ── Constantes ────────────────────────────────────────────────────────────────

ETAPES_VALIDES = [
    "Prospect", "Qualification", "Proposition",
    "Négociation", "Gagné", "Perdu",
]

_PROBA_AUTO: dict[str, int] = {
    "Prospect":      10,
    "Qualification": 25,
    "Proposition":   50,
    "Négociation":   75,
    "Gagné":        100,
    "Perdu":          0,
}

_DATA_TYPE = "pipeline"


# ── Schemas ───────────────────────────────────────────────────────────────────

class DealCreate(BaseModel):
    nom:          str
    client:       str
    montant:      float
    etape:        str
    probabilite:  Optional[int]   = None
    date_cloture: Optional[str]   = None
    commercial:   Optional[str]   = None
    notes:        Optional[str]   = None

    @field_validator("etape")
    @classmethod
    def etape_valide(cls, v: str) -> str:
        if v not in ETAPES_VALIDES:
            raise ValueError(f"Étape invalide. Valeurs acceptées : {ETAPES_VALIDES}")
        return v

    @field_validator("montant")
    @classmethod
    def montant_positif(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Le montant ne peut pas être négatif.")
        return v


class DealUpdate(BaseModel):
    nom:          Optional[str]   = None
    client:       Optional[str]   = None
    montant:      Optional[float] = None
    etape:        Optional[str]   = None
    probabilite:  Optional[int]   = None
    date_cloture: Optional[str]   = None
    commercial:   Optional[str]   = None
    notes:        Optional[str]   = None

    @field_validator("etape")
    @classmethod
    def etape_valide(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ETAPES_VALIDES:
            raise ValueError(f"Étape invalide. Valeurs acceptées : {ETAPES_VALIDES}")
        return v

    @field_validator("montant")
    @classmethod
    def montant_positif(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Le montant ne peut pas être négatif.")
        return v


class EtapePatch(BaseModel):
    etape:       str
    probabilite: Optional[int] = None

    @field_validator("etape")
    @classmethod
    def etape_valide(cls, v: str) -> str:
        if v not in ETAPES_VALIDES:
            raise ValueError(f"Étape invalide. Valeurs acceptées : {ETAPES_VALIDES}")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(db: Session, user_id: int) -> list[dict]:
    return get_user_data(db, user_id, _DATA_TYPE)


def _save(db: Session, user_id: int, deals: list[dict]) -> None:
    save_user_data(db, user_id, _DATA_TYPE, deals)


def _find(deals: list[dict], deal_id: str) -> dict | None:
    return next((d for d in deals if d.get("id") == deal_id), None)


def _sort_by_date(deals: list[dict]) -> list[dict]:
    """Trie par date_cloture asc (None en dernier)."""
    def key(d: dict):
        v = d.get("date_cloture")
        return v or "9999-99-99"
    return sorted(deals, key=key)


# ── GET /pipeline/ ────────────────────────────────────────────────────────────

@router.get("/", summary="Liste des deals")
def list_deals(
    etape:      Optional[str] = Query(None),
    commercial: Optional[str] = Query(None),
    search:     Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    deals = _load(db, current_user.id)

    if etape:
        deals = [d for d in deals if d.get("etape") == etape]
    if commercial:
        deals = [d for d in deals if d.get("commercial") == commercial]
    if search:
        s = search.lower()
        deals = [
            d for d in deals
            if s in (d.get("nom") or "").lower()
            or s in (d.get("client") or "").lower()
        ]

    return _sort_by_date(deals)


# ── GET /pipeline/stats ───────────────────────────────────────────────────────

@router.get("/stats", summary="Statistiques pipeline")
def pipeline_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deals = _load(db, current_user.id)

    count_won  = sum(1 for d in deals if d.get("etape") == "Gagné")
    count_lost = sum(1 for d in deals if d.get("etape") == "Perdu")
    active     = [d for d in deals if d.get("etape") not in ("Gagné", "Perdu")]
    total_value = sum(float(d.get("montant") or 0) for d in active)
    won_values  = [float(d.get("montant") or 0) for d in deals if d.get("etape") == "Gagné"]
    avg_deal_size = (sum(won_values) / len(won_values)) if won_values else 0.0
    decided = count_won + count_lost
    win_rate = round((count_won / decided * 100), 1) if decided else 0.0

    by_etape: dict[str, dict] = {}
    by_commercial: dict[str, dict] = {}
    for d in deals:
        e = d.get("etape", "Inconnu")
        m = float(d.get("montant") or 0)
        by_etape.setdefault(e, {"count": 0, "value": 0.0})
        by_etape[e]["count"] += 1
        by_etape[e]["value"] += m

        c = d.get("commercial") or "Non assigné"
        by_commercial.setdefault(c, {"count": 0, "value": 0.0})
        by_commercial[c]["count"] += 1
        by_commercial[c]["value"] += m

    return {
        "total_value":    total_value,
        "count_active":   len(active),
        "count_won":      count_won,
        "count_lost":     count_lost,
        "win_rate":       win_rate,
        "avg_deal_size":  avg_deal_size,
        "by_etape":       by_etape,
        "by_commercial":  by_commercial,
    }


# ── POST /pipeline/ ───────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED, summary="Créer un deal")
def create_deal(
    body: DealCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deals = _load(db, current_user.id)
    proba = body.probabilite if body.probabilite is not None else _PROBA_AUTO.get(body.etape, 50)
    now = _now_iso()
    deal: dict = {
        "id":               str(uuid.uuid4()),
        "nom":              body.nom,
        "client":           body.client,
        "montant":          body.montant,
        "etape":            body.etape,
        "probabilite":      proba,
        "date_cloture":     body.date_cloture,
        "commercial":       body.commercial,
        "notes":            body.notes,
        "date_creation":    now,
        "date_modification": now,
    }
    deals.append(deal)
    _save(db, current_user.id, deals)
    return deal


# ── PUT /pipeline/{deal_id} ───────────────────────────────────────────────────

@router.put("/{deal_id}", summary="Modifier un deal")
def update_deal(
    deal_id: str,
    body: DealUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deals = _load(db, current_user.id)
    deal  = _find(deals, deal_id)
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Deal introuvable.")

    for field, value in body.model_dump(exclude_none=True).items():
        deal[field] = value
    deal["date_modification"] = _now_iso()

    _save(db, current_user.id, deals)
    return deal


# ── PATCH /pipeline/{deal_id}/etape ──────────────────────────────────────────

@router.patch("/{deal_id}/etape", summary="Changer l'étape d'un deal (Kanban)")
def patch_etape(
    deal_id: str,
    body: EtapePatch,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deals = _load(db, current_user.id)
    deal  = _find(deals, deal_id)
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Deal introuvable.")

    deal["etape"] = body.etape
    # Probabilité automatique selon étape sauf si fournie
    if body.probabilite is not None:
        deal["probabilite"] = body.probabilite
    elif body.etape in ("Gagné", "Perdu"):
        deal["probabilite"] = _PROBA_AUTO[body.etape]

    deal["date_modification"] = _now_iso()
    _save(db, current_user.id, deals)
    return deal


# ── DELETE /pipeline/{deal_id} ────────────────────────────────────────────────

@router.delete("/{deal_id}", summary="Supprimer un deal")
def delete_deal(
    deal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deals = _load(db, current_user.id)
    deal  = _find(deals, deal_id)
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Deal introuvable.")

    deals.remove(deal)
    _save(db, current_user.id, deals)
    return {"success": True}
