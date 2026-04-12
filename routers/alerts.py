"""
Qomiq API — Router alertes proactives.

Endpoints :
  GET   /alerts/               → liste des alertes (filtrable)
  PATCH /alerts/{alert_id}/read → marque une alerte comme lue
  POST  /alerts/refresh         → recalcul des alertes
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.user_data import get_user_data, save_user_data
from routers.auth import get_current_user
from services.alerts.alert_engine import run_all_checks
from services.alerts.alert_models import Alert

router = APIRouter(prefix="/alerts", tags=["alerts"])

_ALERTS_TYPE = "alerts_state"


def _load_alerts_state(db: Session, user_id: int) -> list[Alert]:
    """Charge les alertes persistées en DB (état is_read / is_dismissed)."""
    rows = get_user_data(db, user_id, _ALERTS_TYPE)
    return [Alert.from_dict(r) for r in rows]


def _save_alerts_state(db: Session, user_id: int, alerts: list[Alert]) -> None:
    save_user_data(db, user_id, _ALERTS_TYPE, [a.to_dict() for a in alerts])


def _refresh_alerts(db: Session, user_id: int) -> list[Alert]:
    """
    Recalcule les alertes depuis les données UserData et fusionne l'état
    is_read / is_dismissed depuis la persisted state.
    """
    pipeline = get_user_data(db, user_id, "pipeline")
    produits = get_user_data(db, user_id, "produits")
    budget   = get_user_data(db, user_id, "budget")

    fresh = run_all_checks(
        pipeline_deals=pipeline,
        kpi_products=produits,
        budget_lines=budget,
    )

    # Fusionner l'état précédent (is_read, is_dismissed)
    old_state = {a.id: a for a in _load_alerts_state(db, user_id)}
    for alert in fresh:
        if alert.id in old_state:
            alert.is_read      = old_state[alert.id].is_read
            alert.is_dismissed = old_state[alert.id].is_dismissed

    _save_alerts_state(db, user_id, fresh)
    return fresh


@router.get("/", summary="Liste des alertes")
def list_alerts(
    level: Optional[str] = Query(None, pattern="^(critical|warning|info)$"),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Retourne les alertes actives, filtrées selon les query params."""
    alerts = _load_alerts_state(db, user_id=current_user.id)

    # Si aucune alerte stockée, calculer une première fois
    if not alerts:
        alerts = _refresh_alerts(db, current_user.id)

    # Filtres
    result = [a for a in alerts if not a.is_dismissed]
    if level:
        result = [a for a in result if a.level == level]
    if unread_only:
        result = [a for a in result if not a.is_read]

    return [a.to_dict() for a in result]


@router.patch("/{alert_id}/read", summary="Marquer une alerte comme lue")
def mark_read(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Marque l'alerte alert_id comme lue pour l'utilisateur courant."""
    alerts = _load_alerts_state(db, current_user.id)
    for alert in alerts:
        if alert.id == alert_id:
            alert.is_read = True
            _save_alerts_state(db, current_user.id, alerts)
            return {"ok": True, "alert_id": alert_id}
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Alerte '{alert_id}' introuvable.",
    )


@router.post("/refresh", summary="Recalculer les alertes")
def refresh_alerts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Force le recalcul des alertes depuis les données UserData."""
    alerts = _refresh_alerts(db, current_user.id)
    active = [a for a in alerts if not a.is_dismissed]
    return {
        "count":    len(active),
        "critical": sum(1 for a in active if a.level == "critical"),
        "warning":  sum(1 for a in active if a.level == "warning"),
    }
