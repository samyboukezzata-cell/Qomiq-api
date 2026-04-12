"""
Qomiq API — Router Score de Santé Commerciale.

Endpoints :
  GET /health-score/current  → score calculé depuis les données UserData
  GET /health-score/history  → historique (max weeks dernières semaines)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.user_data import get_user_data, save_user_data
from routers.auth import get_current_user
from services.alerts.alert_engine import run_all_checks
from services.health_score.health_engine import compute_health_score
from services.health_score.health_models import HealthScoreResult

router = APIRouter(prefix="/health-score", tags=["health-score"])

_HISTORY_TYPE  = "health_history"
_MAX_HISTORY   = 16


def _compute_from_db(db: Session, user_id: int) -> HealthScoreResult:
    """Calcule le score depuis les données UserData de l'utilisateur."""
    pipeline = get_user_data(db, user_id, "pipeline")
    ca_rows  = get_user_data(db, user_id, "ca_mensuel")
    produits = get_user_data(db, user_id, "produits")
    budget   = get_user_data(db, user_id, "budget")

    # ── Pipeline ──────────────────────────────────────────────────────────────
    from datetime import date
    ref = date.today()
    cur_str = f"{ref.year:04d}-{ref.month:02d}"
    _STALE_DAYS = 14

    nb_deals        = len(pipeline)
    nb_actifs       = nb_deals
    valeur_ponderee = 0.0
    nb_stale        = 0
    nb_overdue      = 0
    nb_gagnes       = 0
    nb_perdus       = 0

    for deal in pipeline:
        try:
            valeur_ponderee += float(deal.get("montant") or 0)
        except (ValueError, TypeError):
            pass
        statut = str(deal.get("statut", "")).lower().strip()
        if statut in ("gagné", "gagne", "won"):
            nb_gagnes += 1
        elif statut in ("perdu", "lost"):
            nb_perdus += 1

        date_str = deal.get("date_modification") or deal.get("date_cloture")
        if date_str:
            try:
                d = date.fromisoformat(str(date_str))
                if (ref - d).days >= _STALE_DAYS:
                    nb_stale += 1
            except (ValueError, TypeError):
                pass

        close_str = deal.get("date_cloture")
        if close_str:
            try:
                d = date.fromisoformat(str(close_str))
                if d < ref:
                    nb_overdue += 1
            except (ValueError, TypeError):
                pass

    # ── CA mois courant ───────────────────────────────────────────────────────
    ca_realise  = 0.0
    ca_objectif = 0.0
    for row in ca_rows:
        if str(row.get("mois", "")) == cur_str:
            try:
                ca_realise  += float(row.get("ca_realise") or 0)
                ca_objectif += float(
                    row.get("objectif") or row.get("ca_objectif") or 0
                )
            except (ValueError, TypeError):
                pass

    # ── Alertes ───────────────────────────────────────────────────────────────
    live_alerts = run_all_checks(
        pipeline_deals=pipeline,
        kpi_products=produits,
        budget_lines=budget,
    )
    nb_critical = sum(1 for a in live_alerts if a.level == "critical" and not a.is_dismissed)
    nb_warning  = sum(1 for a in live_alerts if a.level == "warning"  and not a.is_dismissed)

    return compute_health_score(
        ca_realise=ca_realise,
        ca_objectif=ca_objectif,
        nb_deals=nb_deals,
        valeur_ponderee=valeur_ponderee,
        nb_gagnes=nb_gagnes,
        nb_perdus=nb_perdus,
        nb_stale=nb_stale,
        nb_overdue=nb_overdue,
        nb_actifs=nb_actifs,
        nb_critical=nb_critical,
        nb_warning=nb_warning,
    )


def _append_history(db: Session, user_id: int, result: HealthScoreResult) -> None:
    """Ajoute le résultat à l'historique (FIFO 16 entrées)."""
    history = get_user_data(db, user_id, _HISTORY_TYPE)
    history.append(result.to_dict())
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    save_user_data(db, user_id, _HISTORY_TYPE, history)


@router.get("/current", summary="Score de santé courant")
def health_score_current(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Calcule et retourne le score de santé depuis les données UserData."""
    result = _compute_from_db(db, current_user.id)
    _append_history(db, current_user.id, result)
    return result.to_dict()


@router.get("/history", summary="Historique du score de santé")
def health_score_history(
    weeks: int = Query(8, ge=1, le=16),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Retourne les N derniers points de l'historique."""
    history = get_user_data(db, current_user.id, _HISTORY_TYPE)
    return history[-weeks:]
