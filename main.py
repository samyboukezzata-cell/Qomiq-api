"""
Qomiq API — Point d'entrée FastAPI.

Lancer en dev :
    uvicorn main:app --reload
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import Base, engine
from routers import auth
from routers import dashboard
from routers import alerts
from routers import health as health_router
from routers import import_data
from routers import coach
from routers import presentation
from routers import pipeline

logger = logging.getLogger(__name__)

# ── Vérification des variables d'environnement ────────────────────────────────

if not os.getenv("DATABASE_URL"):
    logger.warning("DATABASE_URL not set — using SQLite fallback")

if settings.SECRET_KEY == "change-me-in-production" and settings.ENVIRONMENT == "production":
    logger.warning("SECRET_KEY is using default value in production — this is insecure")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crée les tables au démarrage et applique les migrations colonnes."""
    try:
        from models import user, user_data  # noqa: F401 — enregistre les modèles
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Database error at startup: {e}")
        raise

    # ── Migration colonnes users (idempotent via IF NOT EXISTS) ───────────────
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS nom VARCHAR,
                ADD COLUMN IF NOT EXISTS prenom VARCHAR,
                ADD COLUMN IF NOT EXISTS secteur VARCHAR,
                ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;
            """))
            conn.commit()
        print("Migration colonnes users OK")
    except Exception as e:
        # Non-bloquant : SQLite (dev/tests) ne supporte pas IF NOT EXISTS
        print(f"Migration warning (ignoré en dev/test): {e}")

    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend SaaS pour Qomiq — Commercial Intelligence & EPM",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(health_router.router)
app.include_router(import_data.router)
app.include_router(coach.router)
app.include_router(presentation.router)
app.include_router(pipeline.router)


# ── Health checks ─────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health", tags=["health"])
def healthcheck() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION}
