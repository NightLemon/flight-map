"""CIFP structural inspection without claiming verified navigation semantics.

Field positions are referenced in docs/cifp-support.md with the upstream MIT
notice. No agreement is accepted, remote data fetched, or production capability
enabled here. In particular, record-cycle values are not product effective dates.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from urllib.parse import quote
from zipfile import ZipFile, is_zipfile

from flightmap_schema import ParseResult, Provenance, ResearchRecord, ValidationReport

README_URL = "https://aeronav.faa.gov/Upload_313-d/cifp/CIFP%20Readme.pdf"
FIELD_REFERENCE = (
    "https://github.com/jack-laverty/arinc424/tree/"
    "f8c65377e38551c15d6429658bdfde891af1c01c/src/arinc424/definitions"
)
MAX_MEMBER_BYTES = 512 * 1024 * 1024
_FAMILIES = {"PA", "PG", "EA", "PC", "D ", "DB", "ER", "PD", "PE", "PF"}
_PROCEDURES = {"PD": "SID", "PE": "STAR", "PF": "APPROACH"}
_MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August",
         "September", "October", "November", "December"), start=1
    )
}


def parse_coordinate(value: str, axis: str) -> float:
    """Decode an explicitly typed ARINC DDMMSSss / DDDMMSSss field."""
    if axis not in {"latitude", "longitude"}:
        raise ValueError("axis must be latitude or longitude")
    width, hemispheres, maximum = (2, "NS", 90) if axis == "latitude" else (3, "EW", 180)
    if not re.fullmatch(rf"[{hemispheres}][0-9]{{{width + 6}}}", value):
        raise ValueError(f"Invalid {axis} field: {value!r}")
    degrees = int(value[1:width + 1])
    minutes = int(value[width + 1:width + 3])
    seconds = int(value[width + 3:width + 7]) / 100
    if minutes >= 60 or seconds >= 60 or degrees > maximum:
        raise ValueError(f"Out-of-range {axis} field: {value!r}")
    if degrees == maximum and (minutes or seconds):
        raise ValueError(f"Out-of-range {axis} boundary: {value!r}")
    result = degrees + minutes / 60 + seconds / 3600
    return -result if value[0] in "SW" else result


def parse_cifp_validity(text: str) -> dict[str, Any]:
    """Read the product interval printed in a CIFP Readme, without default times."""
    volume = re.findall(r"\bVolume\s*:\s*([0-9]{4})\b", text, re.IGNORECASE)
    date = r"([0-9]{4})Z\s+([0-9]{1,2})\s+([A-Za-z]+)\s+([0-9]{4})"
    intervals = re.findall(
        rf"\bEffective\s*:\s*{date}\s+To\s*:\s*{date}", text, re.IGNORECASE
    )
    if len(volume) != 1 or len(intervals) != 1:
        raise ValueError("CIFP Readme must contain one unambiguous volume and precise interval")

    def timestamp(parts: tuple[str, ...]) -> datetime:
        time, day, month, year = parts
        month_number = _MONTHS.get(month.lower())
        if month_number is None:
            raise ValueError(f"Unknown Readme month: {month}")
        return datetime(int(year), month_number, int(day), int(time[:2]), int(time[2:]), tzinfo=UTC)

    valid_from, valid_to = timestamp(intervals[0][:4]), timestamp(intervals[0][4:])
    if valid_from >= valid_to:
        raise ValueError("CIFP Readme interval must be nonempty and increasing")
    return {
        "airac": volume[0], "valid_from": valid_from, "valid_to": valid_to,
        "evidence": [README_URL, f"Readme Volume {volume[0]}: {valid_from.isoformat()} "
                     f"through {valid_to.isoformat()}"],
    }


@dataclass(frozen=True)
class CifpFrame:
    line_number: int
    raw: str
    family: str | None
    error: str | None = None


def iter_cifp_frames(stream: BinaryIO) -> Iterator[CifpFrame]:
    """Preserve original line positions, trailing spaces, and malformed records."""
    for number, value in enumerate(stream, start=1):
        content = value.rstrip(b"\r\n")
        try:
            raw = content.decode("ascii")
        except UnicodeDecodeError:
            yield CifpFrame(number, content.decode("ascii", errors="backslashreplace"), None,
                            "CIFP data frame is not ASCII")
            continue
        if len(raw) != 132:
            yield CifpFrame(number, raw, None, f"Expected 132 characters; found {len(raw)}")
        elif raw.startswith("HDR"):
            yield CifpFrame(number, raw, "header")
        elif raw[0] not in {"S", "T"}:
            yield CifpFrame(number, raw, None, "Unknown data record prefix")
        else:
            family = raw[4] + raw[12] if raw[4] in {"P", "H"} else raw[4:6]
            yield CifpFrame(number, raw, family)


def _key(*parts: str) -> str:
    return "cifp:" + ":".join(quote(value, safe="") or "_" for value in parts)


def _primary_fields(frame: CifpFrame) -> tuple[str, dict[str, Any]]:
    """Return candidate fields, retaining every raw value as an uninterpreted string."""
    raw, family = frame.raw, frame.family
    values = {
        "raw": raw, "family": family, "area": raw[1:4], "scope": raw[6:10],
        "region": raw[10:12], "file_record_number": raw[123:128],
        "record_changed_cycle": raw[128:132], "support_state": "unverified",
        "field_reference": FIELD_REFERENCE,
    }
    continuation = raw[38] if family in {"ER", "PD", "PE", "PF"} else raw[21]
    if continuation not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        raise ValueError(f"Invalid continuation record number: {continuation!r}")
    values["continuation_record_no"] = continuation
    values["is_continuation"] = continuation not in {"0", "1"}
    if family == "PA":
        identifier = raw[6:10].strip()
        values.update(faa_identifier=raw[13:16], name=raw[93:123])
    elif family in {"PG", "EA", "PC"}:
        identifier = raw[13:18].strip()
        values.update(point_region=raw[19:21])
        if family == "PG":
            values.update(name=raw[101:123], length=raw[22:27], magnetic_bearing=raw[27:31])
        else:
            values.update(name=raw[98:123], waypoint_type=raw[26:29], waypoint_usage=raw[29:31])
    elif family in {"D ", "DB"}:
        identifier = raw[13:17].strip()
        values.update(point_region=raw[19:21], name=raw[93:123], frequency=raw[22:27])
    elif family in {"ER", "PD", "PE", "PF"}:
        identifier = raw[13:18 if family == "ER" else 19].strip()
        values.update(
            sequence_raw=raw[25:29] if family == "ER" else raw[26:29],
            fix_identifier=raw[29:34], fix_region=raw[34:36], fix_section=raw[36:38],
            fix_resolution="unverified",
        )
        if family == "ER":
            values.update(route_type=raw[44], direction_restriction=raw[46],
                          waypoint_description=raw[39:43])
        else:
            values.update(route_type=raw[19], transition_identifier=raw[20:25],
                          procedure_type=_PROCEDURES[family])
            values["branch_candidate_key"] = _key(raw[19], raw[20:25])
            values["branch_status"] = "unverified-final-missed-partition"
    else:
        raise ValueError("Family has no reviewed structural definition")
    if not identifier:
        raise ValueError("Required record identifier is blank")
    if values["is_continuation"]:
        index = 39 if family in {"ER", "PD", "PE", "PF"} else 22
        # Primary-looking bytes in continuation payloads must not become positions or legs.
        values = {key: value for key, value in values.items() if key in {
            "raw", "family", "area", "scope", "region", "file_record_number",
            "record_changed_cycle", "support_state", "field_reference", "continuation_record_no",
            "is_continuation", "sequence_raw", "procedure_type", "route_type",
            "transition_identifier", "branch_candidate_key", "branch_status"
        }}
        values["application_type"] = raw[index]
    elif family in {"PA", "PG", "EA", "PC", "D ", "DB"}:
        values.update(latitude_raw=raw[32:41], longitude_raw=raw[41:51])
        if raw[32:51].strip():
            values["coordinate_candidate"] = {
                "latitude": parse_coordinate(raw[32:41], "latitude"),
                "longitude": parse_coordinate(raw[41:51], "longitude"),
            }
    elif family in _PROCEDURES:
        values.update(
            waypoint_description=raw[39:43], path_terminator=raw[47:49],
            altitude_description=raw[82], altitude_1=raw[84:89], altitude_2=raw[89:94],
            speed_limit=raw[99:102], route_qualifier_1=raw[118], route_qualifier_2=raw[119],
            turn_direction=raw[43], magnetic_course=raw[70:74],
        )
    return identifier, values


def _record(frame: CifpFrame, asset_sha256: str, member: str | None) -> ResearchRecord:
    identifier, values = _primary_fields(frame)
    family = frame.family
    provenance = Provenance(asset_sha256=asset_sha256, member=member, line=frame.line_number,
                            locator=f"{member or 'file'}:line:{frame.line_number}")
    identity = _key(family or "", values["area"], values["scope"], values["region"],
                    values.get("point_region", ""), identifier)
    parent_id = None
    sequence = None
    if family in _PROCEDURES or family == "ER":
        sequence_raw = values["sequence_raw"].strip()
        if not re.fullmatch(r"[0-9]+", sequence_raw):
            raise ValueError(f"Invalid record sequence: {sequence_raw!r}")
        sequence = int(sequence_raw)
        parent_id = identity
        identity += ":" + _key(
            values.get("route_type", ""), values.get("transition_identifier", ""), sequence_raw
        )
    if values["is_continuation"]:
        identity += f":continuation:{values['continuation_record_no']}"
    kind = {"PA": "airport", "PG": "runway", "EA": "waypoint", "PC": "waypoint",
            "D ": "navaid", "DB": "navaid", "ER": "airway",
            "PD": "leg", "PE": "leg", "PF": "leg"}[family]
    return ResearchRecord(
        id=identity, kind=kind, identifier=identifier,
        name=values.get("name", "").strip() or identifier,
        airport_ident=values["scope"].strip() if (family or "").startswith("P") else None,
        parent_id=parent_id, sequence=sequence, properties=values, provenance=provenance,
    )


def _parse_stream(stream: BinaryIO, asset_sha256: str, member: str | None) -> ParseResult:
    records: list[ResearchRecord] = []
    issues: list[dict[str, Any]] = [{
        "code": "cifp-evidence-incomplete", "severity": "error",
        "message": "Structural fields only: real samples, references, continuation and procedure "
                   "branch semantics require independent verification before publication.",
        "context": {"evidence": "docs/cifp-support.md", "supported_capabilities": [],
                    "required_action": "obtain-official-file-and-approve-golden-records"},
    }]
    unsupported = errors = count = 0
    identities: set[str] = set()
    procedures: dict[str, ResearchRecord] = {}
    for frame in iter_cifp_frames(stream):
        count += 1
        context = {"line": frame.line_number, "member": member, "raw": frame.raw,
                   "asset_sha256": asset_sha256}
        if frame.error:
            errors += 1
            issues.append({"code": "cifp-invalid-frame", "severity": "error",
                           "message": frame.error, "context": context})
            continue
        if frame.family not in _FAMILIES:
            unsupported += 1
            issues.append({"code": "cifp-unsupported-family", "severity": "warning",
                           "message": f"Unverified record family: {frame.family}",
                           "context": context})
            continue
        try:
            record = _record(frame, asset_sha256, member)
        except ValueError as exc:
            errors += 1
            issues.append({"code": "cifp-invalid-fields", "severity": "error",
                           "message": str(exc), "context": context})
            continue
        if record.id in identities:
            errors += 1
            issues.append({"code": "cifp-duplicate-identity", "severity": "error",
                           "message": "Duplicate scoped identity; records were not merged",
                           "record_key": record.id, "context": context})
            record = record.model_copy(update={"id": f"{record.id}:duplicate:{frame.line_number}"})
        else:
            unsupported += 1
        identities.add(record.id)
        records.append(record)
        if record.kind == "leg" and record.parent_id not in procedures:
            procedures[record.parent_id] = ResearchRecord(
                id=record.parent_id, kind="procedure", name=record.identifier,
                identifier=record.identifier, airport_ident=record.airport_ident,
                properties={"procedure_type": record.properties["procedure_type"],
                            "support_state": "unverified", "chart_association": "unconfirmed"},
                provenance=record.provenance,
            )
    if count == 0:
        issues.append({"code": "cifp-empty-file", "severity": "error",
                       "message": "The selected CIFP file contains no records"})
    return ParseResult(
        records=list(procedures.values()) + records,
        report=ValidationReport(input_count=count, success_count=0, unsupported_count=unsupported,
                                error_count=errors, issues=issues, capabilities=[]),
    )


def parse_cifp(path: Path, asset_sha256: str, member: str | None = None) -> ParseResult:
    """Inspect a local raw file or selected ZIP member, always yielding a blocked candidate."""
    path = Path(path)
    # Validate the evidence key even when the input contains no supported frames.
    Provenance(asset_sha256=asset_sha256, locator="input")
    if is_zipfile(path):
        with ZipFile(path) as archive:
            candidates = [item for item in archive.infolist() if not item.is_dir() and (
                item.filename == member if member is not None
                else PurePosixPath(item.filename).name.upper() == "FAACIFP18"
            )]
            if len(candidates) != 1:
                raise ValueError("Select exactly one CIFP ZIP member in the import manifest")
            item = candidates[0]
            if item.flag_bits & 1 or item.file_size > MAX_MEMBER_BYTES:
                raise ValueError("Encrypted or oversized CIFP member is not accepted")
            with archive.open(item) as stream:
                return _parse_stream(stream, asset_sha256, item.filename)
    if member is not None:
        raise ValueError("member is only valid for ZIP inputs")
    if path.stat().st_size > MAX_MEMBER_BYTES:
        raise ValueError("CIFP input exceeds maximum size")
    with path.open("rb") as stream:
        return _parse_stream(stream, asset_sha256, None)
