"""Validation for NASR research-2; research-1 keeps its original airport-only meaning."""

import math
import re
from decimal import Decimal

from .research import Provenance, ResearchRecord
from .snapshots import ResearchSnapshot

LAYER_KINDS = {
    "airports": "airport",
    "runways": "runway",
    "navaids": "navaid",
    "waypoints": "waypoint",
    "airways": "airway",
    "communications": "communication",
}
KIND_LAYERS = {kind: layer for layer, kind in LAYER_KINDS.items()}


def check_capabilities(snapshot, report):
    caps = snapshot.capabilities
    if snapshot.schema_version == "research-1":
        if caps != ["airports"] or set(report.capabilities) != {"airports"}:
            raise ValueError("Research capabilities disagree with report")
    elif set(caps) != set(report.capabilities) or len(set(report.capabilities)) != len(
        report.capabilities
    ):
        raise ValueError("Research capabilities disagree with report")


def coordinate(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(type(v) in (int, float) and math.isfinite(v) for v in value)
        and -180 <= value[0] <= 180
        and -90 <= value[1] <= 90
    )


def check_record(record: ResearchRecord, snapshot: ResearchSnapshot):
    if record.provenance.asset_sha256 not in snapshot.input_sha256:
        raise ValueError("Record input provenance differs")
    allowed = {LAYER_KINDS[cap] for cap in snapshot.capabilities if cap in LAYER_KINDS}
    if record.kind not in allowed:
        raise ValueError("Record kind differs from snapshot capabilities")
    geometry = record.geometry or {}
    if record.kind in {"airport", "navaid", "waypoint"}:
        if geometry.get("type") != "Point" or not coordinate(geometry.get("coordinates")):
            raise ValueError("Invalid point coordinates")
    elif record.kind in {"runway", "airway"}:
        coords = geometry.get("coordinates")
        if (
            geometry.get("type") != "LineString"
            or not isinstance(coords, list)
            or len(coords) < 2
            or not all(coordinate(point) for point in coords)
        ):
            raise ValueError("Invalid line coordinates")
    elif record.kind == "communication":
        frequency = record.properties.get("frequency")
        if (
            record.geometry is not None
            or not isinstance(frequency, str)
            or not re.fullmatch(r"\d+(?:\.\d+)?", frequency)
            or Decimal(frequency) <= 0
            or record.properties.get("unit") not in {"MHz", "kHz"}
            or not isinstance(record.properties.get("service"), str)
            or not record.properties["service"].strip()
            or not isinstance(record.properties.get("remarks", ""), str)
        ):
            raise ValueError("Invalid airport communication frequency")
    if record.kind in {"runway", "communication"} and not record.airport_id:
        raise ValueError("Airport child is missing its airport identity")
    supporting = record.properties.get("supporting_provenance", [])
    if not isinstance(supporting, list):
        raise ValueError("Invalid supporting provenance")
    for value in supporting:
        evidence = Provenance.model_validate(value)
        if evidence.asset_sha256 not in snapshot.input_sha256:
            raise ValueError("Supporting provenance is outside the snapshot input set")
