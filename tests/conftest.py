"""
Fixtures pytest partagées pour qomiq-api.

SQLite in-memory avec StaticPool : toutes les connexions partagent
la même base, garantissant que les tables créées restent visibles.
Les données sont purgées entre chaque test.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from main import app

_TEST_DB_URL = "sqlite:///:memory:"

# StaticPool : une seule connexion partagée → la DB in-memory persiste
# sur toute la durée de la session pytest.
_engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Crée le schéma une fois pour toute la session de tests."""
    from models import user, user_data  # noqa: F401 — enregistre User + UserData dans Base.metadata
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def _clear_tables():
    """Vide toutes les tables avant chaque test (isolation des données)."""
    yield
    db = _TestingSession()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(text(f"DELETE FROM {table.name}"))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client() -> TestClient:
    """Client HTTP avec DB in-memory injectée."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def registered_user(client: TestClient) -> dict:
    """Crée un utilisateur de test et retourne ses credentials."""
    payload = {
        "email": "test@qomiq.io",
        "password": "SecurePass1",
        "full_name": "Test User",
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.json()
    return payload


@pytest.fixture()
def auth_token(client: TestClient, registered_user: dict) -> str:
    """Retourne un JWT valide pour l'utilisateur de test."""
    resp = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


@pytest.fixture()
def auth_headers(auth_token: str) -> dict:
    """Headers Authorization prêts à l'emploi."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture()
def user_id(client: TestClient, registered_user: dict) -> int:
    """Retourne l'id de l'utilisateur de test."""
    token = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    }).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me.json()["id"]
