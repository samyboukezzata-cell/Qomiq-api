"""
Tests d'intégration — /health-score/.
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


# ── GET /health-score/current ─────────────────────────────────────────────────

class TestHealthScoreCurrent:
    def test_health_score_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/health-score/current")
        assert resp.status_code == 401

    def test_health_score_empty(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Utilisateur sans données → score neutre, pas de crash."""
        resp = client.get("/health-score/current", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert 0 <= data["score"] <= 100
        assert "label" in data
        assert "color" in data
        assert "computed_at" in data

    def test_health_score_with_data(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Avec pipeline et CA renseignés → score calculé (> neutre)."""
        _inject(user_id, "pipeline", [
            {"nom": "Deal A", "client": "Acme", "montant": 15000,
             "date_cloture": "2030-12-31", "date_modification": "2026-04-10"},
            {"nom": "Deal B", "client": "Beta", "montant": 8000,
             "date_cloture": "2030-06-30", "date_modification": "2026-04-09"},
        ])
        _inject(user_id, "ca_mensuel", [
            {"mois": "2026-04", "ca_realise": 50000.0, "objectif": 45000.0},
        ])
        resp = client.get("/health-score/current", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] > 0
        assert data["component_pipeline"] > 0
        assert data["component_ca"] > 0

    def test_health_score_structure(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """La réponse contient toutes les composantes attendues."""
        resp = client.get("/health-score/current", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = [
            "score", "label", "color",
            "component_ca", "component_pipeline", "component_win_rate",
            "component_activite", "component_alertes",
            "computed_at",
        ]
        for key in expected_keys:
            assert key in data, f"Clé manquante : {key}"

    def test_health_score_appends_history(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Chaque appel à /current ajoute une entrée dans l'historique."""
        client.get("/health-score/current", headers=auth_headers)
        client.get("/health-score/current", headers=auth_headers)

        hist = client.get("/health-score/history", headers=auth_headers).json()
        assert len(hist) >= 2


# ── GET /health-score/history ─────────────────────────────────────────────────

class TestHealthScoreHistory:
    def test_history_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/health-score/history")
        assert resp.status_code == 401

    def test_history_empty(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Sans appel à /current → historique vide."""
        resp = client.get("/health-score/history", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_weeks_param(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Paramètre weeks limite les résultats."""
        # Générer 5 entrées
        for _ in range(5):
            client.get("/health-score/current", headers=auth_headers)

        resp = client.get("/health-score/history?weeks=3", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 3

    def test_history_invalid_weeks(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """weeks=0 → 422 (ge=1)."""
        resp = client.get("/health-score/history?weeks=0", headers=auth_headers)
        assert resp.status_code == 422
