"""Series endpoints, including the derived dashboard."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services.series_manager import (
    create_series,
    get_series,
    list_series,
    update_series,
)
from ..security import require_series_access
from ..services.series_stats import series_dashboard
from ..utils.payload import int_arg, json_body
from ..utils.serializers import series_dict

bp = Blueprint("series", __name__, url_prefix="/api")


def _detail(series) -> dict:
    data = series_dict(series, include_matches=True)
    data.update(series_dashboard(series))
    return data


@bp.get("/series")
def list_all():
    limit = int_arg("limit", default=20, minimum=1, maximum=100)
    return jsonify({"data": [series_dict(series) for series in list_series(limit)]})


@bp.post("/series")
def create():
    series = create_series(json_body())
    return jsonify({"data": _detail(series)}), 201


@bp.get("/series/<int:series_id>")
def read(series_id: int):
    series = get_series(series_id)
    require_series_access(series)
    return jsonify({"data": _detail(series)})


@bp.get("/series/<int:series_id>/dashboard")
def dashboard(series_id: int):
    series = get_series(series_id)
    require_series_access(series)
    return jsonify({"data": _detail(series)})


@bp.patch("/series/<int:series_id>")
def edit(series_id: int):
    series = get_series(series_id)
    require_series_access(series)
    series = update_series(series, json_body())
    return jsonify({"data": _detail(series)})
