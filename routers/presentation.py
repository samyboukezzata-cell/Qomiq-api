"""
Qomiq API — Router Mode Présentation DG.

Endpoints :
  GET  /presentation/data       — agrège toutes les données pour le rapport
  POST /presentation/export-pdf — génère un PDF ReportLab et le retourne
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.user_data import get_user_data
from routers.auth import get_current_user
from routers.alerts import _load_alerts_state, _refresh_alerts
from services.alerts.alert_models import AlertLevel
from services.dashboard.dashboard_engine import (
    compute_ca_stats,
    compute_pipeline_stats,
    compute_budget_stats,
)
from services.health_score.health_engine import compute_health_score
from services.dashboard.dashboard_engine import _parse_ym

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/presentation", tags=["presentation"])

_MONTH_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


# ── GET /presentation/data ────────────────────────────────────────────────────

@router.get("/data", summary="Données agrégées pour la présentation DG")
def presentation_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    today = date.today()
    period = f"{_MONTH_FR[today.month - 1]} {today.year}"

    # ── Données brutes ─────────────────────────────────────────────────────────
    pipeline_rows = get_user_data(db, current_user.id, "pipeline")
    ca_rows       = get_user_data(db, current_user.id, "ca_mensuel")
    budget_rows   = get_user_data(db, current_user.id, "budget")
    produits_rows = get_user_data(db, current_user.id, "produits")
    health_hist   = get_user_data(db, current_user.id, "health_history")
    coach_hist    = get_user_data(db, current_user.id, "coach_history")

    # ── KPIs dashboard ─────────────────────────────────────────────────────────
    ca_stats     = compute_ca_stats(ca_rows, today=today)
    pipeline_st  = compute_pipeline_stats(pipeline_rows, today=today)
    budget_stats = compute_budget_stats(budget_rows)

    # ── Health score ───────────────────────────────────────────────────────────
    if health_hist:
        last_health = health_hist[-1]
    else:
        last_health = {"score": 0, "label": "N/A", "color": "#6b7280"}

    # ── Alertes critiques + importantes ────────────────────────────────────────
    alerts = _load_alerts_state(db, current_user.id)
    important_alerts = [
        a.to_dict() for a in alerts
        if not a.is_dismissed and a.level in (AlertLevel.CRITICAL, AlertLevel.WARNING)
    ][:10]

    # ── CA 6 derniers mois ─────────────────────────────────────────────────────
    from services.dashboard.dashboard_engine import compute_ca_history
    ca_history = compute_ca_history(ca_rows, today=today, n=6)

    # ── Top 5 deals par montant ────────────────────────────────────────────────
    top_deals = sorted(
        pipeline_rows,
        key=lambda d: float(d.get("montant") or 0),
        reverse=True,
    )[:5]

    # ── Dernière analyse Coach IA ──────────────────────────────────────────────
    last_analysis: str | None = None
    if coach_hist:
        last_analysis = coach_hist[-1].get("content")

    return {
        "generated_at":  today.isoformat(),
        "period":        period,
        "user_name":     current_user.full_name or current_user.email,
        "secteur":       "",
        "kpis": {
            "ca_mois_courant":  ca_stats.current_month,
            "ca_mois_precedent": ca_stats.previous_month,
            "ca_growth_pct":    ca_stats.growth_pct,
            "ca_label":         ca_stats.current_month_label,
            "pipeline_total":   pipeline_st.total_montant,
            "pipeline_count":   pipeline_st.count,
            "pipeline_closing_soon": pipeline_st.closing_soon_count,
            "budget_consomme_pct": budget_stats.consumed_pct,
            "budget_lignes_over":  budget_stats.lines_over_budget,
        },
        "ca_history":    ca_history,
        "top_deals":     top_deals,
        "health_score":  last_health,
        "alerts":        important_alerts,
        "last_analysis": last_analysis,
    }


# ── POST /presentation/export-pdf ─────────────────────────────────────────────

class PdfRequest(BaseModel):
    generated_at:  str
    period:        str
    user_name:     str
    secteur:       str = ""
    kpis:          dict
    ca_history:    list[dict]
    top_deals:     list[dict]
    health_score:  dict
    alerts:        list[dict]
    last_analysis: str | None = None


@router.post("/export-pdf", summary="Génère le rapport PDF")
def export_pdf(
    body: PdfRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    pdf_bytes = _build_pdf(body)
    filename = f"rapport-qomiq-{body.generated_at}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Génération PDF (ReportLab) ────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "[\U00010000-\U0010ffff]|[\U0001F300-\U0001F9FF]|[^\x00-\x7F]",
    flags=re.UNICODE,
)

def _clean_for_pdf(text: str) -> str:
    """Supprime les emojis et caractères non-ASCII non supportés par Helvetica."""
    return _EMOJI_RE.sub("", text)


def _build_pdf(data: PdfRequest) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable,
    )

    TEAL   = colors.HexColor("#0d9488")
    TEAL_L = colors.HexColor("#f0fdf9")
    GRAY   = colors.HexColor("#6b7280")
    WHITE  = colors.white
    BLACK  = colors.HexColor("#111827")
    RED    = colors.HexColor("#dc2626")
    ORANGE = colors.HexColor("#ea580c")
    RED_HEX    = "dc2626"
    ORANGE_HEX = "ea580c"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    h1  = ParagraphStyle("H1",  parent=styles["Heading1"],
                          fontSize=22, textColor=TEAL, spaceAfter=6)
    h2  = ParagraphStyle("H2",  parent=styles["Heading2"],
                          fontSize=14, textColor=TEAL, spaceAfter=4)
    h3  = ParagraphStyle("H3",  parent=styles["Heading3"],
                          fontSize=11, textColor=BLACK, spaceAfter=3)
    body_s = ParagraphStyle("Body", parent=styles["Normal"],
                             fontSize=9, textColor=BLACK, spaceAfter=3, leading=13)
    small  = ParagraphStyle("Small", parent=styles["Normal"],
                             fontSize=8, textColor=GRAY)
    cover_title = ParagraphStyle("CoverTitle", parent=styles["Heading1"],
                                  fontSize=28, textColor=TEAL,
                                  spaceAfter=12, alignment=1)
    cover_sub = ParagraphStyle("CoverSub", parent=styles["Normal"],
                                fontSize=13, textColor=GRAY,
                                spaceAfter=8, alignment=1)

    def section_header(title: str) -> list:
        return [
            HRFlowable(width="100%", thickness=2, color=TEAL, spaceAfter=6),
            Paragraph(title, h2),
            Spacer(1, 0.2*cm),
        ]

    def fmt_eur(v: float) -> str:
        if v >= 1_000_000: return f"{v/1_000_000:.1f} M€"
        if v >= 1_000:     return f"{v/1_000:.0f} k€"
        return f"{v:.0f} €"

    story = []

    # ── Page 1 : Couverture ────────────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    # Logo "Q"
    logo_data = [["Q"]]
    logo_tbl = Table(logo_data, colWidths=[1.4*cm], rowHeights=[1.4*cm])
    logo_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), TEAL),
        ("TEXTCOLOR",    (0, 0), (-1, -1), WHITE),
        ("FONTSIZE",     (0, 0), (-1, -1), 22),
        ("FONTNAME",     (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(Table([[logo_tbl, Paragraph("<b>Qomiq</b>", cover_title)]],
                        colWidths=[1.8*cm, None]))
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("Rapport de Direction Générale", cover_title))
    story.append(Paragraph(data.period, cover_sub))
    if data.secteur:
        story.append(Paragraph(f"Secteur : {data.secteur}", cover_sub))
    story.append(Paragraph(f"Généré le {data.generated_at}", cover_sub))
    story.append(Paragraph(f"Préparé pour : {data.user_name}", cover_sub))
    story.append(PageBreak())

    # ── Page 2 : KPIs + Score de santé ────────────────────────────────────────
    story += section_header("SYNTHÈSE COMMERCIALE")

    kpis = data.kpis
    ca = kpis.get("ca_mois_courant", 0)
    ca_prev = kpis.get("ca_mois_precedent", 0)
    growth = kpis.get("ca_growth_pct")
    growth_str = (f"+{growth:.1f}%" if growth and growth > 0 else f"{growth:.1f}%" if growth else "N/A")

    kpi_data = [
        ["KPI", "Valeur", "Évolution"],
        ["CA mois courant",    fmt_eur(ca),                              growth_str],
        ["CA mois précédent",  fmt_eur(ca_prev),                         "—"],
        ["Pipeline total",     fmt_eur(kpis.get("pipeline_total", 0)),   f"{kpis.get('pipeline_count', 0)} deals"],
        ["Clôtures imminentes",str(kpis.get("pipeline_closing_soon", 0)),"≤ 7 jours"],
        ["Budget consommé",    f"{kpis.get('budget_consomme_pct', 0):.0f}%",
                               f"{kpis.get('budget_lignes_over', 0)} ligne(s) dépassée(s)"],
    ]
    kpi_tbl = Table(kpi_data, colWidths=[6*cm, 4*cm, 5*cm])
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, TEAL_L]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 0.5*cm))

    # Score de santé
    hs = data.health_score
    score = hs.get("score", 0)
    label = hs.get("label", "N/A")
    story.append(Paragraph(f"Score de Santé Commerciale : <b>{score}/100</b> — {label}", h3))
    story.append(PageBreak())

    # ── Page 3 : CA 6 mois ────────────────────────────────────────────────────
    story += section_header("ÉVOLUTION CA — 6 DERNIERS MOIS")

    ca_header = [["Mois", "CA Réalisé", "Objectif"]]
    ca_rows_pdf = [
        [row.get("label", row.get("mois", "")),
         fmt_eur(row.get("ca_realise", 0)),
         fmt_eur(row.get("objectif", 0))]
        for row in data.ca_history
    ]
    ca_tbl = Table(ca_header + ca_rows_pdf, colWidths=[5*cm, 5*cm, 5*cm])
    ca_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR",      (0, 0), (-1, 0), WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, TEAL_L]),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("ALIGN",          (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(ca_tbl)
    story.append(PageBreak())

    # ── Page 4 : Top 5 deals ──────────────────────────────────────────────────
    story += section_header("TOP 5 OPPORTUNITÉS PIPELINE")

    deal_header = [["Opportunité", "Client", "Montant", "Étape", "Clôture"]]
    deal_rows = [
        [d.get("nom", "—")[:30],
         d.get("client", "—")[:20],
         fmt_eur(float(d.get("montant") or 0)),
         d.get("etape", d.get("statut", "—"))[:15],
         d.get("date_cloture", "—")]
        for d in data.top_deals
    ]
    if not deal_rows:
        deal_rows = [["Aucun deal", "—", "—", "—", "—"]]
    deal_tbl = Table(deal_header + deal_rows, colWidths=[4.5*cm, 3.5*cm, 2.5*cm, 3*cm, 2.5*cm])
    deal_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR",      (0, 0), (-1, 0), WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, TEAL_L]),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("ALIGN",          (2, 0), (2, -1), "RIGHT"),
    ]))
    story.append(deal_tbl)
    story.append(PageBreak())

    # ── Page 5 : Alertes ──────────────────────────────────────────────────────
    story += section_header(f"ALERTES ACTIVES ({len(data.alerts)})")

    if not data.alerts:
        story.append(Paragraph("Aucune alerte critique ou importante.", body_s))
    else:
        for alert in data.alerts:
            level = alert.get("level", "info")
            color_hex = RED_HEX if level == "critical" else ORANGE_HEX
            story.append(Paragraph(
                f'<font color="#{color_hex}">■</font> '
                f'<b>{alert.get("title", "")}</b> — {alert.get("message", "")}',
                body_s,
            ))
            story.append(Spacer(1, 0.15*cm))

    # ── Page 6 : Analyse IA ───────────────────────────────────────────────────
    if data.last_analysis:
        story.append(PageBreak())
        story += section_header("ANALYSE STRATÉGIQUE (Coach IA)")
        # Tronquer le markdown à 3000 chars pour le PDF, texte brut
        analysis_text = _clean_for_pdf(
            data.last_analysis[:3000].replace("**", "").replace("##", "").replace("#", "")
        )
        for line in analysis_text.split("\n"):
            stripped = line.strip()
            if stripped:
                story.append(Paragraph(stripped, body_s))

    doc.build(story)
    return buf.getvalue()
