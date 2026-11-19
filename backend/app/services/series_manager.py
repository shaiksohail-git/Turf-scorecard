"""Series management.

A series groups matches and carries the roster/planned length chosen when it
was created. Editing a series never rewrites a match, its rules snapshot or its
statistics; the planned length is only a target and may never drop below the
number of completed matches already linked to the series.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import select

from ..errors import NotFoundError, ValidationError
from ..extensions import db
from ..models import Series
from .auth_manager import current_user
from .rules_engine import PRESETS
from .user_manager import get_default_user
from .series_stats import series_dashboard

_MISSING = object()
_MAX_PLANNED_MATCHES = 1000


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(
            f"{field} must be an ISO date (YYYY-MM-DD).", details={"field": field}
        ) from exc


def _parse_planned(value: Any, field: str = "planned_matches") -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(
            f"{field} must be an integer.", details={"field": field}
        )
    if value < 0 or value > _MAX_PLANNED_MATCHES:
        raise ValidationError(
            f"{field} must be between 0 and {_MAX_PLANNED_MATCHES}.",
            details={"field": field, "min": 0, "max": _MAX_PLANNED_MATCHES},
        )
    return value


def _clean_players(raw: Any, field: str) -> list[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValidationError(
            f"{field} must be a list of player names.", details={"field": field}
        )
    players: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(
                f"{field} may only contain non-empty player names.",
                details={"field": field},
            )
        name = item.strip()[:80]
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            players.append(name)
    if len(players) > 30:
        raise ValidationError(
            f"{field} cannot contain more than 30 players.",
            details={"field": field, "max": 30},
        )
    return players


def _team_fields(
    payload: Mapping[str, Any], side: str
) -> tuple[str | None, list[str]] | None:
    """Read either a nested team object or the flat team_* fields."""
    nested = payload.get(f"team_{side}", _MISSING)
    flat_name = payload.get(f"team_{side}_name", _MISSING)
    flat_players = payload.get(f"team_{side}_players", _MISSING)
    if nested is _MISSING and flat_name is _MISSING and flat_players is _MISSING:
        return None
    if nested is not _MISSING and nested is not None:
        if not isinstance(nested, Mapping):
            raise ValidationError(
                f"team_{side} must be an object.", details={"field": f"team_{side}"}
            )
        if flat_name is not _MISSING or flat_players is not _MISSING:
            raise ValidationError(
                f"Use either team_{side} or the flat team_{side}_* fields, not both.",
                details={"field": f"team_{side}"},
            )
        name = nested.get("name")
        players = nested.get("players")
    else:
        name = None if flat_name is _MISSING else flat_name
        players = None if flat_players is _MISSING else flat_players

    clean_name = str(name).strip()[:80] if name not in (None, "") else None
    clean_players = _clean_players(players, f"team_{side}_players")
    if clean_players and not clean_name:
        raise ValidationError(
            f"A team name is required when team_{side} has players.",
            details={"field": f"team_{side}_name"},
        )
    return clean_name, clean_players


def _validate_teams(
    team_a: tuple[str | None, list[str]],
    team_b: tuple[str | None, list[str]],
) -> None:
    a_name, a_players = team_a
    b_name, b_players = team_b
    if (a_name or a_players) and not (b_name or b_players):
        raise ValidationError(
            "Both teams are required when a series roster is selected.",
            details={"field": "team_b"},
        )
    if (b_name or b_players) and not (a_name or a_players):
        raise ValidationError(
            "Both teams are required when a series roster is selected.",
            details={"field": "team_a"},
        )
    if a_name and b_name and a_name.casefold() == b_name.casefold():
        raise ValidationError(
            "The two series teams must have different names.",
            details={"field": "team_b_name"},
        )


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and end_date < start_date:
        raise ValidationError(
            "end_date cannot be before start_date.", details={"field": "end_date"}
        )


def _completed_count(series: Series) -> int:
    return sum(1 for match in series.matches if match.status == "completed")


def _validate_plan(planned: int, series: Series | None = None) -> None:
    if series is None:
        return
    completed = _completed_count(series)
    if planned < completed:
        raise ValidationError(
            "The planned series length cannot be lower than the number of completed matches.",
            details={
                "field": "planned_matches",
                "minimum": completed,
                "completed_matches": completed,
            },
        )


def _preset_value(payload: Mapping[str, Any]) -> str | None:
    preset = payload.get("preset")
    if preset is None:
        return None
    if not isinstance(preset, str) or preset not in PRESETS:
        raise ValidationError(
            "Unknown rules preset.", details={"field": "preset", "allowed": list(PRESETS)}
        )
    return preset


def create_series(payload: Mapping[str, Any]) -> Series:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.", code="invalid_body")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("A series name is required.", details={"field": "name"})

    preset = _preset_value(payload)
    start_date = _parse_date(payload.get("start_date"), "start_date")
    end_date = _parse_date(payload.get("end_date"), "end_date")
    _validate_dates(start_date, end_date)

    planned = _parse_planned(payload.get("planned_matches"))
    team_a = _team_fields(payload, "a")
    team_b = _team_fields(payload, "b")
    if team_a is None and team_b is None:
        team_a = (None, [])
        team_b = (None, [])
    elif team_a is None:
        team_a = (None, [])
    elif team_b is None:
        team_b = (None, [])
    _validate_teams(team_a, team_b)

    from flask import has_request_context

    signed_in = current_user(optional=True) if has_request_context() else None
    owner = signed_in or get_default_user()
    series = Series(
        owner_id=owner.id if owner is not None else None,
        name=name.strip()[:120],
        format=str(payload.get("format") or preset or "custom")[:24],
        preset=preset,
        planned_matches=planned,
        team_a_name=team_a[0],
        team_a_players=team_a[1] or None,
        team_b_name=team_b[0],
        team_b_players=team_b[1] or None,
        start_date=start_date,
        end_date=end_date,
        notes=(str(payload.get("notes")) if payload.get("notes") else None),
    )
    db.session.add(series)
    db.session.commit()
    return series


def update_series(series: Series, payload: Mapping[str, Any]) -> Series:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.", code="invalid_body")

    if "name" in payload:
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("A series name is required.", details={"field": "name"})
        series.name = name.strip()[:120]

    if "preset" in payload:
        series.preset = _preset_value(payload)
        if "format" not in payload and series.preset:
            series.format = series.preset
    if "format" in payload:
        raw_format = payload.get("format")
        series.format = str(raw_format).strip()[:24] if raw_format else "custom"

    start_date = (
        _parse_date(payload.get("start_date"), "start_date")
        if "start_date" in payload
        else series.start_date
    )
    end_date = (
        _parse_date(payload.get("end_date"), "end_date")
        if "end_date" in payload
        else series.end_date
    )
    _validate_dates(start_date, end_date)
    series.start_date = start_date
    series.end_date = end_date

    if "notes" in payload:
        notes = payload.get("notes")
        series.notes = str(notes) if notes else None

    if "planned_matches" in payload:
        planned = _parse_planned(payload.get("planned_matches"))
        _validate_plan(planned, series)
        series.planned_matches = planned

    team_a = _team_fields(payload, "a")
    team_b = _team_fields(payload, "b")
    if team_a is not None or team_b is not None:
        current_a = (series.team_a_name, list(series.team_a_players or []))
        current_b = (series.team_b_name, list(series.team_b_players or []))
        next_a = team_a if team_a is not None else current_a
        next_b = team_b if team_b is not None else current_b
        _validate_teams(next_a, next_b)
        series.team_a_name = next_a[0]
        series.team_a_players = next_a[1] or None
        series.team_b_name = next_b[0]
        series.team_b_players = next_b[1] or None

    db.session.commit()
    return series


def list_series(limit: int = 20) -> list[Series]:
    rows = db.session.execute(
        select(Series).order_by(Series.id.desc()).limit(limit)
    ).scalars()
    result = list(rows)
    from flask import current_app

    if not current_app.config.get("AUTH_REQUIRED", False):
        return result
    signed_in = current_user(optional=True)
    if signed_in is None:
        return []
    return [series for series in result if series.owner_id in (None, signed_in.id)]


def get_series(series_id: int) -> Series:
    series = db.session.get(Series, series_id)
    if series is None:
        raise NotFoundError("Series not found.", details={"series_id": series_id})
    return series


def get_series_dashboard(series: Series) -> dict[str, Any]:
    """Return the derived dashboard, without mutating the series or matches."""
    return series_dashboard(series)
