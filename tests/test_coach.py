"""
Tests — /coach/ (analyze, chat, history).

Les appels Anthropic sont mockés : aucun vrai appel API.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_anthropic_response(text: str = "## Analyse\nContenu de l'analyse mock."):
    """Retourne un mock qui imite anthropic.Anthropic().messages.create()."""
    content_block = MagicMock()
    content_block.text = text

    message = MagicMock()
    message.content = [content_block]

    client_mock = MagicMock()
    client_mock.messages.create.return_value = message

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
        """Clé Anthropic absente → 500 avec message explicite."""
        with patch("core.config.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = ""
            resp = client.post(
                "/coach/analyze",
                headers=auth_headers,
                json={"analysis_type": "pestel"},
            )
        assert resp.status_code == 500
        assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    def test_analyze_pestel_structure(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Analyse PESTEL → 200 avec content et analysis_type."""
        anthropic_mock = _mock_anthropic_response("## PESTEL\n### Politique\nTest.")
        with patch("routers.coach.settings") as mock_settings, \
             patch("routers.coach._get_client", return_value=anthropic_mock):
            mock_settings.ANTHROPIC_API_KEY = "sk-ant-test"
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
            anthropic_mock = _mock_anthropic_response(f"## {atype.upper()}\nMock.")
            with patch("routers.coach._get_client", return_value=anthropic_mock):
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
        anthropic_mock = _mock_anthropic_response("## BCG\nMock analyse.")
        with patch("routers.coach._get_client", return_value=anthropic_mock):
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
        anthropic_mock = _mock_anthropic_response("Bonjour ! Comment puis-je vous aider ?")
        with patch("routers.coach._get_client", return_value=anthropic_mock):
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
        anthropic_mock = _mock_anthropic_response("Suite de la conversation.")
        with patch("routers.coach._get_client", return_value=anthropic_mock):
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
        # Vérifier que l'historique a bien été passé
        call_args = anthropic_mock.messages.create.call_args
        messages_sent = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else []
        if call_args.kwargs:
            messages_sent = call_args.kwargs.get("messages", [])
        assert len(messages_sent) >= 3  # historique + nouveau message


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
        anthropic_mock = _mock_anthropic_response("Mock.")
        with patch("routers.coach._get_client", return_value=anthropic_mock):
            for _ in range(12):
                client.post(
                    "/coach/analyze",
                    headers=auth_headers,
                    json={"analysis_type": "pestel"},
                )

        resp = client.get("/coach/history", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 10
