"""
Qomiq API — Router authentification.

Endpoints :
  POST /auth/register  → crée un compte
  POST /auth/login     → retourne un JWT
  GET  /auth/me        → profil de l'utilisateur connecté
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import create_access_token, decode_access_token, hash_password, verify_password
from models.schemas import Token, UserCreate, UserLogin, UserResponse
from models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def _get_current_user(
    token: str,
    db: Session,
) -> User:
    """Valide le JWT et retourne l'utilisateur correspondant."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou token expiré.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    email = decode_access_token(token)
    if not email:
        raise credentials_exc
    user = _get_user_by_email(db, email)
    if not user or not user.is_active:
        raise credentials_exc
    return user


# ── Dépendance Bearer token ───────────────────────────────────────────────────

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    return _get_current_user(credentials.credentials, db)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouveau compte",
)
def register(body: UserCreate, db: Session = Depends(get_db)) -> User:
    if _get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte avec cet email existe déjà.",
        )
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Obtenir un token JWT",
)
def login(body: UserLogin, db: Session = Depends(get_db)) -> dict:
    user = _get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé.",
        )
    token = create_access_token(subject=user.email)
    return {"access_token": token, "token_type": "bearer"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Profil de l'utilisateur connecté",
)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
