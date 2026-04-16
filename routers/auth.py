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
from models.schemas import (
    Token, UserCreate, UserLogin, UserResponse,
    ProfileUpdate, PasswordChange, HasData, UserMeResponse,
)
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
    response_model=UserMeResponse,
    summary="Profil de l'utilisateur connecté",
)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserMeResponse:
    from models.user_data import get_user_data
    pipeline_rows  = get_user_data(db, current_user.id, "pipeline")
    ca_rows        = get_user_data(db, current_user.id, "ca_mensuel")
    coach_history  = get_user_data(db, current_user.id, "coach_history")
    has_data = HasData(
        pipeline=len(pipeline_rows) > 0,
        ca_mensuel=len(ca_rows) > 0,
        has_generated_analysis=len(coach_history) > 0,
    )
    return UserMeResponse.model_validate(
        {**current_user.__dict__, "has_data": has_data}
    )


@router.post(
    "/complete-onboarding",
    response_model=UserResponse,
    summary="Marquer l'onboarding comme terminé",
)
def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    current_user.onboarding_completed = True
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post(
    "/reset-onboarding",
    response_model=UserResponse,
    summary="Réinitialiser l'onboarding (relancer le guide)",
)
def reset_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    current_user.onboarding_completed = False
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Mettre à jour le profil",
)
def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if body.nom is not None:
        current_user.nom = body.nom
    if body.prenom is not None:
        current_user.prenom = body.prenom
    if body.secteur is not None:
        current_user.secteur = body.secteur
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put(
    "/password",
    summary="Changer le mot de passe",
)
def change_password(
    body: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect.",
        )
    if body.new_password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Les mots de passe ne correspondent pas.",
        )
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Mot de passe mis à jour"}
