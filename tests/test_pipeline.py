"""
Tests — /pipeline/ (CRUD + stats + filtres).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Fixtures helpers ──────────────────────────────────────────────────────────

def _deal(
    nom="Deal Alpha", client="Acme", montant=10000,
    etape="Prospect", commercial=None, **kwargs
) -> dict:
    return {"nom": nom, "client": client, "montant": montant,
            "etape": etape, "commercial": commercial, **kwargs}


def _create(client_http: TestClient, headers: dict, **kwargs) -> dict:
    resp = client_http.post("/pipeline/", headers=headers, json=_deal(**kwargs))
    assert resp.status_code == 201, resp.json()
    return resp.json()


# ── GET /pipeline/ ────────────────────────────────────────────────────────────

class TestListDeals:
    def test_list_empty(self, client: TestClient, auth_headers: dict) -> None:
        """Aucun deal → liste vide."""
        resp = client.get("/pipeline/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        assert client.get("/pipeline/").status_code == 401

    def test_list_returns_created_deals(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Les deals créés apparaissent dans la liste."""
        _create(client, auth_headers, nom="Deal 1")
        _create(client, auth_headers, nom="Deal 2")
        resp = client.get("/pipeline/", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_filter_by_etape(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Filtre par étape."""
        _create(client, auth_headers, nom="D1", etape="Prospect")
        _create(client, auth_headers, nom="D2", etape="Gagné")
        resp = client.get("/pipeline/?etape=Gagné", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["nom"] == "D2"

    def test_list_filter_by_commercial(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Filtre par commercial."""
        _create(client, auth_headers, nom="D1", commercial="Alice")
        _create(client, auth_headers, nom="D2", commercial="Bob")
        resp = client.get("/pipeline/?commercial=Alice", headers=auth_headers)
        assert resp.status_code == 200
        names = [d["nom"] for d in resp.json()]
        assert "D1" in names
        assert "D2" not in names

    def test_list_search(self, client: TestClient, auth_headers: dict) -> None:
        """Recherche par nom ou client."""
        _create(client, auth_headers, nom="Alpha Project", client="Acme Corp")
        _create(client, auth_headers, nom="Beta Deal", client="TechCo")
        resp = client.get("/pipeline/?search=acme", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["nom"] == "Alpha Project"


# ── POST /pipeline/ ───────────────────────────────────────────────────────────

class TestCreateDeal:
    def test_create_deal(self, client: TestClient, auth_headers: dict) -> None:
        """Création valide → 201 + deal avec id."""
        resp = client.post("/pipeline/", headers=auth_headers, json=_deal())
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["nom"] == "Deal Alpha"
        assert data["etape"] == "Prospect"
        assert data["probabilite"] == 10  # auto Prospect

    def test_create_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        assert client.post("/pipeline/", json=_deal()).status_code == 401

    def test_create_invalid_etape(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Étape invalide → 422."""
        resp = client.post(
            "/pipeline/", headers=auth_headers,
            json=_deal(etape="Inexistant"),
        )
        assert resp.status_code == 422

    def test_create_negative_montant(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Montant négatif → 422."""
        resp = client.post(
            "/pipeline/", headers=auth_headers,
            json=_deal(montant=-100),
        )
        assert resp.status_code == 422

    def test_create_proba_auto_gagne(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Étape Gagné → probabilite = 100 automatiquement."""
        deal = _create(client, auth_headers, etape="Gagné")
        assert deal["probabilite"] == 100

    def test_create_proba_auto_perdu(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Étape Perdu → probabilite = 0 automatiquement."""
        deal = _create(client, auth_headers, etape="Perdu")
        assert deal["probabilite"] == 0


# ── PUT /pipeline/{deal_id} ───────────────────────────────────────────────────

class TestUpdateDeal:
    def test_update_deal(self, client: TestClient, auth_headers: dict) -> None:
        """Mise à jour → 200 + valeurs modifiées."""
        deal = _create(client, auth_headers, nom="Avant")
        resp = client.put(
            f"/pipeline/{deal['id']}", headers=auth_headers,
            json={"nom": "Après", "montant": 50000},
        )
        assert resp.status_code == 200
        assert resp.json()["nom"] == "Après"
        assert resp.json()["montant"] == 50000

    def test_update_nonexistent(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Deal inexistant → 404."""
        resp = client.put(
            "/pipeline/no-such-id", headers=auth_headers,
            json={"nom": "X"},
        )
        assert resp.status_code == 404


# ── PATCH /pipeline/{deal_id}/etape ──────────────────────────────────────────

class TestPatchEtape:
    def test_patch_etape(self, client: TestClient, auth_headers: dict) -> None:
        """PATCH étape → seule l'étape change."""
        deal = _create(client, auth_headers, etape="Prospect", nom="D1", client="C1")
        resp = client.patch(
            f"/pipeline/{deal['id']}/etape", headers=auth_headers,
            json={"etape": "Qualification"},
        )
        assert resp.status_code == 200
        assert resp.json()["etape"] == "Qualification"
        assert resp.json()["nom"] == "D1"

    def test_patch_etape_gagne(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Passage à Gagné → probabilite = 100."""
        deal = _create(client, auth_headers, etape="Négociation")
        resp = client.patch(
            f"/pipeline/{deal['id']}/etape", headers=auth_headers,
            json={"etape": "Gagné"},
        )
        assert resp.status_code == 200
        assert resp.json()["probabilite"] == 100

    def test_patch_etape_perdu(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Passage à Perdu → probabilite = 0."""
        deal = _create(client, auth_headers, etape="Proposition")
        resp = client.patch(
            f"/pipeline/{deal['id']}/etape", headers=auth_headers,
            json={"etape": "Perdu"},
        )
        assert resp.status_code == 200
        assert resp.json()["probabilite"] == 0


# ── DELETE /pipeline/{deal_id} ────────────────────────────────────────────────

class TestDeleteDeal:
    def test_delete_deal(self, client: TestClient, auth_headers: dict) -> None:
        """Suppression → 200 + disparition de la liste."""
        deal = _create(client, auth_headers)
        resp = client.delete(f"/pipeline/{deal['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        # Vérification via list
        lst = client.get("/pipeline/", headers=auth_headers).json()
        assert not any(d["id"] == deal["id"] for d in lst)

    def test_delete_nonexistent(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Deal inexistant → 404."""
        assert client.delete("/pipeline/no-such-id", headers=auth_headers).status_code == 404


# ── GET /pipeline/stats ───────────────────────────────────────────────────────

class TestPipelineStats:
    def test_stats_empty(self, client: TestClient, auth_headers: dict) -> None:
        """Aucun deal → stats à zéro."""
        resp = client.get("/pipeline/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["win_rate"] == 0.0
        assert data["count_active"] == 0

    def test_stats_calculation(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Win rate correct : 1 gagné, 1 perdu → 50%."""
        _create(client, auth_headers, etape="Gagné",  montant=20000)
        _create(client, auth_headers, etape="Perdu",  montant=10000)
        _create(client, auth_headers, etape="Prospect", montant=5000)
        resp = client.get("/pipeline/stats", headers=auth_headers)
        data = resp.json()
        assert data["count_won"] == 1
        assert data["count_lost"] == 1
        assert data["win_rate"] == 50.0
        assert data["count_active"] == 1
        assert data["total_value"] == 5000.0

    def test_stats_requires_auth(self, client: TestClient) -> None:
        """Sans token → 401."""
        assert client.get("/pipeline/stats").status_code == 401
