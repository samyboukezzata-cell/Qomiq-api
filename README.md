# Qomiq API

Backend FastAPI pour Qomiq — Intelligence Commerciale PME

## Stack

- **FastAPI** + **SQLAlchemy 2** + **PostgreSQL** (prod) / **SQLite** (dev/tests)
- **bcrypt** — hachage des mots de passe
- **python-jose** — JWT HS256
- **openpyxl** + **chardet** — import CSV/XLSX

## Lancement local

```bash
pip install -r requirements.txt
cp .env.example .env   # remplir les variables
uvicorn main:app --reload
```

L'API est disponible sur `http://localhost:8000`.
Documentation interactive : `http://localhost:8000/docs`

## Tests

```bash
pytest tests/ -v
```

Les tests utilisent SQLite en mémoire — aucune configuration requise.

## Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/auth/register` | Créer un compte |
| POST | `/auth/login` | Obtenir un JWT |
| GET | `/auth/me` | Profil utilisateur |
| GET | `/dashboard/summary` | Tableau de bord complet |
| GET | `/dashboard/kpis` | KPIs condensés |
| GET | `/alerts/` | Liste des alertes |
| PATCH | `/alerts/{id}/read` | Marquer une alerte lue |
| POST | `/alerts/refresh` | Recalculer les alertes |
| GET | `/health-score/current` | Score de santé courant |
| GET | `/health-score/history` | Historique du score |
| POST | `/import/upload` | Parser un fichier CSV/XLSX |
| POST | `/import/validate` | Valider les données |
| POST | `/import/save` | Sauvegarder les données |
| GET | `/import/templates/{type}` | Template CSV |

## Déploiement

Voir `render.yaml` — déploiement automatique via GitHub sur [Render.com](https://render.com).

Variables d'environnement requises :
- `DATABASE_URL` — fournie automatiquement par Render
- `SECRET_KEY` — générée automatiquement par Render
