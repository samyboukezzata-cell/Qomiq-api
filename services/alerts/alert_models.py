"""
Qomiq — Modèles de données pour les alertes proactives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AlertType(str, Enum):
    """Types d'alertes supportés par le moteur."""
    DEAL_STALE       = "deal_stale"       # Deal sans activité récente
    DEAL_CLOSING     = "deal_closing"     # Date de clôture imminente
    STOCK_LOW        = "stock_low"        # Stock sous le seuil minimum
    BUDGET_OVERRUN   = "budget_overrun"   # Dépassement budgétaire


class AlertLevel(str, Enum):
    """Niveau de criticité d'une alerte."""
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """
    Représente une alerte proactive générée par le moteur.

    Attributes:
        id:          Identifiant stable (type + entity_id) pour dédupliquer.
        alert_type:  Valeur de AlertType.
        level:       Valeur de AlertLevel.
        title:       Titre court affiché dans l'UI.
        message:     Message détaillé.
        entity_id:   Identifiant de l'entité source (nom du deal, produit…).
        entity_data: Snapshot des données ayant déclenché l'alerte.
        created_at:  Date ISO 8601 de génération (YYYY-MM-DD).
        is_read:     True si l'utilisateur a consulté l'alerte.
        is_dismissed: True si l'alerte a été masquée.
    """
    id:           str
    alert_type:   str
    level:        str
    title:        str
    message:      str
    entity_id:    str
    entity_data:  dict
    created_at:   str
    is_read:      bool = False
    is_dismissed: bool = False

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "alert_type":   self.alert_type,
            "level":        self.level,
            "title":        self.title,
            "message":      self.message,
            "entity_id":    self.entity_id,
            "entity_data":  self.entity_data,
            "created_at":   self.created_at,
            "is_read":      self.is_read,
            "is_dismissed": self.is_dismissed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Alert":
        return cls(
            id=d["id"],
            alert_type=d["alert_type"],
            level=d["level"],
            title=d["title"],
            message=d["message"],
            entity_id=d["entity_id"],
            entity_data=d.get("entity_data", {}),
            created_at=d["created_at"],
            is_read=d.get("is_read", False),
            is_dismissed=d.get("is_dismissed", False),
        )
