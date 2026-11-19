"""Match timeline events (created, started, delivery recorded, delivery voided).

Ball-by-ball detail lives in ``deliveries``; this table is the human-readable
audit trail that powers the match timeline and undo history.
"""

from __future__ import annotations

from ..extensions import db
from .base import utcnow


class MatchEvent(db.Model):
    __tablename__ = "match_events"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings_id = db.Column(db.Integer, db.ForeignKey("innings.id", ondelete="SET NULL"))
    delivery_id = db.Column(db.Integer, db.ForeignKey("deliveries.id", ondelete="SET NULL"))

    event_type = db.Column(db.String(48), nullable=False, index=True)
    actor = db.Column(db.String(64), nullable=False, default="scorer")
    payload = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        db.Index("ix_match_events_match_id_id", "match_id", "id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MatchEvent {self.id} {self.event_type} match={self.match_id}>"
