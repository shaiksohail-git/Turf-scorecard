"""Normalized rules snapshot for one match.

The same resolved configuration is stored as JSON on ``matches.rules`` (the
scoring engine reads that immutable snapshot). This table normalizes the values
so rules can be queried and reported on without parsing JSON.
"""

from __future__ import annotations

from typing import Any

from ..extensions import db
from .base import TimestampMixin


class MatchRules(TimestampMixin, db.Model):
    __tablename__ = "match_rules"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    preset = db.Column(db.String(32), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)

    overs = db.Column(db.Integer, nullable=False)
    balls_per_over = db.Column(db.Integer, nullable=False)
    players_per_team = db.Column(db.Integer, nullable=False)
    wide_penalty = db.Column(db.Integer, nullable=False)
    wide_counts_as_legal_ball = db.Column(db.Boolean, nullable=False, default=False)
    no_ball_penalty = db.Column(db.Integer, nullable=False)
    no_ball_counts_as_legal_ball = db.Column(db.Boolean, nullable=False, default=False)
    free_hit_enabled = db.Column(db.Boolean, nullable=False, default=True)
    solo_batting_enabled = db.Column(db.Boolean, nullable=False, default=False)
    allowed_runs = db.Column(db.JSON, nullable=False)
    retired_player_option = db.Column(db.Boolean, nullable=False, default=True)
    retirement_types = db.Column(db.JSON, nullable=False)
    max_overs_per_bowler = db.Column(db.Integer)

    match = db.relationship("Match", back_populates="rules_row")

    __table_args__ = (
        db.CheckConstraint("overs >= 1 AND balls_per_over >= 1", name="ck_match_rules_overs"),
        db.CheckConstraint(
            "players_per_team >= 2 AND players_per_team <= 11",
            name="ck_match_rules_players",
        ),
        db.CheckConstraint("version >= 1", name="ck_match_rules_version"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Return the snapshot shape consumed by ``RuleSet.from_dict``."""
        return {
            "preset": self.preset,
            "overs": self.overs,
            "balls_per_over": self.balls_per_over,
            "players_per_team": self.players_per_team,
            "wide_penalty": self.wide_penalty,
            "wide_counts_as_legal_ball": self.wide_counts_as_legal_ball,
            "no_ball_penalty": self.no_ball_penalty,
            "no_ball_counts_as_legal_ball": self.no_ball_counts_as_legal_ball,
            "free_hit_enabled": self.free_hit_enabled,
            "solo_batting_enabled": self.solo_batting_enabled,
            "allowed_runs": list(self.allowed_runs or []),
            "retired_player_option": self.retired_player_option,
            "retirement_types": list(self.retirement_types or []),
            "max_overs_per_bowler": self.max_overs_per_bowler,
        }

    def to_ruleset(self):
        from ..services.rules_engine import RuleSet

        return RuleSet.from_dict(self.to_dict())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MatchRules match={self.match_id} preset={self.preset}>"
