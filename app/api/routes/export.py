import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import Actor
from app.models.external import CorrelationEvidence
from app.schemas.actor import ActorProfileOut
from app.services.attribution_explain import explain_attribution

router = APIRouter(prefix="/api/export", tags=["export"], dependencies=[Depends(get_current_user)])

# Platforms that only ever hold Argus's own synthetic/controlled data — an
# exported report for an actor built entirely from these must say SYNTHETIC
# up front rather than let a reader mistake it for a real attribution.
SYNTHETIC_PLATFORMS = {
    "argus_controlled_demo",
    "mock_marketplace_1",
    "mock_marketplace_2",
    "mock_marketplace_3",
}


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    """Guards against CSV/formula injection (OWASP): a cell value starting
    with =, +, -, or @ is interpreted as a formula by Excel/Sheets when the
    file is opened, not as literal text. This matters here specifically
    because POST /api/leads lets an authenticated user submit free-text
    wallet/pgp_key/onion_address/username values that flow straight into
    this export — prefixing a leading apostrophe neutralizes the formula
    without changing what the cell displays."""
    text = str(value)
    if text and text[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + text
    return text


def _load_actor(actor_id: uuid.UUID, db: Session) -> Actor:
    actor = (
        db.query(Actor)
        .options(
            selectinload(Actor.identifiers),
            selectinload(Actor.infra_findings),
            selectinload(Actor.style_profiles),
            selectinload(Actor.attribution_edges),
        )
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


def _is_synthetic(actor: Actor) -> bool:
    return bool(actor.identifiers) and all(
        ident.source_platform in SYNTHETIC_PLATFORMS for ident in actor.identifiers
    )


@router.get("/{actor_id}/json")
def export_json(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    actor = _load_actor(actor_id, db)
    payload = ActorProfileOut.model_validate(actor).model_dump(mode="json")
    return JSONResponse(content=payload)


@router.get("/{actor_id}/csv")
def export_csv(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    actor = _load_actor(actor_id, db)
    correlation_evidence = (
        db.query(CorrelationEvidence).filter(CorrelationEvidence.actor_id == actor_id).all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["type", "value", "source", "detail"])
    for ident in actor.identifiers:
        writer.writerow(
            [
                _csv_safe(ident.identifier_type),
                _csv_safe(ident.value),
                _csv_safe(ident.source_platform),
                "",
            ]
        )
    for finding in actor.infra_findings:
        writer.writerow(
            [
                _csv_safe(finding.finding_type),
                _csv_safe(finding.onion_address),
                "infra_scan",
                _csv_safe(finding.detail),
            ]
        )
    for edge in actor.attribution_edges:
        writer.writerow(
            [
                _csv_safe(f"attribution_{edge.edge_type}"),
                _csv_safe(f"{edge.username_a} <-> {edge.username_b}"),
                _csv_safe(f"{edge.platform_a} / {edge.platform_b}"),
                _csv_safe(f"weight={edge.weight}"),
            ]
        )
    for ev in correlation_evidence:
        writer.writerow(
            [
                _csv_safe(f"correlation_{ev.evidence_type}"),
                _csv_safe(ev.matched_value),
                _csv_safe(ev.source),
                _csv_safe(ev.description),
            ]
        )
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=actor_{actor_id}.csv"},
    )


_PAGE_MARGIN_BOTTOM = 50


def _draw_line(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    height: float,
    text: str,
    font: tuple[str, int] = ("Helvetica", 10),
) -> float:
    """Draws one line, starting a fresh page first if we're about to run off
    the bottom. Always (re-)applies `font` itself, including right after a
    page break — reportlab's showPage() does not carry font state across
    pages, so a version of this that reset to a hardcoded font on every new
    page would silently drop a caller's bold/size when a heading line (not
    just body text) happened to fall right at a page boundary."""
    if y < _PAGE_MARGIN_BOTTOM:
        pdf.showPage()
        y = height - _PAGE_MARGIN_BOTTOM
    pdf.setFont(*font)
    pdf.drawString(x, y, text)
    return y - 15


def _confidence_status(score: float) -> str:
    if score >= 0.7:
        return "High confidence"
    if score >= 0.4:
        return "Medium confidence"
    if score > 0:
        return "Low confidence — under investigation"
    return "Under investigation — no linking evidence yet"


@router.get("/{actor_id}/report")
def export_report(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    actor = _load_actor(actor_id, db)
    correlation_evidence = (
        db.query(CorrelationEvidence).filter(CorrelationEvidence.actor_id == actor_id).all()
    )
    explanation = explain_attribution(db, actor)
    synthetic = _is_synthetic(actor)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, "ARGUS")
    y -= 22
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, "Threat Actor Investigation Report")
    y -= 20
    pdf.setFont("Helvetica-Oblique", 9)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.drawString(50, y, f"Generated: {generated}")
    y -= 25

    if synthetic:
        pdf.setFillColorRGB(0.75, 0.35, 0.1)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y, "[ SYNTHETIC / CONTROLLED DATA — not a real-world identity ]")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 20

    # actor.label is already stored as "Actor: <names>" (see pipeline.py) —
    # don't re-prefix it here.
    y = _draw_line(pdf, 50, y, height, actor.label, font=("Helvetica-Bold", 14))
    y = _draw_line(pdf, 50, y, height, f"Actor ID: {actor.id}", font=("Helvetica-Oblique", 9))
    y -= 5
    y = _draw_line(
        pdf, 50, y, height,
        f"Attribution confidence: {actor.confidence_score * 100:.0f}%  "
        f"({_confidence_status(actor.confidence_score)})",
        font=("Helvetica-Bold", 12),
    )
    y = _draw_line(
        pdf, 50, y, height, f"Last observed: {actor.updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
    )
    y -= 15

    y = _draw_line(pdf, 50, y, height, "ATTRIBUTION BREAKDOWN", font=("Helvetica-Bold", 13))
    y -= 5
    for signal in explanation.signals:
        value_text = "Not enough evidence" if not signal.available else f"{signal.value * 100:.0f}%"
        y = _draw_line(pdf, 60, y, height, f"- {signal.label}: {value_text}")
    y = _draw_line(pdf, 60, y, height, f"Evidence items: {explanation.evidence_count}")
    y -= 15

    y = _draw_line(pdf, 50, y, height, "IDENTIFIERS", font=("Helvetica-Bold", 13))
    y -= 5
    if not actor.identifiers:
        y = _draw_line(pdf, 60, y, height, "No evidence available.")
    for ident in actor.identifiers:
        y = _draw_line(
            pdf, 60, y, height,
            f"- [{ident.identifier_type}] {ident.value} ({ident.source_platform})",
        )
    y -= 15

    y = _draw_line(pdf, 50, y, height, "INFRASTRUCTURE", font=("Helvetica-Bold", 13))
    y -= 5
    if not actor.infra_findings:
        y = _draw_line(pdf, 60, y, height, "No evidence available.")
    for finding in actor.infra_findings:
        y = _draw_line(pdf, 60, y, height, f"- [{finding.finding_type}] {finding.onion_address}")
    y -= 15

    y = _draw_line(pdf, 50, y, height, "THREAT INTELLIGENCE", font=("Helvetica-Bold", 13))
    y -= 5
    if not correlation_evidence:
        y = _draw_line(
            pdf, 60, y, height,
            "No deterministic match against Tor Onionoo, MISP, or HIBP for this actor's "
            "confirmed infrastructure.",
        )
    for ev in correlation_evidence:
        y = _draw_line(pdf, 60, y, height, f"- [{ev.source}] {ev.matched_value}: {ev.description}")
    y -= 15

    y = _draw_line(pdf, 50, y, height, "RELATIONSHIPS", font=("Helvetica-Bold", 13))
    y -= 5
    if not actor.attribution_edges:
        y = _draw_line(pdf, 60, y, height, "Single-persona actor — no linking evidence found.")
    for edge in actor.attribution_edges:
        y = _draw_line(
            pdf, 60, y, height,
            f"- {edge.username_a} <-> {edge.username_b}: {edge.edge_type} "
            f"(weight {edge.weight * 100:.0f}%)",
        )
    y -= 15

    y = _draw_line(pdf, 50, y, height, "SOURCE PROVENANCE", font=("Helvetica-Bold", 13))
    y -= 5
    for source in explanation.sources:
        y = _draw_line(pdf, 60, y, height, f"- {source}")
    for source in sorted({ev.source for ev in correlation_evidence}):
        y = _draw_line(pdf, 60, y, height, f"- {source} (live threat intelligence)")
    if not explanation.sources and not correlation_evidence:
        y = _draw_line(pdf, 60, y, height, "No evidence available.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=actor_{actor_id}_report.pdf"},
    )
