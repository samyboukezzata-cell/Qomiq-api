"""
Qomiq API — Service d'import CSV/XLSX.

Orchestre parsing, détection de type et scoring de confiance.
Aucune dépendance Flet, aucune écriture de fichier métier.
"""
from __future__ import annotations

import csv
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .column_mapper import map_columns
from .csv_detector import CSV_TYPE_PRODUITS, CSV_TYPE_BUDGET, CSV_TYPE_CA_MENSUEL, detect_csv_type

logger = logging.getLogger(__name__)

_KEY_FIELDS: dict[str, list[str]] = {
    CSV_TYPE_PRODUITS:   ["nom", "ca", "ventes", "stock"],
    CSV_TYPE_BUDGET:     ["ligne", "budget", "reel", "ecart"],
    CSV_TYPE_CA_MENSUEL: ["mois", "ca_realise", "annee", "ca_objectif", "nb_commandes", "nb_nouveaux_clients"],
}


@dataclass
class ParseResult:
    """Résultat complet d'un appel à parse_file()."""
    filepath:             str
    rows:                 list[dict]
    headers:              list[str]
    detected_type:        str
    detection_confidence: float
    suggested_mapping:    dict[str, str | None]
    preview_values:       dict[str, str] = field(default_factory=dict)
    row_count:            int = 0
    error:                str | None = None


# ── Readers ───────────────────────────────────────────────────────────────────

def _read_xlsx(file_path: str) -> tuple[list[dict], str | None]:
    try:
        import openpyxl
    except ImportError:
        return [], "openpyxl n'est pas installé."
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        raw_rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as exc:
        return [], f"Impossible de lire le fichier Excel : {exc}"

    if not raw_rows:
        return [], None

    header_row_idx = 0
    for i, row in enumerate(raw_rows):
        if len([v for v in row if v is not None and str(v).strip()]) >= 2:
            header_row_idx = i
            break

    headers = [
        str(h).strip() if h is not None and str(h).strip() else f"col_{i}"
        for i, h in enumerate(raw_rows[header_row_idx])
    ]
    result: list[dict] = []
    for row in raw_rows[header_row_idx + 1:]:
        if not any(v is not None for v in row):
            continue
        result.append({
            headers[i]: (str(v).strip() if v is not None else "")
            for i, v in enumerate(row)
        })
    return result, None


def _read_csv(file_path: str) -> tuple[list[dict], str | None]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(file_path, encoding=encoding, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                rows = [dict(r) for r in csv.DictReader(f, dialect=dialect)]
            return rows, None
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            return [], str(exc)
    return [], "Impossible de décoder le fichier (encodage non supporté)."


def _read_file(file_path: str) -> tuple[list[dict], str | None]:
    ext = Path(file_path).suffix.lower()
    if ext in (".xlsx", ".xls"):
        return _read_xlsx(file_path)
    return _read_csv(file_path)


# ── Public API ────────────────────────────────────────────────────────────────

def confidence_score(csv_type: str, mapped: dict[str, str | None]) -> float:
    key_fields = _KEY_FIELDS.get(csv_type)
    if not key_fields:
        return 0.0
    matched = sum(1 for f in key_fields if mapped.get(f) is not None)
    return round(matched / len(key_fields), 2)


def _preview(rows: list[dict], headers: list[str]) -> dict[str, str]:
    preview: dict[str, str] = {}
    for row in rows:
        for h in headers:
            if h not in preview:
                val = str(row.get(h, "")).strip()
                if val:
                    preview[h] = val[:40]
        if len(preview) == len(headers):
            break
    return preview


def parse_file(filepath: str) -> ParseResult:
    """
    Lit un fichier CSV ou XLSX et retourne un ParseResult complet.

    La copie temporaire contourne les restrictions d'accès macOS.
    """
    src = Path(filepath)
    tmp_dir: str | None = None
    work_path = filepath
    try:
        tmp_dir  = tempfile.mkdtemp()
        tmp_file = Path(tmp_dir) / src.name
        shutil.copy2(str(src), str(tmp_file))
        work_path = str(tmp_file)
    except Exception:
        logger.warning("Copie temporaire impossible, lecture depuis %s", filepath)

    try:
        rows, err = _read_file(work_path)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if err:
        return ParseResult(
            filepath=filepath, rows=[], headers=[], detected_type="unknown",
            detection_confidence=0.0, suggested_mapping={}, error=err,
        )
    if not rows:
        return ParseResult(
            filepath=filepath, rows=[], headers=[], detected_type="unknown",
            detection_confidence=0.0, suggested_mapping={}, error="Fichier vide.",
        )

    headers           = list(rows[0].keys())
    suggested_mapping = map_columns(headers)
    detected_type     = detect_csv_type(headers)
    detection_conf    = confidence_score(detected_type, suggested_mapping)

    return ParseResult(
        filepath=filepath,
        rows=rows,
        headers=headers,
        detected_type=detected_type,
        detection_confidence=detection_conf,
        suggested_mapping=suggested_mapping,
        preview_values=_preview(rows, headers),
        row_count=len(rows),
        error=None,
    )
