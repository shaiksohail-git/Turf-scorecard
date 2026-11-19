"""Flask application factory."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from .extensions import cors, db, migrate
from .errors import register_error_handlers
from .security import install_security


def create_app(config_object=None, **overrides) -> Flask:
    """Build a configured Flask application.

    ``config_object`` defaults to :class:`config.Config`; tests pass their own
    class to point at a throwaway database.
    """
    from config import Config

    config_cls = config_object or Config
    frontend_dir = Path(getattr(config_cls, "FRONTEND_DIR", Config.FRONTEND_DIR))

    app = Flask(__name__, static_folder=str(frontend_dir), static_url_path="")
    app.config.from_object(config_cls)
    app.config.update(overrides)
    app.json.sort_keys = False

    app.static_folder = str(app.config.get("FRONTEND_DIR", frontend_dir))

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Config.MIGRATIONS_DIR), render_as_batch=False)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=bool(app.config.get("CORS_SUPPORTS_CREDENTIALS", False)),
    )

    register_error_handlers(app)
    install_security(app)

    from .routes import register_blueprints

    register_blueprints(app)

    @app.get("/")
    def index():
        """Serve the static frontend shell."""
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.get("/login")
    def login_page():
        return send_from_directory(app.static_folder, "pages/login.html")

    _register_cli(app)
    return app


def _register_cli(app: Flask) -> None:
    """Developer helpers for local databases (Alembic owns real migrations)."""

    @app.cli.command("init-db")
    def init_db() -> None:
        """Create tables directly from the models (local development only)."""
        from . import models  # noqa: F401  (registers metadata)

        db.create_all()
        print("Database tables created from models.")

    @app.cli.command("seed-demo")
    def seed_demo() -> None:
        """Create a ready-to-score Custom Turf match with two 5-player teams."""
        from .services.match_manager import create_match, start_match
        from .extensions import db as _db

        match = create_match(
            {
                "preset": "custom_turf",
                "venue": "Local turf",
                "team_a": {
                    "name": "Green Caps",
                    "players": ["Arun", "Bilal", "Chetan", "Danish", "Eshan"],
                },
                "team_b": {
                    "name": "Night Riders",
                    "players": ["Farid", "Gopal", "Harish", "Imran", "Jatin"],
                },
                "toss": {"winner": "a", "decision": "bat"},
            }
        )
        start_match(match)
        _db.session.commit()
        print(f"Created match {match.id} (Custom Turf, 6 overs).")
