"""
Qomiq — Modèles de données pour le Score de Santé Commerciale.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HealthScoreResult:
    """
    Résultat complet d'un calcul de score de santé commerciale.

    Attributes:
        score:              Score global 0-100.
        label:              Libellé qualitatif (Excellent / Bon / Moyen / Faible).
        color:              Couleur hexadécimale associée au niveau.
        component_ca:       Composante CA vs objectif (0-100).
        component_pipeline: Composante pipeline (0-100).
        component_win_rate: Composante taux de conversion (0-100).
        component_activite: Composante activité / fraîcheur des deals (0-100).
        component_alertes:  Composante alertes actives (0-100).
        computed_at:        Date ISO 8601 du calcul (YYYY-MM-DD).
        secteur:            Secteur source des données.
        inputs:             Paramètres bruts utilisés (traçabilité).
    """
    score:              int
    label:              str
    color:              str
    component_ca:       float
    component_pipeline: float
    component_win_rate: float
    component_activite: float
    component_alertes:  float
    computed_at:        str
    secteur:            str  = ""
    inputs:             dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score":              self.score,
            "label":              self.label,
            "color":              self.color,
            "component_ca":       self.component_ca,
            "component_pipeline": self.component_pipeline,
            "component_win_rate": self.component_win_rate,
            "component_activite": self.component_activite,
            "component_alertes":  self.component_alertes,
            "computed_at":        self.computed_at,
            "secteur":            self.secteur,
            "inputs":             self.inputs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HealthScoreResult":
        return cls(
            score=             int(d.get("score", 0)),
            label=             str(d.get("label", "")),
            color=             str(d.get("color", "")),
            component_ca=      float(d.get("component_ca", 0.0)),
            component_pipeline=float(d.get("component_pipeline", 0.0)),
            component_win_rate=float(d.get("component_win_rate", 0.0)),
            component_activite=float(d.get("component_activite", 0.0)),
            component_alertes= float(d.get("component_alertes", 0.0)),
            computed_at=       str(d.get("computed_at", "")),
            secteur=           str(d.get("secteur", "")),
            inputs=            dict(d.get("inputs", {})),
        )
