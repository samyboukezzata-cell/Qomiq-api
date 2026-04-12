"""
Qomiq API — Modèle SQLAlchemy UserData.

Stocke toutes les données métier d'un utilisateur sous forme JSON.
data_type identifie le type de jeu de données :
  "pipeline" | "ca_mensuel" | "produits" | "budget" | "contacts"
  | "alerts_state" | "health_history"
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class UserData(Base):
    __tablename__ = "user_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_user_data(db, user_id: int, data_type: str) -> list[dict]:
    """Retourne la liste de dicts pour (user_id, data_type). [] si absent."""
    row = (
        db.query(UserData)
        .filter(UserData.user_id == user_id, UserData.data_type == data_type)
        .first()
    )
    if row is None:
        return []
    return row.data or []


def save_user_data(
    db,
    user_id: int,
    data_type: str,
    rows: list[dict],
    merge: str = "replace",
) -> UserData:
    """
    Persiste rows dans UserData(user_id, data_type).

    merge="replace" : remplace complètement (défaut).
    merge="upsert"  : identique à replace pour l'instant
                      (extensible pour un merge clé-par-clé).
    """
    row = (
        db.query(UserData)
        .filter(UserData.user_id == user_id, UserData.data_type == data_type)
        .first()
    )
    if row is None:
        row = UserData(user_id=user_id, data_type=data_type, data=rows)
        db.add(row)
    else:
        row.data = rows
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
