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
    nom: Optional[str] = None
    prenom: Optional[str] = None
    secteur: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    """Corps de la requête PUT /auth/me."""
    nom: Optional[str] = None
    prenom: Optional[str] = None
    secteur: Optional[str] = None


class PasswordChange(BaseModel):
    """Corps de la requête PUT /auth/password."""
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        return v
