"""Per-player, per-match statistics derived from delivery events.

Rows are rebuilt whenever an innings is recomputed (every delivery and every
undo), so this table is a cached projection and never the source of truth.
"""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class PlayerMatchStatistics(TimestampMixin, db.Model):
    __tablename__ = "player_match_statistics"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id = db.Column(
        db.Integer, db.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)

    batting_innings = db.Column(db.Integer, nullable=False, default=0)
    runs = db.Column(db.Integer, nullable=False, default=0)
    highest_score = db.Column(db.Integer, nullable=False, default=0)
    balls_faced = db.Column(db.Integer, nullable=False, default=0)
    fours = db.Column(db.Integer, nullable=False, default=0)
    sixes = db.Column(db.Integer, nullable=False, default=0)
    is_out = db.Column(db.Boolean, nullable=False, default=False)
    not_outs = db.Column(db.Integer, nullable=False, default=0)
    dismissal = db.Column(db.String(64))

    bowling_innings = db.Column(db.Integer, nullable=False, default=0)
    balls_bowled = db.Column(db.Integer, nullable=False, default=0)
    runs_conceded = db.Column(db.Integer, nullable=False, default=0)
    wickets = db.Column(db.Integer, nullable=False, default=0)
    best_bowling_wickets = db.Column(db.Integer, nullable=False, default=0)
    best_bowling_runs = db.Column(db.Integer, nullable=False, default=0)
    wides = db.Column(db.Integer, nullable=False, default=0)
    no_balls = db.Column(db.Integer, nullable=False, default=0)

    fantasy_points = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("match_id", "player_id", name="uq_player_match_statistics"),
        db.CheckConstraint(
            "runs >= 0 AND balls_faced >= 0 AND wickets >= 0 AND runs_conceded >= 0",
            name="ck_player_match_statistics_values",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<PlayerMatchStatistics match={self.match_id} player={self.player_id} "
            f"runs={self.runs} wickets={self.wickets}>"
        )
