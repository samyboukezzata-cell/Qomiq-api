"""
Qomiq API — Validation des lignes importées avant persistance.

Vérifie la présence des champs requis et la cohérence des valeurs
pour chaque type de données supporté.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Champs requis par data_type ────────────────────────────────────────────────

_REQUIRED: dict[str, list[str]] = {
    "pipeline":   ["nom"],
    "ca_mensuel": ["mois", "ca_realise"],
    "produits":   ["nom"],
    "budget":     ["nom"],
    "contacts":   ["nom"],
}

_NUMERIC: dict[str, list[str]] = {
    "pipeline":   ["montant"],
    "ca_mensuel": ["ca_realise"],
    "produits":   ["ca", "ventes", "stock"],
    "budget":     ["budget", "reel"],
    "contacts":   [],
}


@dataclass
class ValidationResult:
    """Résultat d'une validation de lignes."""
    valid_rows:   list[dict]
    invalid_rows: list[dict]   # dict original + clé "_errors": list[str]
    warnings:     list[str]
    stats:        dict         # {"total", "valid", "invalid"}


def validate_rows(rows: list[dict], data_type: str) -> ValidationResult:
    """
    Valide une liste de lignes pour le data_type donné.

    Contrôles effectués :
    - Présence des champs requis (non-vides).
    - Cohérence numérique des champs numériques (warning si non-parseable).

    Args:
        rows:      Lignes déjà remappées vers les champs canoniques.
        data_type: Type de données ("pipeline", "ca_mensuel", …).

    Returns:
        ValidationResult avec valid_rows, invalid_rows, warnings, stats.
    """
    required = _REQUIRED.get(data_type, [])
    numeric  = _NUMERIC.get(data_type, [])
    warnings: list[str] = []
    valid:    list[dict] = []
    invalid:  list[dict] = []

    if data_type not in _REQUIRED:
        warnings.append(f"Type '{data_type}' non reconnu — aucune validation appliquée.")
        return ValidationResult(
            valid_rows=list(rows),
            invalid_rows=[],
            warnings=warnings,
            stats={"total": len(rows), "valid": len(rows), "invalid": 0},
        )

    for row in rows:
        errors: list[str] = []

        # Champs requis
        for field_name in required:
            val = str(row.get(field_name, "")).strip()
            if not val:
                errors.append(f"Champ requis manquant : '{field_name}'.")

        # Champs numériques
        for field_name in numeric:
            val = str(row.get(field_name, "")).strip()
            if val:
                try:
                    float(val.replace(",", ".").replace(" ", ""))
                except ValueError:
                    warnings.append(
                        f"Valeur non numérique pour '{field_name}' : '{val[:30]}'."
                    )

        if errors:
            invalid.append({**row, "_errors": errors})
        else:
            valid.append(row)

    return ValidationResult(
        valid_rows=valid,
        invalid_rows=invalid,
        warnings=warnings,
        stats={"total": len(rows), "valid": len(valid), "invalid": len(invalid)},
    )


def remap_rows(
    rows: list[dict],
    mapping: dict[str, str],
) -> list[dict]:
    """
    Remappe les clés des lignes selon le mapping {header_csv: champ_canonique}.

    Les colonnes non présentes dans le mapping sont conservées telles quelles.

    Args:
        rows:    Lignes avec les en-têtes bruts.
        mapping: {header_csv: champ_canonique}.  Valeurs vides → ignorées.

    Returns:
        Nouvelles lignes avec les champs canoniques.
    """
    # Inverser : {header_brut: champ_canonique}
    col_map = {src: dst for src, dst in mapping.items() if dst}
    result: list[dict] = []
    for row in rows:
        new_row: dict = {}
        for key, val in row.items():
            new_key = col_map.get(key, key)
            new_row[new_key] = val
        result.append(new_row)
    return result
