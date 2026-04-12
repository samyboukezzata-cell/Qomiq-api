"""
Qomiq — Mapping de colonnes CSV universel.

Normalise les en-têtes de colonnes bruts vers les champs canoniques Qomiq,
en tolérant les variantes orthographiques, accents et pluriels courants.
"""
from __future__ import annotations

import unicodedata

# ── Dictionnaire de synonymes ─────────────────────────────────────────────────
#
# Clés : noms canoniques utilisés en interne par Qomiq.
# Valeurs : liste de synonymes acceptés (insensibles à la casse et aux accents).
#
# Groupes :
#   produits  — champs pour kpi_products
#   budget    — champs pour la vue EPM / Budget
#   commun    — champs partagés (periode, etc.)

SYNONYMES: dict[str, list[str]] = {
    # ── Produits ──────────────────────────────────────────────────────────────
    "nom": [
        "nom", "produit", "produits", "product", "name", "libelle", "libellé",
        "designation", "désignation", "article", "ref", "référence",
        "reference", "intitule", "intitulé",
    ],
    "marque": [
        "marque", "marques", "brand", "brands", "fabricant", "fournisseur",
        "manufacturer", "supplier", "editeur", "éditeur", "constructeur",
    ],
    "ca": [
        "ca", "ca_realise", "ca réalisé", "ca_realise", "chiffre_affaires",
        "chiffre affaires", "chiffre d'affaires", "chiffre daffaires",
        "revenus", "revenue", "montant", "ventes_ca", "turnover",
        "ca_ht", "ca ht", "total_ca", "total ca", "recettes", "recette",
        "montant vendu", "total ventes",
    ],
    "ventes": [
        "ventes", "vente", "qte", "quantite", "quantité", "qty", "sales",
        "units", "nb_ventes", "nb ventes", "volume", "qté", "nb_unites",
        "nb unités", "unites_vendues", "unités vendues",
    ],
    "stock": [
        "stock", "inventaire", "inventory", "stock_disponible",
        "stock disponible", "disponible", "qte_stock", "qté stock",
        "encours", "en_cours",
    ],
    # ── Budget / EPM ──────────────────────────────────────────────────────────
    "ligne": [
        "ligne", "item", "poste", "budget_item", "category", "categorie",
        "catégorie", "rubrique", "nature", "compte", "libelle_budget",
        "libellé budget",
    ],
    "budget": [
        "budget", "budget_prevu", "budget prévu", "budget_initial",
        "prevision", "prévision", "forecast", "objectif", "cible",
        "montant_budget", "montant budget",
    ],
    "reel": [
        "reel", "réel", "realise", "réalisé", "actuel", "actual",
        "constate", "constaté", "depense", "dépense", "consomme",
        "consommé", "montant_reel", "montant réel",
    ],
    "ecart": [
        "ecart", "écart", "variance", "gap", "difference", "différence",
        "delta", "deviation", "déviation", "solde",
    ],
    # ── Commun ────────────────────────────────────────────────────────────────
    "periode": [
        "periode", "période", "period", "mois", "month", "trimestre",
        "quarter", "annee", "année", "year", "date", "exercice",
    ],
    # ── Exports Odoo Analyse Produits ─────────────────────────────────────────
    "quantite": [
        "quantité", "quantite", "qty", "qté", "volume",
        "nb ventes", "nombre ventes", "unités vendues", "unites",
    ],
    "categorie": [
        "catégorie", "categorie", "category", "famille", "family",
        "type produit", "gamme",
    ],
}


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normalise une chaîne : minuscules, suppression des accents,
    remplacement des séparateurs (_/-/espace) par un espace unique.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    lowered = ascii_str.lower()
    for sep in ("_", "-"):
        lowered = lowered.replace(sep, " ")
    return " ".join(lowered.split())


# ── API publique ───────────────────────────────────────────────────────────────

def match_column(header: str, field: str) -> bool:
    """
    Retourne True si l'en-tête brut correspond au champ canonique donné.

    La correspondance est insensible à la casse, aux accents et aux
    séparateurs (_/-/espace).

    Args:
        header: En-tête brut tel que lu dans le fichier (ex: "CA Réalisé").
        field:  Nom canonique Qomiq (ex: "ca").

    Returns:
        True si le header est un synonyme connu du field.
    """
    if field not in SYNONYMES:
        return False
    normalized_header = _normalize(header)
    return any(_normalize(syn) == normalized_header for syn in SYNONYMES[field])


def map_columns(headers: list[str]) -> dict[str, str | None]:
    """
    Mappe les champs canoniques aux en-têtes réels du fichier.

    Parcourt chaque en-tête et tente de le faire correspondre à l'un
    des champs canoniques. En cas de doublon (deux colonnes matchent
    le même champ), la première est retenue.

    Args:
        headers: Liste des en-têtes bruts du fichier CSV/XLSX.

    Returns:
        Dict {champ_canonique: en_tête_réel_ou_None}.
        Exemple : {"nom": "Produit", "ca": "CA HT", "marque": None, ...}
    """
    result: dict[str, str | None] = {field: None for field in SYNONYMES}
    for header in headers:
        for field in SYNONYMES:
            if result[field] is None and match_column(header, field):
                result[field] = header
                break
    return result
