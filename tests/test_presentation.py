"""
Tests — /presentation/ (data, export-pdf).

Les tests vérifient l'authentification, la structure de la réponse,
et la génération PDF sans erreur.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── /presentation/data ───────────────────────────────────────────────────────

class TestPresentationData:
    def test_data_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        resp = client.get("/presentation/data")
        assert resp.status_code == 401

    def test_data_empty(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Sans données importées → réponse 200 avec structure complète."""
        resp = client.get("/presentation/data", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Champs obligatoires
        assert "generated_at" in data
        assert "period" in data
        assert "user_name" in data
        assert "kpis" in data
        assert "ca_history" in data
        assert "top_deals" in data
        assert "health_score" in data
        assert "alerts" in data
        assert "last_analysis" in data

    def test_data_kpis_structure(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Les KPIs ont les sous-champs attendus."""
        resp = client.get("/presentation/data", headers=auth_headers)
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        for key in (
            "ca_mois_courant", "ca_mois_precedent", "ca_growth_pct",
            "pipeline_total", "pipeline_count", "pipeline_closing_soon",
            "budget_consomme_pct", "budget_lignes_over",
        ):
            assert key in kpis, f"Clé manquante dans kpis: {key}"

    def test_data_with_pipeline(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Avec des deals → top_deals est limité à 5 et trié par montant desc."""
        # Importer 6 deals avec montants différents
        deals = [
            {"nom": f"Deal {i}", "client": f"Client {i}",
             "montant": str(i * 1000), "statut": "en_cours",
             "date_cloture": "2026-06-30"}
            for i in range(1, 7)
        ]
        client.post(
            "/import/data",
            headers=auth_headers,
            json={"data_type": "pipeline", "rows": deals},
        )
        resp = client.get("/presentation/data", headers=auth_headers)
        assert resp.status_code == 200
        top_deals = resp.json()["top_deals"]
        assert len(top_deals) <= 5
        # Vérifie tri décroissant
        montants = [float(d.get("montant", 0)) for d in top_deals]
        assert montants == sorted(montants, reverse=True)

    def test_data_user_name(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """user_name doit correspondre à l'utilisateur connecté."""
        resp = client.get("/presentation/data", headers=auth_headers)
        assert resp.status_code == 200
        user_name = resp.json()["user_name"]
        # L'utilisateur de test a full_name "Test User"
        assert user_name in ("Test User", "test@qomiq.io")


# ── /presentation/export-pdf ─────────────────────────────────────────────────

class TestExportPdf:
    def _get_data_payload(self, client: TestClient, auth_headers: dict) -> dict:
        resp = client.get("/presentation/data", headers=auth_headers)
        assert resp.status_code == 200
        return resp.json()

    def test_export_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        resp = client.post("/presentation/export-pdf", json={
            "generated_at": "2026-04-12",
            "period": "Avril 2026",
            "user_name": "Test",
            "kpis": {},
            "ca_history": [],
            "top_deals": [],
            "health_score": {},
            "alerts": [],
        })
        assert resp.status_code == 401

    def test_export_pdf_empty_data(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Données vides → génère un PDF sans erreur (content-type pdf)."""
        payload = self._get_data_payload(client, auth_headers)
        resp = client.post(
            "/presentation/export-pdf",
            headers=auth_headers,
            json=payload,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        # Un PDF commence toujours par %PDF-
        assert resp.content[:5] == b"%PDF-"

    def test_export_pdf_with_data(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Données réelles → PDF généré et non vide."""
        # Importer quelques données
        client.post("/import/data", headers=auth_headers, json={
            "data_type": "pipeline",
            "rows": [
                {"nom": "Deal A", "client": "Acme", "montant": "50000",
                 "statut": "en_cours", "date_cloture": "2026-05-01"},
            ],
        })
        client.post("/import/data", headers=auth_headers, json={
            "data_type": "ca_mensuel",
            "rows": [
                {"mois": 4, "annee": 2026, "ca_realise": 120000, "ca_objectif": 100000},
            ],
        })
        payload = self._get_data_payload(client, auth_headers)
        resp = client.post(
            "/presentation/export-pdf",
            headers=auth_headers,
            json=payload,
        )
        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"
        # PDF doit être > 1 Ko
        assert len(resp.content) > 1024

    def test_export_pdf_filename_header(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Content-Disposition doit contenir le nom du fichier."""
        payload = self._get_data_payload(client, auth_headers)
        resp = client.post(
            "/presentation/export-pdf",
            headers=auth_headers,
            json=payload,
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "rapport-qomiq-" in cd
        assert ".pdf" in cd

    def test_export_pdf_with_last_analysis(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Avec last_analysis → le PDF est généré sans erreur."""
        payload = self._get_data_payload(client, auth_headers)
        payload["last_analysis"] = (
            "## Analyse PESTEL\n\n"
            "### Politique\nFacteurs politiques stables.\n\n"
            "### Économique\nCroissance positive."
        )
        resp = client.post(
            "/presentation/export-pdf",
            headers=auth_headers,
            json=payload,
        )
        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"
