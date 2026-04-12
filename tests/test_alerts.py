"""
Tests d'intégration — /alerts/.
"""
import pytest
from fastapi.testclient import TestClient

from models.user_data import save_user_data
from tests.conftest import _TestingSession


# ── Helpers ───────────────────────────────────────────────────────────────────

def _inject(user_id: int, data_type: str, rows: list) -> None:
    db = _TestingSession()
    try:
        save_user_data(db, user_id, data_type, rows)
    finally:
        db.close()


# ── GET /alerts/ ──────────────────────────────────────────────────────────────

class TestListAlerts:
    def test_alerts_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/alerts/")
        assert resp.status_code == 401

    def test_alerts_empty(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Aucune donnée → liste vide, pas de crash."""
        resp = client.get("/alerts/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_alerts_with_stale_deal(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Deal inactif depuis > 30j → alerte DEAL_STALE CRITICAL présente."""
        _inject(user_id, "pipeline", [
            {"nom": "Vieux deal", "client": "X",
             "montant": 5000, "date_modification": "2025-01-01"},
        ])
        resp = client.get("/alerts/", headers=auth_headers)
        assert resp.status_code == 200
        alerts = resp.json()
        assert len(alerts) > 0
        types = [a["alert_type"] for a in alerts]
        assert "deal_stale" in types

    def test_alerts_filter_critical(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Filtre level=critical → uniquement les alertes critiques."""
        _inject(user_id, "pipeline", [
            {"nom": "Vieux deal", "client": "X",
             "montant": 5000, "date_modification": "2025-01-01"},
        ])
        resp = client.get("/alerts/?level=critical", headers=auth_headers)
        assert resp.status_code == 200
        alerts = resp.json()
        for a in alerts:
            assert a["level"] == "critical"

    def test_alerts_filter_warning(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Filtre level=warning → uniquement les alertes warning."""
        # Deal stale entre 14 et 30 jours → WARNING
        _inject(user_id, "pipeline", [
            {"nom": "Deal semi-stale", "client": "Y",
             "montant": 3000, "date_modification": "2026-03-20"},
        ])
        resp = client.get("/alerts/?level=warning", headers=auth_headers)
        assert resp.status_code == 200
        for a in resp.json():
            assert a["level"] == "warning"

    def test_alerts_unread_only(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """unread_only=true → exclut les alertes déjà lues."""
        _inject(user_id, "pipeline", [
            {"nom": "Vieux deal", "client": "X",
             "montant": 5000, "date_modification": "2025-01-01"},
        ])
        # Premier appel pour générer les alertes
        resp = client.get("/alerts/", headers=auth_headers)
        alerts = resp.json()
        assert len(alerts) > 0

        # Marquer la première comme lue
        alert_id = alerts[0]["id"]
        client.patch(f"/alerts/{alert_id}/read", headers=auth_headers)

        # unread_only=true → la lue n'apparaît plus
        resp2 = client.get("/alerts/?unread_only=true", headers=auth_headers)
        ids = [a["id"] for a in resp2.json()]
        assert alert_id not in ids


# ── PATCH /alerts/{id}/read ───────────────────────────────────────────────────

class TestMarkRead:
    def test_mark_read_success(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Marquer une alerte existante comme lue → 200."""
        _inject(user_id, "pipeline", [
            {"nom": "Vieux deal", "client": "X",
             "montant": 5000, "date_modification": "2025-01-01"},
        ])
        alerts = client.get("/alerts/", headers=auth_headers).json()
        assert len(alerts) > 0

        alert_id = alerts[0]["id"]
        resp = client.patch(f"/alerts/{alert_id}/read", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_mark_read_not_found(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """ID inexistant → 404."""
        resp = client.patch("/alerts/fake_id/read", headers=auth_headers)
        assert resp.status_code == 404


# ── POST /alerts/refresh ──────────────────────────────────────────────────────

class TestRefreshAlerts:
    def test_refresh_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/alerts/refresh")
        assert resp.status_code == 401

    def test_refresh_returns_count(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Refresh renvoie les compteurs."""
        _inject(user_id, "pipeline", [
            {"nom": "Vieux deal", "client": "X",
             "montant": 5000, "date_modification": "2025-01-01"},
        ])
        resp = client.post("/alerts/refresh", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "critical" in data
        assert "warning" in data
        assert data["count"] > 0
