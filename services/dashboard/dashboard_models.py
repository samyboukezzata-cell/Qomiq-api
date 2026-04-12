"""
Qomiq — Modèles de données du tableau de bord premier écran.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DealSummary:
    """Résumé d'un deal pour l'affichage dans les top-deals du dashboard."""
    nom:              str
    client:           str
    montant:          float
    days_until_close: int | None   # None si date_cloture absente ou passée


@dataclass
class PipelineStats:
    """Statistiques agrégées du pipeline commercial."""
    total_montant:      float
    count:              int
    closing_soon_count: int              # deals clôturant dans ≤ 7 jours
    top_deals:          list[DealSummary]  # top 3 par montant décroissant


@dataclass
class CaStats:
    """CA réalisé du mois courant vs mois précédent."""
    current_month:       float
    previous_month:      float
    growth_pct:          float | None   # None si mois précédent = 0
    current_month_label: str            # ex. "Avr. 2026"
    # Champs optionnels — backward-compatible
    objectif:     float = 0.0
    objectif_pct: float = 0.0   # current_month / objectif * 100
    is_behind:    bool  = False  # True si current_month < objectif


@dataclass
class BudgetStats:
    """Synthèse budgétaire toutes lignes confondues."""
    total_budget:      float
    total_reel:        float
    consumed_pct:      float   # total_reel / total_budget * 100
    lines_over_budget: int     # nombre de lignes en dépassement


@dataclass
class AlertStats:
    """Compteurs d'alertes actives (non masquées)."""
    total_active:   int
    critical_count: int
    warning_count:  int


@dataclass
class ActionItem:
    """Action dérivée d'une alerte — affichée dans la section "À faire"."""
    title:       str
    description: str
    priority:    str  = "LOW"   # "HIGH" | "MEDIUM" | "LOW"
    done:        bool = False


@dataclass
class DashboardSummary:
    """Agrégat complet du tableau de bord premier écran."""
    pipeline:    PipelineStats
    ca:          CaStats
    budget:      BudgetStats
    alerts:      AlertStats
    computed_at: str   # date ISO YYYY-MM-DD
    # Champs enrichis — backward-compatible
    has_data:     bool        = False
    health_score: int         = 0    # 0-100
    health_delta: int         = 0    # variation vs semaine précédente
    ca_history:   list        = field(default_factory=list)   # list[dict]
    actions:      list        = field(default_factory=list)   # list[ActionItem]
