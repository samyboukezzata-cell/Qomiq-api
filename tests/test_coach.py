"""
Tests — /coach/ (analyze, chat, history).

Les appels Groq sont mockés : aucun vrai appel API.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_groq_response(text: str = "## Analyse\nContenu de l'analyse mock."):
    """Retourne un mock qui imite groq.Groq().chat.completions.create()."""
    message = MagicMock()
    message.content = text

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]

    client_mock = MagicMock()
    client_mock.chat.completions.create.return_value = response

    return client_mock


# ── /coach/analyze ────────────────────────────────────────────────────────────

class TestCoachAnalyze:
    def test_analyze_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        resp = client.post("/coach/analyze", json={"analysis_type": "pestel"})
        assert resp.status_code == 401

    def test_analyze_without_api_key(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Clé Groq absente → 500 avec message explicite."""
        with patch("routers.coach.settings") as mock_settings:
            mock_settings.GROQ_API_KEY = ""
            resp = client.post(
                "/coach/analyze",
                headers=auth_headers,
                json={"analysis_type": "pestel"},
            )
        assert resp.status_code == 500
        assert "GROQ_API_KEY" in resp.json()["detail"]

    def test_analyze_pestel_structure(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Analyse PESTEL → 200 avec content et analysis_type."""
        groq_mock = _mock_groq_response("## PESTEL\n### Politique\nTest.")
        with patch("routers.coach._get_client", return_value=groq_mock):
            resp = client.post(
                "/coach/analyze",
                headers=auth_headers,
                json={"analysis_type": "pestel"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["analysis_type"] == "pestel"
        assert "content" in data
        assert len(data["content"]) > 0

    def test_analyze_all_types(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Les 4 types d'analyse répondent 200."""
        for atype in ("pestel", "bcg", "ansoff", "porter"):
            groq_mock = _mock_groq_response(f"## {atype.upper()}\nMock.")
            with patch("routers.coach._get_client", return_value=groq_mock):
                resp = client.post(
                    "/coach/analyze",
                    headers=auth_headers,
                    json={"analysis_type": atype},
                )
            assert resp.status_code == 200, f"Échec pour type={atype}"
            assert resp.json()["analysis_type"] == atype

    def test_analyze_invalid_type(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Type invalide → 422."""
        resp = client.post(
            "/coach/analyze",
            headers=auth_headers,
            json={"analysis_type": "swot"},
        )
        assert resp.status_code == 422

    def test_analyze_stores_history(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Après analyze → history contient l'entrée."""
        groq_mock = _mock_groq_response("## BCG\nMock analyse.")
        with patch("routers.coach._get_client", return_value=groq_mock):
            client.post(
                "/coach/analyze",
                headers=auth_headers,
                json={"analysis_type": "bcg"},
            )

        resp = client.get("/coach/history", headers=auth_headers)
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) >= 1
        assert history[0]["type"] == "bcg"


# ── /coach/chat ───────────────────────────────────────────────────────────────

class TestCoachChat:
    def test_chat_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        resp = client.post("/coach/chat", json={"message": "Bonjour"})
        assert resp.status_code == 401

    def test_chat_basic(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Message simple → 200 avec role assistant et content."""
        groq_mock = _mock_groq_response("Bonjour ! Comment puis-je vous aider ?")
        with patch("routers.coach._get_client", return_value=groq_mock):
            resp = client.post(
                "/coach/chat",
                headers=auth_headers,
                json={"message": "Bonjour", "history": []},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert len(data["content"]) > 0

    def test_chat_with_history(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Chat avec historique → passe les messages précédents à l'API."""
        groq_mock = _mock_groq_response("Suite de la conversation.")
        with patch("routers.coach._get_client", return_value=groq_mock):
            resp = client.post(
                "/coach/chat",
                headers=auth_headers,
                json={
                    "message": "Et le pipeline ?",
                    "history": [
                        {"role": "user",      "content": "Comment ça va ?"},
                        {"role": "assistant", "content": "Très bien, merci !"},
                    ],
                },
            )
        assert resp.status_code == 200
        # Vérifier que l'historique a bien été transmis à Groq
        call_args = groq_mock.chat.completions.create.call_args
        messages_sent = call_args.kwargs.get("messages", [])
        # system + 2 historique + nouveau message = 4 minimum
        assert len(messages_sent) >= 4


# ── /coach/history ────────────────────────────────────────────────────────────

class TestCoachHistory:
    def test_history_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        resp = client.get("/coach/history")
        assert resp.status_code == 401

    def test_history_empty(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Sans analyses → liste vide."""
        resp = client.get("/coach/history", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_max_10(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """L'historique est limité à 10 entrées (FIFO)."""
        groq_mock = _mock_groq_response("Mock.")
        with patch("routers.coach._get_client", return_value=groq_mock):
            for _ in range(12):
                client.post(
                    "/coach/analyze",
                    headers=auth_headers,
                    json={"analysis_type": "pestel"},
                )

        resp = client.get("/coach/history", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 10
