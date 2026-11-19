"""Series-to-match association.

``matches.series_id`` stays as the quick reference used by list filters, while
this table normalizes series membership and carries the ordering of matches
inside a series.
"""

from __future__ import annotations

from ..extensions import db
from .base import utcnow


class SeriesMatch(db.Model):
    __tablename__ = "series_matches"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(
        db.Integer, db.ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_id = db.Column(
        db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    series = db.relationship("Series", back_populates="match_links")
    match = db.relationship("Match", back_populates="series_links")

    __table_args__ = (
        db.UniqueConstraint("series_id", "match_id", name="uq_series_matches_pair"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SeriesMatch series={self.series_id} match={self.match_id}>"
