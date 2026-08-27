import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import Actor
from app.schemas.actor import ActorProfileOut

router = APIRouter(prefix="/api/export", tags=["export"], dependencies=[Depends(get_current_user)])


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
        )
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@router.get("/{actor_id}/json")
def export_json(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    actor = _load_actor(actor_id, db)
    payload = ActorProfileOut.model_validate(actor).model_dump(mode="json")
    return JSONResponse(content=payload)


@router.get("/{actor_id}/csv")
def export_csv(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    actor = _load_actor(actor_id, db)

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


@router.get("/{actor_id}/report")
def export_report(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    actor = _load_actor(actor_id, db)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, f"Actor Report: {actor.label}")
    y -= 30
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Confidence score: {actor.confidence_score:.2f}")
    y -= 30

    y = _draw_line(pdf, 50, y, height, "Identifiers", font=("Helvetica-Bold", 13))
    y -= 5
    for ident in actor.identifiers:
        y = _draw_line(
            pdf, 60, y, height,
            f"- [{ident.identifier_type}] {ident.value} ({ident.source_platform})",
        )

    y -= 15
    y = _draw_line(pdf, 50, y, height, "Infrastructure Findings", font=("Helvetica-Bold", 13))
    y -= 5
    for finding in actor.infra_findings:
        y = _draw_line(pdf, 60, y, height, f"- [{finding.finding_type}] {finding.onion_address}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=actor_{actor_id}_report.pdf"},
    )
