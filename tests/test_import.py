"""
Tests d'intégration — /import/.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from models.user_data import get_user_data
from tests.conftest import _TestingSession


# ── Helpers ───────────────────────────────────────────────────────────────────

def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _upload(client: TestClient, headers: dict, content: bytes, filename: str) -> dict:
    resp = client.post(
        "/import/upload",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )
    return resp


def _get_user_data(user_id: int, data_type: str) -> list:
    db = _TestingSession()
    try:
        return get_user_data(db, user_id, data_type)
    finally:
        db.close()


# ── POST /import/upload ───────────────────────────────────────────────────────

class TestUpload:
    def test_upload_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/import/upload",
            files={"file": ("test.csv", io.BytesIO(b"nom,ca\nA,100"), "text/csv")},
        )
        assert resp.status_code == 401

    def test_upload_csv_pipeline(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """CSV avec colonnes pipeline → ParseResult correct."""
        csv_content = _csv_bytes(
            "nom,client,montant,date_cloture\n"
            "Deal A,Acme,15000,2026-12-31\n"
            "Deal B,Beta,8000,2026-06-30\n"
        )
        resp = _upload(client, auth_headers, csv_content, "pipeline.csv")
        assert resp.status_code == 200
        data = resp.json()
        assert "nom" in data["headers"]
        assert data["row_count"] == 2
        assert len(data["rows"]) == 2
        assert "suggested_mapping" in data
        assert "preview_values" in data

    def test_upload_csv_produits(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """CSV produits → type détecté."""
        csv_content = _csv_bytes(
            "nom,ca,ventes,stock\n"
            "Produit A,12000,150,45\n"
        )
        resp = _upload(client, auth_headers, csv_content, "produits.csv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected_type"] == "produits"
        assert data["detection_confidence"] > 0

    def test_upload_xlsx(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Fichier XLSX valide → ParseResult correct."""
        import openpyxl
        import io as _io
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["nom", "ca", "ventes", "stock"])
        ws.append(["Produit A", 12000, 150, 45])
        ws.append(["Produit B", 8000, 80, 10])
        buf = _io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        resp = client.post(
            "/import/upload",
            headers=auth_headers,
            files={"file": ("data.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["row_count"] == 2
        assert "nom" in data["headers"]

    def test_upload_invalid_extension(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Extension non supportée → 400 avec message clair."""
        resp = client.post(
            "/import/upload",
            headers=auth_headers,
            files={"file": ("data.pdf", io.BytesIO(b"some pdf"), "application/pdf")},
        )
        assert resp.status_code == 400
        assert "Extension" in resp.json()["detail"]

    def test_upload_empty_csv(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """CSV vide → 400."""
        resp = _upload(client, auth_headers, b"", "empty.csv")
        assert resp.status_code == 400


# ── POST /import/validate ─────────────────────────────────────────────────────

class TestValidate:
    def test_validate_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/import/validate", json={
            "mapping": {}, "data_type": "pipeline", "rows": [],
        })
        assert resp.status_code == 401

    def test_validate_mapping(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Remap + validation de lignes pipeline correctes."""
        resp = client.post("/import/validate", headers=auth_headers, json={
            "mapping": {"Nom Deal": "nom", "Montant": "montant"},
            "data_type": "pipeline",
            "rows": [
                {"Nom Deal": "Deal A", "Montant": "15000"},
                {"Nom Deal": "Deal B", "Montant": "8000"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["total"] == 2
        assert data["stats"]["valid"] == 2
        assert data["stats"]["invalid"] == 0
        # Les clés ont été remappées
        assert data["valid_rows"][0]["nom"] == "Deal A"

    def test_validate_invalid_rows(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Ligne sans champ requis 'nom' → détectée comme invalide."""
        resp = client.post("/import/validate", headers=auth_headers, json={
            "mapping": {},
            "data_type": "pipeline",
            "rows": [
                {"client": "Acme", "montant": "5000"},   # pas de 'nom'
                {"nom": "Deal B", "montant": "8000"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["invalid"] == 1
        assert data["stats"]["valid"] == 1

    def test_validate_unknown_data_type(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """data_type inconnu → warning, toutes les lignes valides."""
        resp = client.post("/import/validate", headers=auth_headers, json={
            "mapping": {},
            "data_type": "unknown_type",
            "rows": [{"foo": "bar"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["warnings"]) > 0
        assert data["stats"]["valid"] == 1


# ── POST /import/save ─────────────────────────────────────────────────────────

class TestSave:
    def test_save_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/import/save", json={
            "data_type": "pipeline", "rows": [], "merge_strategy": "replace",
        })
        assert resp.status_code == 401

    def test_save_data_replace(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Sauvegarde replace → données en base."""
        rows = [
            {"nom": "Deal A", "montant": "15000"},
            {"nom": "Deal B", "montant": "8000"},
        ]
        resp = client.post("/import/save", headers=auth_headers, json={
            "data_type": "pipeline",
            "rows": rows,
            "merge_strategy": "replace",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported_count"] == 2
        assert data["data_type"] == "pipeline"

        # Vérifier que les données sont bien en base
        stored = _get_user_data(user_id, "pipeline")
        assert len(stored) == 2
        assert stored[0]["nom"] == "Deal A"

    def test_save_data_append(
        self, client: TestClient, auth_headers: dict, user_id: int
    ) -> None:
        """Sauvegarde append → s'ajoute aux données existantes."""
        # Premier import
        client.post("/import/save", headers=auth_headers, json={
            "data_type": "pipeline",
            "rows": [{"nom": "Deal A"}],
            "merge_strategy": "replace",
        })
        # Second import avec append
        resp = client.post("/import/save", headers=auth_headers, json={
            "data_type": "pipeline",
            "rows": [{"nom": "Deal B"}],
            "merge_strategy": "append",
        })
        assert resp.status_code == 200
        stored = _get_user_data(user_id, "pipeline")
        assert len(stored) == 2

    def test_save_invalid_strategy(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Stratégie invalide → 422."""
        resp = client.post("/import/save", headers=auth_headers, json={
            "data_type": "pipeline",
            "rows": [],
            "merge_strategy": "invalid_strategy",
        })
        assert resp.status_code == 422


# ── GET /import/templates/{data_type} ────────────────────────────────────────

class TestTemplates:
    def test_template_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/import/templates/pipeline")
        assert resp.status_code == 401

    def test_template_pipeline(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Template pipeline → CSV avec les bons en-têtes."""
        resp = client.get("/import/templates/pipeline", headers=auth_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        assert "nom" in content
        assert "montant" in content

    def test_template_ca_mensuel(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        resp = client.get("/import/templates/ca_mensuel", headers=auth_headers)
        assert resp.status_code == 200
        assert "mois" in resp.text
        assert "ca_realise" in resp.text

    def test_template_unknown_type(
        self, client: TestClient, auth_headers: dict
    ) -> None:
        """Type inconnu → 404."""
        resp = client.get("/import/templates/unknown_type", headers=auth_headers)
        assert resp.status_code == 404
