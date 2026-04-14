"""
Qomiq — Construction des prompts pour le Coach IA.

4 analyses structurées + mode chat libre.
Toutes les fonctions sont pures (aucun I/O).
"""
from __future__ import annotations

from datetime import date

# ── Prompt système commun ────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es le Coach Commercial IA de Qomiq, un expert en performance
commerciale et pilotage d'entreprise. Tu analyses des données réelles de l'utilisateur
pour fournir des recommandations concrètes, actionnables et chiffrées.

Règles strictes :
- Réponse en français uniquement
- Structure tes réponses avec des titres Markdown (##, ###)
- Sois direct et concis — pas de généralités, que des faits issus des données
- Chaque recommandation doit être actionnable dans les 7 prochains jours
- Si les données sont insuffisantes, dis-le clairement et demande ce qu'il manque
- Ne jamais inventer de données non fournies
"""


# ── Formatage du contexte utilisateur ────────────────────────────────────────

def _fmt_pipeline(deals: list[dict]) -> str:
    if not deals:
        return "Aucun deal dans le pipeline."
    total = sum(float(d.get("montant") or 0) for d in deals)
    lines = [f"- **{d.get('nom', '?')}** | {d.get('client', '?')} | "
             f"{float(d.get('montant') or 0):,.0f}€ | {d.get('etape', d.get('statut', '?'))} | "
             f"clôture : {d.get('date_cloture', 'N/A')}"
             for d in deals[:15]]
    return f"**Total pipeline : {total:,.0f}€ ({len(deals)} deals)**\n" + "\n".join(lines)


def _fmt_ca(rows: list[dict]) -> str:
    if not rows:
        return "Aucune donnée CA mensuel."
    today = date.today()
    lines = []
    for r in sorted(rows, key=lambda x: (
        int(str(x.get("annee", today.year))),
        int(str(x.get("mois", 1)))
    ), reverse=True)[:12]:
        mois = r.get("mois", "?")
        annee = r.get("annee", today.year)
        ca = float(r.get("ca_realise") or 0)
        obj = float(r.get("ca_objectif") or r.get("objectif") or 0)
        pct = f" ({ca/obj*100:.0f}% obj)" if obj > 0 else ""
        lines.append(f"- {annee}/{mois:>02} : {ca:,.0f}€{pct}")
    return "\n".join(lines)


def _fmt_budget(lines: list[dict]) -> str:
    if not lines:
        return "Aucune donnée budgétaire."
    result = []
    for l in lines[:10]:
        nom = l.get("nom", l.get("ligne", "?"))
        budget = float(l.get("budget") or 0)
        reel = float(l.get("reel") or 0)
        ecart = reel - budget
        signe = "⚠️" if ecart > 0 else "✅"
        result.append(f"- {signe} **{nom}** : budget {budget:,.0f}€ | réel {reel:,.0f}€ | écart {ecart:+,.0f}€")
    return "\n".join(result)


def _fmt_produits(products: list[dict]) -> str:
    if not products:
        return "Aucune donnée produits."
    lines = []
    for p in sorted(products, key=lambda x: float(x.get("ca") or 0), reverse=True)[:10]:
        nom = p.get("nom", "?")
        ca = float(p.get("ca") or 0)
        ventes = p.get("ventes", "N/A")
        stock = p.get("stock", "N/A")
        lines.append(f"- **{nom}** | CA : {ca:,.0f}€ | ventes : {ventes} | stock : {stock}")
    return "\n".join(lines)


def build_context(
    pipeline: list[dict],
    ca_rows: list[dict],
    budget: list[dict],
    produits: list[dict],
    health_score: int | None = None,
) -> str:
    today = date.today().isoformat()
    ctx = f"**Date d'analyse : {today}**\n\n"
    if health_score is not None:
        ctx += f"**Score de santé global : {health_score}/100**\n\n"
    ctx += f"### Pipeline commercial\n{_fmt_pipeline(pipeline)}\n\n"
    ctx += f"### CA mensuel (12 derniers mois)\n{_fmt_ca(ca_rows)}\n\n"
    ctx += f"### Budget\n{_fmt_budget(budget)}\n\n"
    ctx += f"### Top produits\n{_fmt_produits(produits)}\n"
    return ctx


# ── Prompts des 4 analyses ────────────────────────────────────────────────────

def prompt_pestel(context: str) -> str:
    return f"""Réalise une analyse PESTEL commerciale à partir de ces données :

{context}

## Format de réponse OBLIGATOIRE — respecte exactement ce format markdown :

## Analyse PESTEL

| Facteur | Description | Impact | Opportunité / Menace |
|---------|-------------|--------|----------------------|
| 🏛️ Politique | [facteur clé 1] | Élevé/Moyen/Faible | Opportunité/Menace |
| 🏛️ Politique | [facteur clé 2] | Élevé/Moyen/Faible | Opportunité/Menace |
| 💰 Économique | [facteur clé 1] | Élevé/Moyen/Faible | Opportunité/Menace |
| 💰 Économique | [facteur clé 2] | Élevé/Moyen/Faible | Opportunité/Menace |
| 👥 Social | [facteur clé 1] | Élevé/Moyen/Faible | Opportunité/Menace |
| 👥 Social | [facteur clé 2] | Élevé/Moyen/Faible | Opportunité/Menace |
| 💡 Technologique | [facteur clé 1] | Élevé/Moyen/Faible | Opportunité/Menace |
| 💡 Technologique | [facteur clé 2] | Élevé/Moyen/Faible | Opportunité/Menace |
| 🌱 Environnemental | [facteur clé 1] | Élevé/Moyen/Faible | Opportunité/Menace |
| 🌱 Environnemental | [facteur clé 2] | Élevé/Moyen/Faible | Opportunité/Menace |
| ⚖️ Légal | [facteur clé 1] | Élevé/Moyen/Faible | Opportunité/Menace |
| ⚖️ Légal | [facteur clé 2] | Élevé/Moyen/Faible | Opportunité/Menace |

### 🎯 3 Recommandations prioritaires
1. [Action concrète avec impact CA estimé]
2. [Action concrète avec impact CA estimé]
3. [Action concrète avec impact CA estimé]

Règles strictes :
- Remplace chaque [facteur clé] par un fait tiré des données fournies
- Chaque cellule ne doit pas contenir de pipe | non échappé
- Le tableau doit être du markdown valide avec les séparateurs | bien alignés
- Chaque lettre du PESTEL doit avoir exactement 2 lignes dans le tableau
- Les recommandations doivent citer des chiffres issus des données (CA, nombre de deals, etc.)"""


def prompt_bcg(context: str) -> str:
    return f"""Réalise une analyse matricielle BCG des produits/segments à partir de ces données :

{context}

## Format attendu :
### Étoiles (forte croissance, forte part de marché)
### Vaches à lait (faible croissance, forte part de marché)
### Dilemmes (forte croissance, faible part de marché)
### Poids morts (faible croissance, faible part de marché)

Pour chaque quadrant : liste les produits/segments concernés avec justification chiffrée.
Termine par **3 recommandations d'allocation des ressources**."""


def prompt_ansoff(context: str) -> str:
    return f"""Réalise une analyse de la matrice Ansoff à partir de ces données :

{context}

## Format attendu :
### Pénétration de marché (produits existants × marchés existants)
### Développement de produits (nouveaux produits × marchés existants)
### Développement de marchés (produits existants × nouveaux marchés)
### Diversification (nouveaux produits × nouveaux marchés)

Pour chaque quadrant : opportunités identifiées dans les données + niveau de risque.
Termine par **la stratégie recommandée** avec justification chiffrée."""


def prompt_porter(context: str) -> str:
    return f"""Réalise une analyse des 5 forces de Porter à partir de ces données :

{context}

## Format attendu :
### Pouvoir des clients
### Pouvoir des fournisseurs
### Menace des nouveaux entrants
### Menace des substituts
### Rivalité entre concurrents

Pour chaque force : niveau (Faible/Moyen/Fort) + indicateurs issus des données.
Termine par **la position concurrentielle globale** et **2 leviers de différenciation**."""


def prompt_chat(context: str, user_message: str, history: list[dict]) -> list[dict]:
    """
    Construit la liste de messages pour une conversation libre.

    Args:
        context:      Contexte formaté des données utilisateur.
        user_message: Message courant de l'utilisateur.
        history:      Historique [{role, content}, ...] (max 10 tours).

    Returns:
        Liste de messages Anthropic API.
    """
    # Contexte en premier message système (via premier user turn si pas déjà là)
    messages: list[dict] = []

    # Injecter le contexte comme premier tour si historique vide
    if not history:
        messages.append({
            "role": "user",
            "content": f"Voici les données actuelles de mon entreprise :\n\n{context}\n\n"
                       f"Tu peux te référer à ces données dans toute notre conversation.",
        })
        messages.append({
            "role": "assistant",
            "content": "Bonjour ! J'ai bien analysé vos données. Je suis prêt à répondre "
                       "à vos questions et vous accompagner dans votre développement commercial. "
                       "Comment puis-je vous aider ?",
        })
    else:
        # Conserver les 10 derniers tours max (évite les tokens excessifs)
        for turn in history[-10:]:
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages
