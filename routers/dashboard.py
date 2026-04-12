"""
Qomiq API — Router tableau de bord.

Endpoints :
  GET /dashboard/summary  → DashboardSummary complète
  GET /dashboard/kpis     → KPIs condensés (pipeline + CA + budget + alertes)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.user_data import get_user_data
from routers.auth import get_current_user
from services.alerts.alert_engine import run_all_checks
from services.alerts.alert_models import Alert
from services.dashboard.dashboard_engine import compute

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _load_data(db: Session, user_id: int) -> dict:
    """Charge toutes les données UserData du user."""
    return {
        "pipeline":  get_user_data(db, user_id, "pipeline"),
        "ca_mensuel": get_user_data(db, user_id, "ca_mensuel"),
        "budget":    get_user_data(db, user_id, "budget"),
        "produits":  get_user_data(db, user_id, "produits"),
    }


def _compute_alerts(data: dict) -> list[Alert]:
    return run_all_checks(
        pipeline_deals=data["pipeline"],
        kpi_products=data["produits"],
        budget_lines=data["budget"],
    )


@router.get("/summary", summary="Tableau de bord complet")
def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Calcule et retourne le DashboardSummary complet."""
    data    = _load_data(db, current_user.id)
    alerts  = _compute_alerts(data)
    summary = compute(
        pipeline_deals=data["pipeline"],
        ca_rows=data["ca_mensuel"],
        budget_lines=data["budget"],
        alerts=alerts,
    )
    result = {
        "pipeline": {
            "total_montant":      summary.pipeline.total_montant,
            "count":              summary.pipeline.count,
            "closing_soon_count": summary.pipeline.closing_soon_count,
            "top_deals": [
                {
                    "nom":              d.nom,
                    "client":           d.client,
                    "montant":          d.montant,
                    "days_until_close": d.days_until_close,
                }
                for d in summary.pipeline.top_deals
            ],
        },
        "ca": {
            "current_month":       summary.ca.current_month,
            "previous_month":      summary.ca.previous_month,
            "growth_pct":          summary.ca.growth_pct,
            "current_month_label": summary.ca.current_month_label,
            "objectif":            summary.ca.objectif,
            "objectif_pct":        summary.ca.objectif_pct,
            "is_behind":           summary.ca.is_behind,
        },
        "budget": {
            "total_budget":      summary.budget.total_budget,
            "total_reel":        summary.budget.total_reel,
            "consumed_pct":      summary.budget.consumed_pct,
            "lines_over_budget": summary.budget.lines_over_budget,
        },
        "alerts": {
            "total_active":   summary.alerts.total_active,
            "critical_count": summary.alerts.critical_count,
            "warning_count":  summary.alerts.warning_count,
        },
        "computed_at":  summary.computed_at,
        "has_data":     summary.has_data,
        "health_score": summary.health_score,
        "health_delta": summary.health_delta,
        "ca_history":   summary.ca_history,
        "actions": [
            {"title": a.title, "description": a.description, "priority": a.priority}
            for a in summary.actions
        ],
    }
    return result


@router.get("/kpis", summary="KPIs condensés")
def dashboard_kpis(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Retourne uniquement les compteurs clés (plus léger que /summary)."""
    data    = _load_data(db, current_user.id)
    alerts  = _compute_alerts(data)
    summary = compute(
        pipeline_deals=data["pipeline"],
        ca_rows=data["ca_mensuel"],
        budget_lines=data["budget"],
        alerts=alerts,
    )
    return {
        "pipeline_count":     summary.pipeline.count,
        "pipeline_montant":   summary.pipeline.total_montant,
        "ca_current_month":   summary.ca.current_month,
        "ca_growth_pct":      summary.ca.growth_pct,
        "budget_consumed_pct": summary.budget.consumed_pct,
        "alert_critical":     summary.alerts.critical_count,
        "alert_warning":      summary.alerts.warning_count,
        "health_score":       summary.health_score,
        "has_data":           summary.has_data,
    }
