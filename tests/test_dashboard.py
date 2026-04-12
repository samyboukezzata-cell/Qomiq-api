"""
Tests d'intégration — /dashboard/summary et /dashboard/kpis.
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


# ── /dashboard/summary ────────────────────────────────────────────────────────

class TestDashboardSummary:
    def test_dashboard_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 401

    def test_dashboard_empty_user(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Utilisateur sans données → has_data=False, pas de crash."""
        resp = client.get("/dashboard/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is False
        assert data["pipeline"]["count"] == 0
        assert data["ca"]["current_month"] == 0.0

    def test_dashboard_with_pipeline(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Avec des deals → KPIs calculés et has_data=True."""
        _inject(user_id, "pipeline", [
            {"nom": "Deal A", "client": "Acme", "montant": 10000,
             "date_cloture": "2030-12-31"},
            {"nom": "Deal B", "client": "Beta", "montant": 5000,
             "date_cloture": "2030-06-30"},
        ])
        resp = client.get("/dashboard/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is True
        assert data["pipeline"]["count"] == 2
        assert data["pipeline"]["total_montant"] == 15000.0
        assert len(data["pipeline"]["top_deals"]) == 2
        # Le deal le plus cher en premier
        assert data["pipeline"]["top_deals"][0]["nom"] == "Deal A"

    def test_dashboard_ca_stats(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """CA renseigné → current_month > 0."""
        _inject(user_id, "ca_mensuel", [
            {"mois": "2026-04", "ca_realise": 42000.0},
            {"mois": "2026-03", "ca_realise": 35000.0},
        ])
        resp = client.get("/dashboard/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ca"]["current_month"] == 42000.0
        assert data["ca"]["previous_month"] == 35000.0
        assert data["ca"]["growth_pct"] is not None

    def test_dashboard_alert_stats(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Deal stale → alerte détectée et comptée dans le dashboard."""
        _inject(user_id, "pipeline", [
            {"nom": "Vieux deal", "client": "X",
             "montant": 1000, "date_modification": "2025-01-01"},
        ])
        resp = client.get("/dashboard/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alerts"]["total_active"] > 0


# ── /dashboard/kpis ───────────────────────────────────────────────────────────

class TestDashboardKpis:
    def test_kpis_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/dashboard/kpis")
        assert resp.status_code == 401

    def test_kpis_empty(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """KPIs vides → has_data=False, pas de crash."""
        resp = client.get("/dashboard/kpis", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is False
        assert "pipeline_count" in data
        assert "health_score" in data

    def test_kpis_with_data(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """KPIs retournent les bonnes valeurs."""
        _inject(user_id, "pipeline", [
            {"nom": "D1", "client": "C1", "montant": 8000, "date_cloture": "2030-01-01"},
        ])
        resp = client.get("/dashboard/kpis", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_count"] == 1
        assert data["pipeline_montant"] == 8000.0
