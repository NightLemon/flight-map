"""Limited, explicit IF/TF nominal geometry; never bridge an unsupported leg."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

from flightmap_schema import ResearchRecord
from geographiclib.geodesic import Geodesic

NOTICE = (
    "IF points and TF nominal WGS84 geodesics only; "
    "these lines do not predict the complete flown turn trajectory."
)
MAX_STEP_METERS = 1852.0
_POSITION_MASK = Geodesic.LATITUDE | Geodesic.LONGITUDE | Geodesic.LONG_UNROLL


def _point(leg: ResearchRecord) -> tuple[float, float] | None:
    if leg.properties.get("fix_resolution") != "unique":
        return None
    fix = leg.properties.get("resolved_fix")
    if not isinstance(fix, dict) or not fix.get("id"):
        return None
    lat, lon = fix.get("latitude"), fix.get("longitude")
    if any(isinstance(value, bool) or not isinstance(value, (float, int)) for value in (lat, lon)):
        return None
    if not all(math.isfinite(value) for value in (lat, lon)):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return float(lon), float(lat)


def _longitude(longitude: float) -> float:
    return (longitude + 180.0) % 360.0 - 180.0


def nominal_geodesic(start: tuple[float, float], end: tuple[float, float]) -> dict[str, Any]:
    """Return lon/lat GeoJSON sampled at <= 1 NM, split exactly at the antimeridian."""
    for lon, lat in (start, end):
        if not math.isfinite(lon) or not math.isfinite(lat) or not (
            -180 <= lon <= 180 and -90 <= lat <= 90
        ):
            raise ValueError("Geodesic endpoints must be finite WGS84 coordinates")
    line = Geodesic.WGS84.InverseLine(start[1], start[0], end[1], end[0])
    count = max(1, math.ceil(line.s13 / MAX_STEP_METERS))
    samples = [
        (distance, line.Position(distance, _POSITION_MASK))
        for distance in (line.s13 * index / count for index in range(count + 1))
    ]
    first = samples[0][1]
    segments: list[list[list[float]]] = [[[_longitude(first["lon2"]), first["lat2"]]]]
    for (previous_distance, previous), (distance, point) in pairwise(samples):
        lon, previous_lon = _longitude(point["lon2"]), _longitude(previous["lon2"])
        if abs(lon - previous_lon) > 180:
            increasing = point["lon2"] > previous["lon2"]
            zone = math.floor((previous["lon2"] + 180) / 360)
            boundary = (180 if increasing else -180) + 360 * zone
            lower, upper = previous_distance, distance
            for _ in range(60):
                middle = (lower + upper) / 2
                middle_lon = line.Position(middle, _POSITION_MASK)["lon2"]
                if (middle_lon < boundary) == increasing:
                    lower = middle
                else:
                    upper = middle
            latitude = line.Position((lower + upper) / 2, _POSITION_MASK)["lat2"]
            edge = 180.0 if increasing else -180.0
            boundary_point = [edge, latitude]
            if segments[-1][-1] != boundary_point:
                segments[-1].append(boundary_point)
            segments.append([[-edge, latitude]])
        next_point = [lon, point["lat2"]]
        if segments[-1][-1] != next_point:
            segments[-1].append(next_point)
    segments = [segment for segment in segments if len(segment) > 1]
    # Coincident endpoints still produce a valid two-position nominal LineString.
    if not segments:
        coordinate = [_longitude(start[0]), start[1]]
        segments = [[coordinate, list(coordinate)]]
    if len(segments) == 1:
        return {"type": "LineString", "coordinates": segments[0]}
    return {"type": "MultiLineString", "coordinates": segments}


def geometry_for_legs(
    legs: list[ResearchRecord], branch_id: str | None = None
) -> dict[str, Any]:
    """Consume original leg order; selecting a branch must not make new adjacency.

    Only ``fix_resolution='unique'`` plus a valid ``resolved_fix`` dictionary
    authorizes point use. A TF must immediately follow a successfully rendered
    IF/TF in the same procedure and named branch. We intentionally do not sort,
    remove failures, or infer branches from transition names.
    """
    features: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    previous: ResearchRecord | None = None
    previous_point: tuple[float, float] | None = None
    previous_supported = False
    seen: set[str] = set()
    for leg in legs:
        point = _point(leg)
        terminator = leg.properties.get("path_terminator", "")
        reason = None
        geometry = None
        if leg.id in seen:
            reason = "duplicate-leg-id"
        elif leg.kind != "leg":
            reason = "not-a-program-leg"
        elif terminator not in {"IF", "TF"}:
            reason = "unsupported-path-terminator"
        elif point is None:
            reason = "unresolved-or-invalid-fix"
        elif terminator == "IF":
            geometry = {"type": "Point", "coordinates": list(point)}
        elif previous is None:
            reason = "missing-previous-leg"
        elif not leg.branch_id or (
            leg.branch_id != previous.branch_id or leg.parent_id != previous.parent_id
        ):
            reason = "branch-boundary"
        elif (
            leg.sequence is not None
            and previous.sequence is not None
            and leg.sequence <= previous.sequence
        ):
            reason = "invalid-original-order"
        elif not previous_supported or previous_point is None:
            reason = "previous-leg-not-supported"
        else:
            geometry = nominal_geodesic(previous_point, point)

        selected = branch_id is None or leg.branch_id == branch_id
        if selected:
            if geometry is not None:
                features.append(
                    {
                        "type": "Feature",
                        "id": leg.id,
                        "geometry": geometry,
                        "properties": {
                            "leg_id": leg.id,
                            "parent_id": leg.parent_id,
                            "branch_id": leg.branch_id,
                            "path_terminator": terminator,
                            "status": "nominal",
                        },
                    }
                )
            else:
                gap = {"leg_id": leg.id, "branch_id": leg.branch_id, "reason": reason}
                if point is not None:
                    gap["coordinates"] = list(point)
                gaps.append(gap)
        seen.add(leg.id)
        previous, previous_point = leg, point
        previous_supported = geometry is not None
    return {"type": "FeatureCollection", "features": features, "gaps": gaps, "notice": NOTICE}
