"""Canonical geometry validation. Only bbox and point are supported; antimeridian crossing is rejected."""
from __future__ import annotations

from .errors import ApiError

MAX_SPAN_DEG = 10.0  # POWER regional endpoint maximum per axis (documented in error responses; enforced here too)
MIN_REGIONAL_SPAN_DEG = 2.0  # POWER regional requires >= 2 degrees per axis


def _num(v, name):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ApiError("invalid_geometry", f"{name} must be a number.")
    if f != f or f in (float("inf"), float("-inf")):
        raise ApiError("invalid_geometry", f"{name} must be finite.")
    return round(f, 4)


def canonical(geom: dict) -> dict:
    if not isinstance(geom, dict):
        raise ApiError("invalid_geometry", "Geometry must be an object.")
    t = geom.get("type")
    if t == "point":
        lon, lat = _num(geom.get("lon"), "lon"), _num(geom.get("lat"), "lat")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ApiError("invalid_geometry", "Point is outside valid longitude/latitude ranges.")
        return {"type": "point", "lon": lon, "lat": lat}
    if t == "bbox":
        w, s, e, n = (_num(geom.get(k), k) for k in ("west", "south", "east", "north"))
        if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
            raise ApiError("invalid_geometry", "Bounding box is outside valid longitude/latitude ranges.")
        if w >= e:
            raise ApiError(
                "antimeridian_unsupported",
                "West must be less than east. Boxes crossing the antimeridian are not supported; split the area.",
            )
        if s >= n:
            raise ApiError("invalid_geometry", "South must be less than north.")
        if (e - w) > MAX_SPAN_DEG or (n - s) > MAX_SPAN_DEG:
            raise ApiError("area_too_large", f"Each side of the box must be at most {MAX_SPAN_DEG:g} degrees.")
        return {"type": "bbox", "west": w, "south": s, "east": e, "north": n}
    raise ApiError("unsupported_geometry", "Only 'bbox' and 'point' geometries are supported.")


def is_regional_capable(geom: dict) -> bool:
    return (
        geom["type"] == "bbox"
        and (geom["east"] - geom["west"]) >= MIN_REGIONAL_SPAN_DEG
        and (geom["north"] - geom["south"]) >= MIN_REGIONAL_SPAN_DEG
    )


def centroid(geom: dict) -> tuple[float, float]:
    if geom["type"] == "point":
        return geom["lon"], geom["lat"]
    return (geom["west"] + geom["east"]) / 2, (geom["south"] + geom["north"]) / 2
