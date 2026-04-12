"""
Qomiq — Moteur de calcul du tableau de bord premier écran.

Toutes les fonctions sont pures (aucun I/O).
Le paramètre `today` est injectable pour les tests.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from .dashboard_models import (
    ActionItem,
    AlertStats,
    BudgetStats,
    CaStats,
    DashboardSummary,
    DealSummary,
    PipelineStats,
)

logger = logging.getLogger(__name__)

_MONTH_LABELS = [
    "Jan.", "Fév.", "Mar.", "Avr.", "Mai",  "Jui.",
    "Jul.", "Aoû.", "Sep.", "Oct.", "Nov.", "Déc.",
]
_CLOSING_SOON_DAYS = 7


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_euros(value: float) -> str:
    """
    Formate un montant en euros lisible.

    Exemples :
        1_234_567 → "1.2M€"
        45_300    → "45k€"
        800       → "800€"
    """
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M€"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k€"
    return f"{value:.0f}€"


def _parse_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _today_or(today: Optional[date]) -> date:
    return today if today is not None else date.today()


def _month_label(year: int, month: int) -> str:
    return f"{_MONTH_LABELS[month - 1]} {year}"


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _parse_ym(row: dict) -> tuple[int, int] | None:
    """
    Extrait (annee, mois) depuis un row ca_mensuel.

    Supporte deux formats :
    - "YYYY-MM" dans le champ "mois" (ex: "2026-04")
    - champs séparés "mois" (int ou str 1-12) + "annee" (int ou str)
    """
    mois_raw = str(row.get("mois", "")).strip()
    # Format "YYYY-MM"
    if len(mois_raw) == 7 and mois_raw[4] == "-":
        try:
            y, m = mois_raw.split("-")
            return int(y), int(m)
        except (ValueError, TypeError):
            return None
    # Format mois seul + annee séparé
    try:
        m = int(mois_raw)
        y = int(str(row.get("annee", 0)).strip())
        if 1 <= m <= 12 and y > 0:
            return y, m
    except (ValueError, TypeError):
        pass
    return None


def _get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """Accès uniforme dict ou objet."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _level_str(obj: Any) -> str:
    lv = _get_attr(obj, "level", "")
    return lv.value if hasattr(lv, "value") else str(lv)


# ── Calculs partiels ──────────────────────────────────────────────────────────

def compute_pipeline_stats(
    deals: list[dict],
    today: Optional[date] = None,
) -> PipelineStats:
    """
    Calcule les statistiques du pipeline commercial.

    Args:
        deals: Liste de deals (dicts avec nom, client, montant, date_cloture).
        today: Date de référence (injectée en test).

    Returns:
        PipelineStats avec total, compteur, deals imminents et top 3.
    """
    ref           = _today_or(today)
    total_montant = 0.0
    closing_soon  = 0
    summaries:  list[DealSummary] = []

    for deal in deals:
        nom    = deal.get("nom", "")
        client = deal.get("client", "")
        try:
            montant = float(deal.get("montant") or 0)
        except (ValueError, TypeError):
            montant = 0.0

        days_until_close: int | None = None
        date_str = deal.get("date_cloture")
        if date_str:
            dt = _parse_date(date_str)
            if dt is not None:
                delta = (dt - ref).days
                if delta >= 0:
                    days_until_close = delta
                    if delta <= _CLOSING_SOON_DAYS:
                        closing_soon += 1

        total_montant += montant
        summaries.append(DealSummary(
            nom=nom,
            client=client,
            montant=montant,
            days_until_close=days_until_close,
        ))

    top_deals = sorted(summaries, key=lambda d: d.montant, reverse=True)[:3]

    return PipelineStats(
        total_montant=total_montant,
        count=len(summaries),
        closing_soon_count=closing_soon,
        top_deals=top_deals,
    )


def compute_ca_stats(
    ca_rows: list[dict],
    today: Optional[date] = None,
    objectif: float = 0.0,
) -> CaStats:
    """
    Calcule les statistiques CA mois courant vs mois précédent.

    Args:
        ca_rows:  Lignes CA avec {"mois": "YYYY-MM", "ca_realise": float}.
        today:    Date de référence.
        objectif: Objectif mensuel (0 = non renseigné).

    Returns:
        CaStats avec totaux mensuel, croissance et indicateurs d'objectif.
    """
    ref      = _today_or(today)
    py, pm   = _prev_month(ref.year, ref.month)

    current  = 0.0
    previous = 0.0

    for row in ca_rows:
        ym = _parse_ym(row)
        if ym is None:
            continue
        y, m = ym
        try:
            ca = float(row.get("ca_realise") or 0)
        except (ValueError, TypeError):
            ca = 0.0
        if y == ref.year and m == ref.month:
            current += ca
        elif y == py and m == pm:
            previous += ca

    growth_pct: float | None = None
    if previous > 0:
        growth_pct = (current - previous) / previous * 100

    objectif_pct = (current / objectif * 100) if objectif > 0 else 0.0
    is_behind    = objectif > 0 and current < objectif

    return CaStats(
        current_month=current,
        previous_month=previous,
        growth_pct=growth_pct,
        current_month_label=_month_label(ref.year, ref.month),
        objectif=objectif,
        objectif_pct=objectif_pct,
        is_behind=is_behind,
    )


def compute_budget_stats(lines: list[dict]) -> BudgetStats:
    """
    Calcule la synthèse budgétaire.

    Args:
        lines: Lignes avec {"nom": str, "budget": float, "reel": float}.

    Returns:
        BudgetStats avec totaux et nombre de lignes en dépassement.
    """
    total_budget  = 0.0
    total_reel    = 0.0
    lines_over    = 0

    for line in lines:
        try:
            budget = float(line.get("budget") or 0)
            reel   = float(line.get("reel")   or 0)
        except (ValueError, TypeError):
            continue
        total_budget += budget
        total_reel   += reel
        if budget > 0 and reel > budget:
            lines_over += 1

    consumed_pct = (total_reel / total_budget * 100) if total_budget > 0 else 0.0

    return BudgetStats(
        total_budget=total_budget,
        total_reel=total_reel,
        consumed_pct=consumed_pct,
        lines_over_budget=lines_over,
    )


def compute_alert_stats(alerts: list) -> AlertStats:
    """
    Calcule les compteurs d'alertes actives (non masquées).

    Accepte des objets Alert ou des dicts.

    Args:
        alerts: Liste d'alertes (Alert ou dict).

    Returns:
        AlertStats avec totaux par niveau.
    """
    active   = [a for a in alerts if not _get_attr(a, "is_dismissed", False)]
    critical = [a for a in active  if _level_str(a) == "critical"]
    warning  = [a for a in active  if _level_str(a) == "warning"]

    return AlertStats(
        total_active=len(active),
        critical_count=len(critical),
        warning_count=len(warning),
    )


def compute_ca_history(
    ca_rows: list[dict],
    today: Optional[date] = None,
    n: int = 6,
) -> list[dict]:
    """
    Agrège le CA par mois pour les n derniers mois (du plus ancien au plus récent).

    Returns:
        list de dicts : {"mois": "YYYY-MM", "label": "Avr.", "ca_realise": float, "objectif": float}
    """
    ref = _today_or(today)

    # Générer les n derniers mois (du plus récent vers le plus ancien)
    months: list[tuple[int, int]] = []
    y, m = ref.year, ref.month
    for _ in range(n):
        months.append((y, m))
        y, m = _prev_month(y, m)
    months.reverse()   # le plus ancien en premier

    # Agréger les ca_rows par (annee, mois)
    totals: dict[tuple[int, int], float] = {}
    for row in ca_rows:
        ym = _parse_ym(row)
        if ym is None:
            continue
        y, m = ym
        try:
            ca = float(row.get("ca_realise") or 0)
        except (ValueError, TypeError):
            ca = 0.0
        totals[(y, m)] = totals.get((y, m), 0.0) + ca

    return [
        {
            "mois":       f"{yr:04d}-{mo:02d}",
            "label":      _MONTH_LABELS[mo - 1],
            "ca_realise": totals.get((yr, mo), 0.0),
            "objectif":   0.0,
        }
        for yr, mo in months
    ]


def compute_health_score(
    pipeline: PipelineStats,
    ca: CaStats,
    budget: BudgetStats,
    alerts: AlertStats,
) -> int:
    """
    Calcule un score de santé 0-100 à partir des métriques.

    Pénalités :
    - Alerte critique : -10 chacune (max -40)
    - Alerte warning  : -3 chacune  (max -15)
    - Budget > 110%   : -15  |  > 100% : -5
    - Croissance CA < -10% : -10  |  < 0% : -5
    - Moins de 2 deals actifs : -10
    """
    score = 100
    score -= min(40, alerts.critical_count * 10)
    score -= min(15, alerts.warning_count  *  3)

    if budget.consumed_pct > 110:
        score -= 15
    elif budget.consumed_pct > 100:
        score -= 5

    if ca.growth_pct is not None:
        if ca.growth_pct < -10:
            score -= 10
        elif ca.growth_pct < 0:
            score -= 5

    if pipeline.count < 2:
        score -= 10

    return max(0, score)


def compute_actions(alerts: list) -> list[ActionItem]:
    """
    Dérive des actions prioritaires depuis les alertes non lues et non masquées.

    Returns:
        Liste d'ActionItem triée HIGH → MEDIUM → LOW, limitée à 10.
    """
    _priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    items: list[ActionItem] = []

    for a in alerts:
        if _get_attr(a, "is_dismissed", False) or _get_attr(a, "is_read", False):
            continue
        level    = _level_str(a)
        priority = "HIGH" if level == "critical" else "MEDIUM" if level == "warning" else "LOW"
        items.append(ActionItem(
            title=str(_get_attr(a, "title", "")),
            description=str(_get_attr(a, "message", "")),
            priority=priority,
        ))

    items.sort(key=lambda x: _priority_order.get(x.priority, 9))
    return items[:10]


# ── Point d'entrée ────────────────────────────────────────────────────────────

def compute(
    pipeline_deals:  Optional[list[dict]] = None,
    ca_rows:         Optional[list[dict]] = None,
    budget_lines:    Optional[list[dict]] = None,
    alerts:          Optional[list]       = None,
    today:           Optional[date]       = None,
) -> DashboardSummary:
    """
    Calcule le résumé complet du tableau de bord.

    Args:
        pipeline_deals: Deals du pipeline.
        ca_rows:        Lignes CA mensuelles.
        budget_lines:   Lignes budgétaires normalisées.
        alerts:         Alertes chargées depuis alert_store.
        today:          Date de référence (injectée en test).

    Returns:
        DashboardSummary agrégé.
    """
    ref         = _today_or(today)
    _deals      = pipeline_deals or []
    _ca         = ca_rows        or []
    _budget     = budget_lines   or []
    _alerts     = alerts         or []

    pipeline    = compute_pipeline_stats(_deals,  today=ref)
    ca          = compute_ca_stats(_ca,           today=ref)
    budget      = compute_budget_stats(_budget)
    alert_stats = compute_alert_stats(_alerts)
    history     = compute_ca_history(_ca,         today=ref)
    actions     = compute_actions(_alerts)
    score       = compute_health_score(pipeline, ca, budget, alert_stats)
    has_data    = bool(_deals or _ca or _budget)

    return DashboardSummary(
        pipeline=pipeline,
        ca=ca,
        budget=budget,
        alerts=alert_stats,
        computed_at=ref.isoformat(),
        has_data=has_data,
        health_score=score,
        health_delta=0,
        ca_history=history,
        actions=actions,
    )
