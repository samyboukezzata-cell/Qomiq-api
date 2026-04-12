"""
Qomiq API — Engine SQLAlchemy et session factory.

SQLite en développement/tests, PostgreSQL en production (via DATABASE_URL).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# Fix Render.com : DATABASE_URL commence par "postgres://" mais SQLAlchemy
# requiert "postgresql://".
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

# connect_args requis uniquement pour SQLite (threads multiples)
_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}

engine = create_engine(_db_url, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy."""
    pass


def get_db():
    """Dépendance FastAPI — fournit une session DB et la ferme après usage."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Crée toutes les tables en base (idempotent)."""
    from models import user, user_data  # noqa: F401 — enregistre tous les modèles
    Base.metadata.create_all(bind=engine)
