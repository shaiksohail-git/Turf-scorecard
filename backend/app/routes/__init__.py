"""API blueprint registration."""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .auth import bp as auth_bp
    from .health import bp as health_bp
    from .matches import bp as matches_bp
    from .rules import bp as rules_bp
    from .scoring import bp as scoring_bp
    from .series import bp as series_bp
    from .stats import bp as stats_bp
    from .users import bp as users_bp

    for blueprint in (
        auth_bp,
        health_bp,
        rules_bp,
        matches_bp,
        scoring_bp,
        series_bp,
        stats_bp,
        users_bp,
    ):
        app.register_blueprint(blueprint)
