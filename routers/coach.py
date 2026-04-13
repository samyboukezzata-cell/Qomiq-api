"""
Qomiq API — Router Coach IA.

Endpoints :
  POST /coach/analyze  — analyse structurée (PESTEL / BCG / Ansoff / Porter)
  POST /coach/chat     — conversation libre avec contexte
  GET  /coach/history  — 10 dernières analyses
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models.user import User
from models.user_data import get_user_data, save_user_data
from routers.auth import get_current_user
from services.coach.prompt_builder import (
    SYSTEM_PROMPT,
    build_context,
    prompt_ansoff,
    prompt_bcg,
    prompt_chat,
    prompt_pestel,
    prompt_porter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coach", tags=["coach"])

_HISTORY_TYPE = "coach_history"
_MAX_HISTORY  = 10
_MODEL        = "claude-3-5-haiku-20241022"
_MAX_TOKENS   = 2048

AnalysisType = Literal["pestel", "bcg", "ansoff", "porter"]

_PROMPT_MAP = {
    "pestel": prompt_pestel,
    "bcg":    prompt_bcg,
    "ansoff": prompt_ansoff,
    "porter": prompt_porter,
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    analysis_type: AnalysisType


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ── Helper : client Anthropic ─────────────────────────────────────────────────

def _get_client():
    """Retourne un client Anthropic. Lève 500 si la clé est absente."""
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ANTHROPIC_API_KEY non configurée. "
                   "Ajoutez la variable d'environnement dans Render.",
        )
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bibliothèque 'anthropic' non installée.",
        )


def _load_context(db: Session, user_id: int) -> str:
    pipeline = get_user_data(db, user_id, "pipeline")
    ca_rows  = get_user_data(db, user_id, "ca_mensuel")
    budget   = get_user_data(db, user_id, "budget")
    produits = get_user_data(db, user_id, "produits")

    # Score de santé depuis l'historique (dernier point)
    health_hist = get_user_data(db, user_id, "health_history")
    health_score = health_hist[-1].get("score") if health_hist else None

    return build_context(pipeline, ca_rows, budget, produits, health_score)


# ── POST /coach/analyze ───────────────────────────────────────────────────────

@router.post("/analyze", summary="Analyse IA structurée")
def coach_analyze(
    body: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Génère une analyse structurée (PESTEL / BCG / Ansoff / Porter)
    à partir des données UserData de l'utilisateur.
    """
    client  = _get_client()
    context = _load_context(db, current_user.id)

    build_prompt = _PROMPT_MAP[body.analysis_type]
    user_prompt  = build_prompt(context)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = response.content[0].text
    except Exception as exc:
        logger.exception("Erreur appel Anthropic /analyze")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erreur API Anthropic : {exc}",
        )

    # Persistance dans l'historique
    history = get_user_data(db, current_user.id, _HISTORY_TYPE)
    from datetime import date
    history.append({
        "type":       body.analysis_type,
        "content":    content,
        "created_at": date.today().isoformat(),
    })
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    save_user_data(db, current_user.id, _HISTORY_TYPE, history)

    return {
        "analysis_type": body.analysis_type,
        "content":       content,
        "model":         _MODEL,
    }


# ── POST /coach/chat ──────────────────────────────────────────────────────────

@router.post("/chat", summary="Chat libre avec le Coach IA")
def coach_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Conversation libre avec le Coach IA.
    Le contexte des données utilisateur est injecté automatiquement.
    """
    client  = _get_client()
    context = _load_context(db, current_user.id)

    history = [{"role": m.role, "content": m.content} for m in body.history]
    messages = prompt_chat(context, body.message, history)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = response.content[0].text
    except Exception as exc:
        logger.exception("Erreur appel Anthropic /chat")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erreur API Anthropic : {exc}",
        )

    return {"role": "assistant", "content": reply, "model": _MODEL}


# ── GET /coach/history ────────────────────────────────────────────────────────

@router.get("/history", summary="Historique des analyses IA")
def coach_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Retourne les 10 dernières analyses générées pour cet utilisateur."""
    history = get_user_data(db, current_user.id, _HISTORY_TYPE)
    return list(reversed(history))
