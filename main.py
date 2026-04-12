"""
Qomiq API — Point d'entrée FastAPI.

Lancer en dev :
    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import create_tables
from routers import auth, dashboard, alerts, health, import_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crée les tables au démarrage (idempotent)."""
    create_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend SaaS pour Qomiq — Commercial Intelligence & EPM",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# En production, restreindre origins aux domaines Qomiq
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(health.router)
app.include_router(import_data.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
