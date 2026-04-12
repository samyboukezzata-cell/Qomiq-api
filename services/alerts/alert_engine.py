"""
Qomiq — Moteur de détection des alertes proactives.

Toutes les fonctions sont pures (aucun I/O).
Le paramètre `today` est injectable pour les tests.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from .alert_models import Alert, AlertLevel, AlertType

logger = logging.getLogger(__name__)


# ── Helpers internes ──────────────────────────────────────────────────────────

def _parse_date(value: str) -> Optional[date]:
    """Convertit une chaîne YYYY-MM-DD en date. Retourne None si invalide."""
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _make_id(alert_type: AlertType, entity_id: str) -> str:
    """Génère un ID stable pour dédupliquer les alertes entre deux runs."""
    safe = entity_id.lower().replace(" ", "_")[:40]
    return f"{alert_type.value}__{safe}"


def _today_or(today: Optional[date]) -> date:
    return today if today is not None else date.today()


# ── DEAL_STALE — Deals sans activité récente ──────────────────────────────────

def check_deals_stale(
    deals:         list[dict],
    warning_days:  int = 14,
    critical_days: int = 30,
    today:         Optional[date] = None,
) -> list[Alert]:
    """
    Détecte les deals qui n'ont pas été mis à jour depuis longtemps.

    Règle date_modification :
    - Si `date_modification` est présent → utilisé en priorité.
    - Sinon si `date_cloture` est présent → utilisé comme fallback.
    - Sinon → deal ignoré (pas d'alerte DEAL_STALE).

    Args:
        deals:         Liste de deals (dicts).
        warning_days:  Seuil en jours pour le niveau WARNING.
        critical_days: Seuil en jours pour le niveau CRITICAL.
        today:         Date de référence (injectée en test).

    Returns:
        Liste d'alertes DEAL_STALE.
    """
    ref       = _today_or(today)
    alerts:   list[Alert] = []

    for deal in deals:
        nom = deal.get("nom", "")

        # Résolution de la date de référence
        date_str = deal.get("date_modification") or deal.get("date_cloture")
        if not date_str:
            continue  # pas de date → ignoré

        ref_date = _parse_date(date_str)
        if ref_date is None:
            continue

        age_days = (ref - ref_date).days
        if age_days < warning_days:
            continue

        if age_days >= critical_days:
            level   = AlertLevel.CRITICAL
            message = (
                f"Le deal « {nom} » n'a pas été mis à jour depuis "
                f"{age_days} jours (seuil critique : {critical_days} j)."
            )
        else:
            level   = AlertLevel.WARNING
            message = (
                f"Le deal « {nom} » n'a pas été mis à jour depuis "
                f"{age_days} jours (seuil : {warning_days} j)."
            )

        alerts.append(Alert(
            id=_make_id(AlertType.DEAL_STALE, nom),
            alert_type=AlertType.DEAL_STALE,
            level=level,
            title=f"Deal inactif : {nom}",
            message=message,
            entity_id=nom,
            entity_data=dict(deal),
            created_at=ref.isoformat(),
        ))

    return alerts


# ── DEAL_CLOSING — Clôture imminente ─────────────────────────────────────────

def check_deals_closing(
    deals:         list[dict],
    warning_days:  int = 7,
    critical_days: int = 2,
    today:         Optional[date] = None,
) -> list[Alert]:
    """
    Détecte les deals dont la date de clôture est imminente.

    Seuls les deals dont la date de clôture est DANS LE FUTUR sont traités.
    Les deals déjà clôturés (date_cloture < today) sont ignorés.

    Args:
        deals:         Liste de deals.
        warning_days:  Jours restants pour déclencher un WARNING.
        critical_days: Jours restants pour déclencher un CRITICAL.
        today:         Date de référence.

    Returns:
        Liste d'alertes DEAL_CLOSING.
    """
    ref     = _today_or(today)
    alerts: list[Alert] = []

    for deal in deals:
        nom      = deal.get("nom", "")
        date_str = deal.get("date_cloture")
        if not date_str:
            continue

        cloture = _parse_date(date_str)
        if cloture is None:
            continue

        days_left = (cloture - ref).days
        if days_left < 0 or days_left > warning_days:
            continue  # passé ou trop loin

        if days_left <= critical_days:
            level   = AlertLevel.CRITICAL
            message = (
                f"Le deal « {nom} » clôture dans {days_left} jour(s) "
                f"(seuil critique : {critical_days} j)."
            )
        else:
            level   = AlertLevel.WARNING
            message = (
                f"Le deal « {nom} » clôture dans {days_left} jour(s) "
                f"(seuil : {warning_days} j)."
            )

        alerts.append(Alert(
            id=_make_id(AlertType.DEAL_CLOSING, nom),
            alert_type=AlertType.DEAL_CLOSING,
            level=level,
            title=f"Clôture imminente : {nom}",
            message=message,
            entity_id=nom,
            entity_data=dict(deal),
            created_at=ref.isoformat(),
        ))

    return alerts


# ── STOCK_LOW — Stock insuffisant ─────────────────────────────────────────────

def check_stock_low(
    products:            list[dict],
    warning_threshold:   int = 5,
    critical_threshold:  int = 0,
) -> list[Alert]:
    """
    Détecte les produits dont le stock est sous le seuil minimum.

    Args:
        products:           Liste de produits KPI.
        warning_threshold:  Stock ≤ ce seuil → WARNING.
        critical_threshold: Stock ≤ ce seuil → CRITICAL.

    Returns:
        Liste d'alertes STOCK_LOW.
    """
    today   = date.today().isoformat()
    alerts: list[Alert] = []

    for product in products:
        nom   = product.get("nom", "")
        stock = product.get("stock", None)
        if stock is None:
            continue

        try:
            stock_val = int(stock)
        except (ValueError, TypeError):
            continue

        if stock_val > warning_threshold:
            continue

        if stock_val <= critical_threshold:
            level   = AlertLevel.CRITICAL
            message = (
                f"Stock critique pour « {nom} » : "
                f"{stock_val} unité(s) (seuil : {critical_threshold})."
            )
        else:
            level   = AlertLevel.WARNING
            message = (
                f"Stock faible pour « {nom} » : "
                f"{stock_val} unité(s) (seuil : {warning_threshold})."
            )

        alerts.append(Alert(
            id=_make_id(AlertType.STOCK_LOW, nom),
            alert_type=AlertType.STOCK_LOW,
            level=level,
            title=f"Stock bas : {nom}",
            message=message,
            entity_id=nom,
            entity_data=dict(product),
            created_at=today,
        ))

    return alerts


# ── BUDGET_OVERRUN — Dépassement budgétaire ───────────────────────────────────

def check_budget_overrun(
    lines:        list[dict],
    warning_pct:  float = 0.0,
    critical_pct: float = 0.20,
) -> list[Alert]:
    """
    Détecte les lignes budgétaires en dépassement.

    Chaque ligne doit contenir {"nom": str, "budget": float, "reel": float}.
    Les lignes avec budget = 0 sont ignorées (division par zéro).

    Args:
        lines:        Liste de lignes budgétaires.
        warning_pct:  Tout dépassement (reel > budget + warning_pct*budget).
        critical_pct: Dépassement ≥ critical_pct du budget → CRITICAL.

    Returns:
        Liste d'alertes BUDGET_OVERRUN.
    """
    today   = date.today().isoformat()
    alerts: list[Alert] = []

    for line in lines:
        nom    = line.get("nom", "")
        budget = line.get("budget")
        reel   = line.get("reel")

        if budget is None or reel is None:
            continue

        try:
            budget_f = float(budget)
            reel_f   = float(reel)
        except (ValueError, TypeError):
            continue

        if budget_f == 0:
            continue  # évite division par zéro

        overrun_pct = (reel_f - budget_f) / budget_f

        if overrun_pct <= warning_pct:
            continue

        if overrun_pct >= critical_pct:
            level   = AlertLevel.CRITICAL
            message = (
                f"Dépassement critique sur « {nom} » : "
                f"{overrun_pct * 100:.1f}% au-dessus du budget "
                f"({reel_f:.0f} vs {budget_f:.0f})."
            )
        else:
            level   = AlertLevel.WARNING
            message = (
                f"Dépassement budgétaire sur « {nom} » : "
                f"{overrun_pct * 100:.1f}% au-dessus du budget "
                f"({reel_f:.0f} vs {budget_f:.0f})."
            )

        alerts.append(Alert(
            id=_make_id(AlertType.BUDGET_OVERRUN, nom),
            alert_type=AlertType.BUDGET_OVERRUN,
            level=level,
            title=f"Dépassement : {nom}",
            message=message,
            entity_id=nom,
            entity_data=dict(line),
            created_at=today,
        ))

    return alerts


# ── run_all_checks — Point d'entrée principal ─────────────────────────────────

def run_all_checks(
    pipeline_deals:  Optional[list[dict]] = None,
    kpi_products:    Optional[list[dict]] = None,
    budget_lines:    Optional[list[dict]] = None,
    today:           Optional[date] = None,
) -> list[Alert]:
    """
    Lance tous les contrôles disponibles et retourne la liste consolidée.

    Args:
        pipeline_deals:  Deals du pipeline commercial.
        kpi_products:    Produits KPI (pour STOCK_LOW).
        budget_lines:    Lignes budgétaires normalisées (nom, budget, reel).
        today:           Date de référence (injectée en test).

    Returns:
        Liste d'alertes triée par niveau (CRITICAL d'abord).
    """
    alerts: list[Alert] = []

    if pipeline_deals:
        alerts.extend(check_deals_stale(pipeline_deals, today=today))
        alerts.extend(check_deals_closing(pipeline_deals, today=today))

    if kpi_products:
        stock_alerts = check_stock_low(kpi_products)
        # Limiter à 3 alertes produits (les plus critiques en premier)
        alerts.extend(stock_alerts[:3])

    if budget_lines:
        alerts.extend(check_budget_overrun(budget_lines))

    # Tri : CRITICAL d'abord, puis WARNING, puis INFO
    _order = {AlertLevel.CRITICAL: 0, AlertLevel.WARNING: 1, AlertLevel.INFO: 2}
    alerts.sort(key=lambda a: _order.get(a.level, 9))

    return alerts
