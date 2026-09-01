"""Shared "what threat activity is this actor associated with?" query — used
by both GET /api/actors/{id}/threat-activity and the JSON/CSV/PDF exports,
so the API and an exported report can never disagree about which classified
activities support an actor's threat-category summary. Mirrors
app.services.attribution_explain's "one implementation, not two copies that
drift apart" rationale.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.actor import ThreatActivity
from app.services.threat_categorization import CATEGORY_LABELS


@dataclass
class CategorySummary:
    category: str
    category_label: str
    activity_count: int
    sources: list[str]


def get_actor_threat_activities(db: Session, actor_id: uuid.UUID) -> list[ThreatActivity]:
    # id is a real tiebreaker, not decoration: many rows legitimately share
    # observed_at (often NULL — see ThreatActivity's docstring), and without
    # a deterministic secondary key, two separate paginated fetches of the
    # same actor (GET .../threat-activity?page=1, then ?page=2) can return
    # tied rows in a different relative order, silently skipping or
    # duplicating activities across pages.
    return (
        db.query(ThreatActivity)
        .filter(ThreatActivity.actor_id == actor_id)
        .order_by(ThreatActivity.observed_at.desc().nullslast(), ThreatActivity.id)
        .all()
    )


def summarize_by_category(activities: list[ThreatActivity]) -> list[CategorySummary]:
    by_category: dict[str, list[ThreatActivity]] = {}
    for activity in activities:
        by_category.setdefault(activity.category, []).append(activity)

    return [
        CategorySummary(
            category=category,
            category_label=CATEGORY_LABELS.get(category, category),
            activity_count=len(items),
            sources=sorted({item.source_platform for item in items}),
        )
        for category, items in sorted(by_category.items(), key=lambda kv: -len(kv[1]))
    ]
