"""Per-match team participation.

``matches.team_a_id`` / ``team_b_id`` remain the fast side lookup used by the
scoring engine, while ``match_teams`` records the normalized participation rows
(side, toss winner, who bats first) that biographies, stats and future
per-match team settings build on. Both are written in the same transaction.
"""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class MatchTeam(TimestampMixin, db.Model):
    __tablename__ = "match_teams"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    side = db.Column(db.String(1), nullable=False)
    is_toss_winner = db.Column(db.Boolean, nullable=False, default=False)
    bats_first = db.Column(db.Boolean, nullable=False, default=False)

    match = db.relationship("Match", back_populates="match_teams")
    team = db.relationship("Team")

    __table_args__ = (
        db.UniqueConstraint("match_id", "side", name="uq_match_teams_match_side"),
        db.UniqueConstraint("match_id", "team_id", name="uq_match_teams_match_team"),
        db.CheckConstraint("side IN ('a', 'b')", name="ck_match_teams_side"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MatchTeam match={self.match_id} team={self.team_id} side={self.side}>"
