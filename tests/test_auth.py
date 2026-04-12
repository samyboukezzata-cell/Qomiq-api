"""
Tests d'intégration — /auth/register, /auth/login, /auth/me.

Base de données : SQLite en mémoire (via conftest.py).
"""
import pytest
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════════════════════
# POST /auth/register
# ══════════════════════════════════════════════════════════════════════════════

class TestRegister:
    def test_register_success(self, client: TestClient) -> None:
        """Inscription valide → 201 + données utilisateur."""
        resp = client.post("/auth/register", json={
            "email": "alice@qomiq.io",
            "password": "StrongPass1",
            "full_name": "Alice Martin",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alice@qomiq.io"
        assert data["full_name"] == "Alice Martin"
        assert data["is_active"] is True
        assert data["is_admin"] is False
        assert "id" in data
        assert "created_at" in data
        # Le mot de passe ne doit jamais apparaître dans la réponse
        assert "password" not in data
        assert "hashed_password" not in data

    def test_register_duplicate_email(self, client: TestClient) -> None:
        """Email déjà utilisé → 409."""
        payload = {"email": "bob@qomiq.io", "password": "StrongPass1"}
        client.post("/auth/register", json=payload)
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 409

    def test_register_invalid_email(self, client: TestClient) -> None:
        """Email invalide → 422."""
        resp = client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "StrongPass1",
        })
        assert resp.status_code == 422

    def test_register_password_too_short(self, client: TestClient) -> None:
        """Mot de passe < 8 caractères → 422."""
        resp = client.post("/auth/register", json={
            "email": "short@qomiq.io",
            "password": "abc",
        })
        assert resp.status_code == 422

    def test_register_without_full_name(self, client: TestClient) -> None:
        """full_name optionnel → 201."""
        resp = client.post("/auth/register", json={
            "email": "noname@qomiq.io",
            "password": "StrongPass1",
        })
        assert resp.status_code == 201
        assert resp.json()["full_name"] is None


# ══════════════════════════════════════════════════════════════════════════════
# POST /auth/login
# ══════════════════════════════════════════════════════════════════════════════

class TestLogin:
    def test_login_success(self, client: TestClient, registered_user: dict) -> None:
        """Credentials corrects → 200 + token bearer."""
        resp = client.post("/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_login_wrong_password(self, client: TestClient, registered_user: dict) -> None:
        """Mauvais mot de passe → 401."""
        resp = client.post("/auth/login", json={
            "email": registered_user["email"],
            "password": "wrong-password",
        })
        assert resp.status_code == 401

    def test_login_unknown_email(self, client: TestClient) -> None:
        """Email inconnu → 401."""
        resp = client.post("/auth/login", json={
            "email": "ghost@qomiq.io",
            "password": "StrongPass1",
        })
        assert resp.status_code == 401

    def test_login_invalid_email_format(self, client: TestClient) -> None:
        """Email malformé → 422."""
        resp = client.post("/auth/login", json={
            "email": "not-valid",
            "password": "StrongPass1",
        })
        assert resp.status_code == 422

    def test_login_missing_fields(self, client: TestClient) -> None:
        """Corps vide → 422."""
        resp = client.post("/auth/login", json={})
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# GET /auth/me
# ══════════════════════════════════════════════════════════════════════════════

class TestMe:
    def test_me_authenticated(
        self, client: TestClient, registered_user: dict, auth_token: str
    ) -> None:
        """Token valide → 200 + profil utilisateur."""
        resp = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == registered_user["email"]
        assert data["full_name"] == registered_user.get("full_name")
        assert "hashed_password" not in data

    def test_me_no_token(self, client: TestClient) -> None:
        """Pas de token → 401 (HTTPBearer renvoie 401 si absent)."""
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client: TestClient) -> None:
        """Token invalide → 401."""
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401

    def test_me_malformed_bearer(self, client: TestClient) -> None:
        """Header mal formé → 401."""
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "notbearer token"},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Utilitaires de sécurité
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurity:
    def test_password_not_stored_plaintext(self, client: TestClient) -> None:
        """Le mot de passe en base ne correspond pas au clair (bcrypt)."""
        from sqlalchemy.orm import Session
        from tests.conftest import _TestingSession
        from models.user import User

        email = "hash_check@qomiq.io"
        client.post("/auth/register", json={"email": email, "password": "MySecret1"})

        db: Session = _TestingSession()
        user = db.query(User).filter(User.email == email).first()
        db.close()

        assert user is not None
        assert user.hashed_password != "MySecret1"
        assert user.hashed_password.startswith("$2b$")

    def test_token_decode_returns_email(self) -> None:
        """create_access_token + decode_access_token sont inverses."""
        from core.security import create_access_token, decode_access_token
        token = create_access_token("user@qomiq.io")
        assert decode_access_token(token) == "user@qomiq.io"

    def test_expired_token_returns_none(self) -> None:
        """Un token expiré est rejeté."""
        from datetime import timedelta
        from core.security import create_access_token, decode_access_token
        token = create_access_token("x@qomiq.io", expires_delta=timedelta(seconds=-1))
        assert decode_access_token(token) is None


# ══════════════════════════════════════════════════════════════════════════════
# Health checks
# ══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_root(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
