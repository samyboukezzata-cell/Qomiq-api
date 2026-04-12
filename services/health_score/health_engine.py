"""
Qomiq — Moteur du Score de Santé Commerciale.

Toutes les fonctions de composante sont pures (aucun I/O).
Le paramètre `today` est injectable pour les tests.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from .health_models import HealthScoreResult

logger = logging.getLogger(__name__)

# ── Pondérations des 5 composantes ────────────────────────────────────────────

_WEIGHTS: dict[str, float] = {
    "ca":       0.30,
    "pipeline": 0.25,
    "win_rate": 0.20,
    "activite": 0.15,
    "alertes":  0.10,
}

_STALE_DAYS = 14   # jours sans mise à jour → deal considéré inactif


# ── Helpers internes ──────────────────────────────────────────────────────────

def _parse_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


def _today_or(today: Optional[date]) -> date:
    return today if today is not None else date.today()


def _label_and_color(score: int) -> tuple[str, str]:
    if score >= 80:
        return "Excellent", "#0d9488"
    if score >= 60:
        return "Bon", "#16a34a"
    if score >= 40:
        return "Moyen", "#f97316"
    return "Faible", "#dc2626"


# ── Composantes (fonctions pures) ─────────────────────────────────────────────

def score_ca(ca_realise: float, ca_objectif: float) -> float:
    """
    Composante CA : ratio réalisé / objectif.

    - Objectif non renseigné (≤ 0) → 50.0 (neutre).
    - Dépassement de l'objectif → plafonné à 100.
    - Valeurs négatives tolérées → plancher à 0.

    Returns:
        float 0.0 – 100.0
    """
    if ca_objectif <= 0:
        return 50.0
    ratio = ca_realise / ca_objectif
    return float(min(100.0, max(0.0, round(ratio * 100, 1))))


def score_pipeline(nb_deals: int, valeur_ponderee: float) -> float:
    """
    Composante pipeline : quantité et valeur des deals actifs.

    - 0 deals → 0.
    - Score de comptage : min(80, nb_deals × 12) — 7 deals ≈ 84 → plafonné à 80.
    - Bonus de 20 si valeur_ponderee > 0 (pipeline valorisé).

    Returns:
        float 0.0 – 100.0
    """
    if nb_deals == 0:
        return 0.0
    count_score = min(80.0, nb_deals * 12.0)
    value_bonus = 20.0 if valeur_ponderee > 0 else 0.0
    return float(min(100.0, count_score + value_bonus))


def score_win_rate(nb_gagnes: int, nb_perdus: int) -> float:
    """
    Composante taux de conversion : gagnes / (gagnes + perdus).

    - Aucun historique (0/0) → 50.0 (neutre).

    Returns:
        float 0.0 – 100.0
    """
    total = nb_gagnes + nb_perdus
    if total == 0:
        return 50.0
    return float(round(nb_gagnes / total * 100, 1))


def score_activite(nb_stale: int, nb_overdue: int, nb_actifs: int) -> float:
    """
    Composante activité : fraîcheur et respect des échéances des deals.

    - Aucun deal actif → 50.0 (neutre).
    - Pénalité inactivité  : -15 par deal stale   (max -60).
    - Pénalité hors-délai  : -20 par deal overdue  (max -60).

    Returns:
        float 0.0 – 100.0
    """
    if nb_actifs == 0:
        return 50.0
    s = 100.0 - min(60.0, nb_stale * 15.0) - min(60.0, nb_overdue * 20.0)
    return float(max(0.0, s))


def score_alertes(nb_critical: int, nb_warning: int) -> float:
    """
    Composante alertes : poids des alertes actives non masquées.

    - Pénalité critique : -20 par alerte  (max -80).
    - Pénalité warning  :  -5 par alerte  (max -30).

    Returns:
        float 0.0 – 100.0
    """
    s = 100.0 - min(80.0, nb_critical * 20.0) - min(30.0, nb_warning * 5.0)
    return float(max(0.0, s))


# ── Score global ──────────────────────────────────────────────────────────────

def compute_health_score(
    ca_realise:      float         = 0.0,
    ca_objectif:     float         = 0.0,
    nb_deals:        int           = 0,
    valeur_ponderee: float         = 0.0,
    nb_gagnes:       int           = 0,
    nb_perdus:       int           = 0,
    nb_stale:        int           = 0,
    nb_overdue:      int           = 0,
    nb_actifs:       int           = 0,
    nb_critical:     int           = 0,
    nb_warning:      int           = 0,
    today:           Optional[date] = None,
) -> HealthScoreResult:
    """
    Calcule le Score de Santé Commerciale (0-100) à partir de 5 composantes.

    Pondérations : CA 30 % · Pipeline 25 % · Win-rate 20 % · Activité 15 % · Alertes 10 %

    Args:
        ca_realise:      CA réalisé sur le mois courant.
        ca_objectif:     Objectif CA mensuel (0 = non renseigné).
        nb_deals:        Nombre de deals actifs dans le pipeline.
        valeur_ponderee: Valeur totale (ou pondérée) du pipeline.
        nb_gagnes:       Deals conclus (historique).
        nb_perdus:       Deals perdus (historique).
        nb_stale:        Deals sans activité depuis ≥ 14 jours.
        nb_overdue:      Deals dépassant leur date de clôture prévue.
        nb_actifs:       Total des deals actifs (base de calcul activité).
        nb_critical:     Alertes critiques non masquées.
        nb_warning:      Alertes warning non masquées.
        today:           Date de référence (injectable en test).

    Returns:
        HealthScoreResult complet avec composantes détaillées.
    """
    ref = _today_or(today)

    c_ca       = score_ca(ca_realise, ca_objectif)
    c_pipeline = score_pipeline(nb_deals, valeur_ponderee)
    c_win_rate = score_win_rate(nb_gagnes, nb_perdus)
    c_activite = score_activite(nb_stale, nb_overdue, nb_actifs)
    c_alertes  = score_alertes(nb_critical, nb_warning)

    raw = (
        c_ca       * _WEIGHTS["ca"]
        + c_pipeline * _WEIGHTS["pipeline"]
        + c_win_rate * _WEIGHTS["win_rate"]
        + c_activite * _WEIGHTS["activite"]
        + c_alertes  * _WEIGHTS["alertes"]
    )
    score         = max(0, min(100, round(raw)))
    label, color  = _label_and_color(score)

    return HealthScoreResult(
        score=              score,
        label=              label,
        color=              color,
        component_ca=       c_ca,
        component_pipeline= c_pipeline,
        component_win_rate= c_win_rate,
        component_activite= c_activite,
        component_alertes=  c_alertes,
        computed_at=        ref.isoformat(),
        secteur=            "",
        inputs={
            "ca_realise":      ca_realise,
            "ca_objectif":     ca_objectif,
            "nb_deals":        nb_deals,
            "valeur_ponderee": valeur_ponderee,
            "nb_gagnes":       nb_gagnes,
            "nb_perdus":       nb_perdus,
            "nb_stale":        nb_stale,
            "nb_overdue":      nb_overdue,
            "nb_actifs":       nb_actifs,
            "nb_critical":     nb_critical,
            "nb_warning":      nb_warning,
        },
    )
