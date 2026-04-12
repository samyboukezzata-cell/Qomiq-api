"""
Qomiq — Détection automatique du type de fichier CSV/XLSX.

Analyse les en-têtes d'un fichier pour déterminer à quelle entité
Qomiq les données correspondent.
"""
from __future__ import annotations

from .column_mapper import map_columns

# ── Types reconnus ─────────────────────────────────────────────────────────────

CSV_TYPE_PRODUITS   = "produits"
CSV_TYPE_BUDGET     = "budget"
CSV_TYPE_CA_MENSUEL = "ca_mensuel"
CSV_TYPE_UNKNOWN    = "unknown"

# Champs requis pour chaque type (au moins N colonnes présentes)
# Les règles ca_mensuel sont en premier pour avoir la priorité.
_RULES: list[tuple[str, list[str], int]] = [
    # (type, champs_requis, nb_minimum)
    (CSV_TYPE_CA_MENSUEL, ["ca_realise", "mois"],    2),
    (CSV_TYPE_CA_MENSUEL, ["ca_realise", "annee"],   2),
    (CSV_TYPE_CA_MENSUEL, ["ca_realise", "periode"], 2),
    (CSV_TYPE_PRODUITS,   ["nom", "ca"],              2),
    (CSV_TYPE_PRODUITS,   ["nom", "ventes"],          2),
    (CSV_TYPE_PRODUITS,   ["nom", "stock"],           2),
    (CSV_TYPE_BUDGET,     ["ligne", "budget"],        2),
    (CSV_TYPE_BUDGET,     ["ligne", "reel"],          2),
    (CSV_TYPE_BUDGET,     ["budget", "reel"],         2),
]


def detect_csv_type(headers: list[str]) -> str:
    """
    Détermine le type de données d'un fichier à partir de ses en-têtes.

    Utilise le mapping de colonnes pour tester la présence des champs
    caractéristiques de chaque type Qomiq.

    Args:
        headers: Liste des en-têtes bruts du fichier.

    Returns:
        "produits" | "budget" | "unknown"
    """
    if not headers:
        return CSV_TYPE_UNKNOWN

    mapped = map_columns(headers)
    present = {field for field, col in mapped.items() if col is not None}

    for csv_type, required_fields, min_count in _RULES:
        matched = sum(1 for f in required_fields if f in present)
        if matched >= min_count:
            return csv_type

    return CSV_TYPE_UNKNOWN
