"""User model.

Authentication is out of scope for Phase 1, but matches are owned by a user so
the schema and API are ready for sign-in later. A local default user is created
on demand (see ``services/user_manager.py``).
"""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(160), unique=True)
    password_hash = db.Column(db.String(255))
    last_login_at = db.Column(db.DateTime(timezone=True))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    matches = db.relationship("Match", back_populates="owner")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} {self.display_name!r}>"
