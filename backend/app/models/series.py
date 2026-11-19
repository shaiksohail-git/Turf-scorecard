"""Series model: a container for matches that share rules."""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class Series(TimestampMixin, db.Model):
    __tablename__ = "series"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name = db.Column(db.String(120), nullable=False)
    format = db.Column(db.String(24), nullable=False, default="custom")
    preset = db.Column(db.String(32))
    planned_matches = db.Column(db.Integer, nullable=False, default=0)
    team_a_name = db.Column(db.String(80))
    team_b_name = db.Column(db.String(80))
    team_a_players = db.Column(db.JSON)
    team_b_players = db.Column(db.JSON)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    matches = db.relationship("Match", back_populates="series", order_by="Match.id")
    match_links = db.relationship(
        "SeriesMatch", back_populates="series", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.Index("ix_series_owner_id_id", "owner_id", "id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Series {self.id} {self.name!r}>"
