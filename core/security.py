"""
Qomiq API — Utilitaires de sécurité : hachage bcrypt + JWT.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from .config import settings


# ── Mots de passe ─────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hache un mot de passe en clair avec bcrypt."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Génère un JWT signé HS256.

    Args:
        subject:       Identifiant unique (email ou user_id en str).
        expires_delta: Durée de validité (défaut : ACCESS_TOKEN_EXPIRE_MINUTES).

    Returns:
        Token JWT encodé.
    """
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + delta
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """
    Décode un JWT et retourne le subject (email).

    Returns:
        Subject (email) si valide, None sinon.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload.get("sub")
    except JWTError:
        return None
