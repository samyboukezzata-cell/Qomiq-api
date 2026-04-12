"""
Qomiq API — Schémas Pydantic (validation requêtes + réponses).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Corps de la requête POST /auth/register."""
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
        return v


class UserLogin(BaseModel):
    """Corps de la requête POST /auth/login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Réponse du endpoint /auth/login."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Payload interne du JWT (non exposé en API)."""
    email: Optional[str] = None


# ── User response ─────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Réponse sérialisée d'un utilisateur (sans mot de passe)."""
    id: int
    email: str
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}
