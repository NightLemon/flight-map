"""Conservative, date-level NASR layers with original-row and join provenance.

Coordinates for airways come exclusively from the same-edition AWY2 product;
neither airport centres nor name-only NAV/FIX matches can complete a missing line.
The caller supplies the official edition evidence for the fixed-width asset,
which has no EFF_DATE field of its own.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from flightmap_schema import ParseResult, Provenance, ResearchRecord, ValidationReport

from .nasr import REQUIRED as AIRPORT_COLUMNS
from .nasr import parse_nasr

CAPABILITIES = ["airports", "runways", "navaids", "waypoints", "airways", "communications"]
SITE_KEY = ("SITE_NO", "SITE_TYPE_CODE")
RUNWAY_KEY = (*SITE_KEY, "RWY_ID")
ROUTE_KEY = ("REGULATORY", "AWY_LOCATION", "AWY_ID")
POINT_KEY = (*ROUTE_KEY, "POINT_SEQ")
COORD_COLUMNS = {"LAT_DECIMAL", "LONG_DECIMAL"}
TABLES = {
    "APT": {
        "APT_BASE.csv": AIRPORT_COLUMNS,
        "APT_RWY.csv": {"EFF_DATE", *RUNWAY_KEY, "ARPT_ID", "RWY_LEN", "RWY_WIDTH"},
        "APT_RWY_END.csv": {
            "EFF_DATE",
            *RUNWAY_KEY,
            "ARPT_ID",
            "RWY_END_ID",
            *COORD_COLUMNS,
            "LAT_DISPLACED_THR_DECIMAL",
            "LONG_DISPLACED_THR_DECIMAL",
            "DISPLACED_THR_LEN",
        },
    },
    "NAV": {"NAV_BASE.csv": {"EFF_DATE", "NAV_ID", "NAV_TYPE", "CITY", "NAME", *COORD_COLUMNS}},
    "FIX": {"FIX_BASE.csv": {"EFF_DATE", "FIX_ID", "ICAO_REGION_CODE", *COORD_COLUMNS}},
    "AWY": {
        "AWY_BASE.csv": {"EFF_DATE", *ROUTE_KEY, "AIRWAY_STRING"},
        "AWY_SEG_ALT.csv": {
            "EFF_DATE",
            *POINT_KEY,
            "FROM_POINT",
            "TO_POINT",
            "AWY_SEG_GAP_FLAG",
            "DOGLEG",
        },
    },
    "FRQ": {
        "FRQ.csv": {
            "EFF_DATE",
            "SERVICED_FACILITY",
            "SERVICED_SITE_TYPE",
            "SERVICED_STATE",
            "SERVICED_COUNTRY",
            "FREQ",
            "FREQ_USE",
            "SECTORIZATION",
            "REMARK",
        }
    },
}
PRIMARY = {
    "APT_BASE.csv",
    "APT_RWY.csv",
    "NAV_BASE.csv",
    "FIX_BASE.csv",
    "AWY_SEG_ALT.csv",
    "FRQ.csv",
}


@dataclass
class _Row:
    fields: dict[str, str]
    provenance: Provenance
    error: str | None = None

    def key(self, columns: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self.fields.get(column, "").strip() for column in columns)


class _Report:
    def __init__(self) -> None:
        self.success = 0
        self.unsupported = 0
        self.errors = 0
        self.primary: dict[str, int] = {}
        self.auxiliary_errors = 0
        self.groups: dict[tuple[str, str], dict] = {}

    def issue(
        self,
        code: str,
        message: str,
        row: _Row | None = None,
        *,
        severity: str = "warning",
        auxiliary: bool = False,
    ) -> None:
        if severity == "error":
            self.errors += 1
            self.auxiliary_errors += int(auxiliary)
        else:
            self.unsupported += int(not auxiliary)
        group = self.groups.setdefault(
            (code, severity),
            {
                "code": code,
                "severity": severity,
                "message": message,
                "context": {"count": 0, "examples": []},
            },
        )
        group["context"]["count"] += 1
        examples = group["context"]["examples"]
        if len(examples) < 3:
            sample = {"reason": message}
            if row is not None:
                sample["provenance"] = row.provenance.model_dump(mode="json")
                sample["identity"] = {
                    k: v
                    for k, v in row.fields.items()
                    if k
                    in {
                        *SITE_KEY,
                        "ARPT_ID",
                        "RWY_ID",
                        "RWY_END_ID",
                        "NAV_ID",
                        "NAV_TYPE",
                        "CITY",
                        "FIX_ID",
                        "ICAO_REGION_CODE",
                        *POINT_KEY,
                        "FROM_POINT",
                        "TO_POINT",
                        "SERVICED_FACILITY",
                        "SERVICED_SITE_TYPE",
                        "FREQ",
                        "FREQ_USE",
                    }
                }
            examples.append(sample)

    def invalid(self, row: _Row, *, auxiliary: bool = False) -> bool:
        if row.error is None:
            return False
        self.issue("nasr-invalid-record", row.error, row, severity="error", auxiliary=auxiliary)
        return True

    def result(self, records: list[ResearchRecord]) -> ParseResult:
        return ParseResult(
            records=records,
            report=ValidationReport(
                input_count=self.success + self.unsupported + self.errors,
                success_count=self.success,
                unsupported_count=self.unsupported,
                error_count=self.errors,
                capabilities=CAPABILITIES,
                issues=[
                    *self.groups.values(),
                    {
                        "code": "nasr-layer-accounting",
                        "severity": "info",
                        "message": "Primary table rows count once; auxiliary validation failures "
                        "count as additional input/error events. Valid supporting rows "
                        "do not count as separate features. Source archives retain all rows.",
                        "context": {
                            "primary_table_rows": self.primary,
                            "auxiliary_error_events": self.auxiliary_errors,
                        },
                    },
                ],
            ),
        )


def _csv_rows(stream, member: str, sha: str, expected: date, columns: set[str]) -> list[_Row]:
    reader = csv.DictReader(stream)
    headers = reader.fieldnames or []
    missing = columns - set(headers)
    if missing or len(headers) != len(set(headers)):
        raise ValueError(f"{member}: missing columns {sorted(missing)} or duplicate headers")
    rows = []
    for line, fields in enumerate(reader, 2):
        error = None
        if None in fields or any(value is None for value in fields.values()):
            error = "CSV field count differs from header"
        else:
            try:
                if datetime.strptime(fields["EFF_DATE"], "%Y/%m/%d").date() != expected:
                    raise ValueError("EFF_DATE conflicts with product validity evidence")
            except ValueError as exc:
                error = str(exc)
        # Malformed fields are never used for joins, but their source locator is retained.
        rows.append(
            _Row(
                {k: v or "" for k, v in fields.items() if k is not None},
                Provenance(
                    asset_sha256=sha,
                    member=member,
                    line=line,
                    locator=f"CSV record {line - 1} (header excluded)",
                ),
                error,
            )
        )
    return rows


def _load_tables(
    assets: dict[str, tuple[Path, str]], expected: date, report: _Report
) -> dict[str, list[_Row]]:
    tables: dict[str, list[_Row]] = {}
    for product, required in TABLES.items():
        if product not in assets:
            report.issue(
                "nasr-missing-asset", f"Missing asset {product}", severity="error", auxiliary=True
            )
            continue
        path, sha = assets[product]
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                for basename, columns in required.items():
                    matches = [n for n in names if n.rsplit("/", 1)[-1] == basename]
                    try:
                        if len(matches) != 1:
                            raise ValueError(f"Expected exactly one {basename}")
                        with archive.open(matches[0]) as raw:
                            rows = _csv_rows(
                                io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""),
                                matches[0],
                                sha,
                                expected,
                                columns,
                            )
                        tables[basename] = rows
                        if basename in PRIMARY:
                            report.primary[basename] = len(rows)
                        if not rows:
                            raise ValueError(f"Empty required table {basename}")
                    except (ValueError, UnicodeError, csv.Error) as exc:
                        report.issue(
                            "nasr-invalid-table", str(exc), severity="error", auxiliary=True
                        )
                # The edition guard also covers ancillary CSVs that are not emitted as layers.
                for member in names:
                    basename = member.rsplit("/", 1)[-1]
                    if not basename.endswith(".csv") or basename in required:
                        continue
                    with archive.open(member) as raw:
                        stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                        reader = csv.DictReader(stream)
                        if "EFF_DATE" not in (reader.fieldnames or []):
                            continue  # Official CSV structure dictionaries have no edition column.
                        for line, fields in enumerate(reader, 2):
                            error = None
                            try:
                                if None in fields or any(v is None for v in fields.values()):
                                    raise ValueError("CSV field count differs from header")
                                if (
                                    datetime.strptime(fields["EFF_DATE"], "%Y/%m/%d").date()
                                    != expected
                                ):
                                    raise ValueError(
                                        "EFF_DATE conflicts with product validity evidence"
                                    )
                            except ValueError as exc:
                                error = str(exc)
                            if error:
                                report.invalid(
                                    _Row(
                                        {},
                                        Provenance(
                                            asset_sha256=sha,
                                            member=member,
                                            line=line,
                                            locator=f"CSV record {line - 1} (header excluded)",
                                        ),
                                        error,
                                    ),
                                    auxiliary=True,
                                )
        except (OSError, zipfile.BadZipFile, UnicodeError, csv.Error) as exc:
            report.issue(
                "nasr-invalid-asset", f"{product}: {exc}", severity="error", auxiliary=True
            )
    return tables


def _index(rows: list[_Row], columns: tuple[str, ...]) -> dict[tuple[str, ...], _Row]:
    groups: dict[tuple[str, ...], list[_Row]] = defaultdict(list)
    for row in rows:
        key = row.key(columns)
        if not all(key):
            row.error = row.error or f"Empty required identity {columns}"
        groups[key].append(row)
    index = {}
    for key, matches in groups.items():
        if len(matches) > 1:
            for row in matches:
                row.error = row.error or f"Duplicate identity {columns}: {key}"
        elif matches[0].error is None:
            index[key] = matches[0]
    return index


def _number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite numeric value")
    return number


def _coordinate(
    row: dict[str, str], lat: str = "LAT_DECIMAL", lon: str = "LONG_DECIMAL"
) -> list[float]:
    latitude, longitude = _number(row[lat]), _number(row[lon])
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinate out of geographic range")
    return [longitude, latitude]


def _identifier(kind: str, key: tuple[str, ...]) -> str:
    return f"faa-aeronav:nasr:{kind}:" + ":".join(quote(part, safe="") for part in key)


def _properties(row: _Row, expected: date) -> dict:
    return {"raw_fields": row.fields, "effective_date": expected.isoformat()}


def _support(row: _Row) -> dict:
    return row.provenance.model_dump(mode="json")


def _airports(assets, tables, expected, report) -> list[ResearchRecord]:
    if "APT_BASE.csv" not in tables:
        return []
    rows = tables["APT_BASE.csv"]
    _index(rows, SITE_KEY)
    try:
        parsed = parse_nasr(*assets["APT"], expected)
    except (ValueError, OSError, zipfile.BadZipFile, csv.Error) as exc:
        for row in rows:
            row.error = row.error or str(exc)
        parsed = None
    records = []
    by_line = {r.provenance.line: r for r in parsed.records} if parsed else {}
    old_errors = (
        {
            int(i["record_key"].split(":")[-1]): i["message"]
            for i in parsed.report.issues
            if "record_key" in i
        }
        if parsed
        else {}
    )
    for row in rows:
        record = by_line.get(row.provenance.line)
        if record is None:
            row.error = row.error or old_errors.get(row.provenance.line, "Invalid airport")
        if not report.invalid(row):
            records.append(record)
            report.success += 1
    return records


def _runways(tables, airports, expected, report) -> list[ResearchRecord]:
    rows = tables.get("APT_RWY.csv", [])
    ends = tables.get("APT_RWY_END.csv", [])
    runway_index = _index(rows, RUNWAY_KEY)
    _index(ends, (*RUNWAY_KEY, "RWY_END_ID"))
    grouped: dict[tuple[str, ...], list[_Row]] = defaultdict(list)
    for end in ends:
        key = end.key(RUNWAY_KEY)
        if key not in runway_index:
            end.error = end.error or "Runway end has no unique valid parent runway"
        grouped[key].append(end)
        report.invalid(end, auxiliary=True)
    airport_index = {r.id: r for r in airports}
    records = []
    for row in rows:
        fields = row.fields
        airport_id = (
            f"faa-aeronav:nasr:airport:{fields.get('SITE_NO')}:{fields.get('SITE_TYPE_CODE')}"
        )
        airport = airport_index.get(airport_id)
        if airport is None or fields.get("ARPT_ID") != airport.airport_ident:
            row.error = row.error or "Runway has no matching airport SITE_NO/SITE_TYPE_CODE/ARPT_ID"
        try:
            length, width = (
                _number(fields["RWY_LEN"]),
                _number(fields["RWY_WIDTH"]),
            )
            if length < 0 or width < 0:
                raise ValueError("Negative runway dimension")
        except ValueError as exc:
            row.error = row.error or f"Invalid runway dimensions: {exc}"
        if report.invalid(row):
            continue
        if length == 0 or width == 0:
            report.issue(
                "nasr-runway-zero-dimension", "Zero-size runway has no supported line", row
            )
            continue
        key = row.key(RUNWAY_KEY)
        pair = grouped.get(key, [])
        designators = fields["RWY_ID"].split("/")
        if len(designators) != 2 or len(set(designators)) != 2:
            report.issue(
                "nasr-runway-nonlinear", "Runway has no distinct slash-separated ends", row
            )
            continue
        if (
            len(pair) != 2
            or any(end.error for end in pair)
            or {end.fields["RWY_END_ID"] for end in pair} != set(designators)
        ):
            report.issue(
                "nasr-runway-incomplete-ends", "Expected exactly two matching runway ends", row
            )
            continue
        pair.sort(key=lambda end: designators.index(end.fields["RWY_END_ID"]))
        if any(end.fields["ARPT_ID"] != fields["ARPT_ID"] for end in pair):
            report.issue(
                "nasr-runway-parent-mismatch",
                "Runway endpoint ARPT_ID mismatch",
                row,
                severity="error",
            )
            continue
        try:
            coordinates = [_coordinate(end.fields) for end in pair]
        except ValueError:
            report.issue(
                "nasr-runway-missing-coordinate", "Physical runway endpoint unavailable", row
            )
            continue
        displaced = []
        for end in pair:
            try:
                position = _coordinate(
                    end.fields, "LAT_DISPLACED_THR_DECIMAL", "LONG_DISPLACED_THR_DECIMAL"
                )
            except ValueError:
                position = None
            displaced.append(
                {
                    "runway_end_id": end.fields["RWY_END_ID"],
                    "coordinates": position,
                    "length_ft_raw": end.fields["DISPLACED_THR_LEN"],
                }
            )
        records.append(
            ResearchRecord(
                id=_identifier("runway", key),
                kind="runway",
                name=fields["RWY_ID"],
                identifier=fields["RWY_ID"],
                airport_id=airport_id,
                airport_ident=airport.airport_ident,
                geometry={"type": "LineString", "coordinates": coordinates},
                properties={
                    **_properties(row, expected),
                    "length_ft": length,
                    "width_ft": width,
                    "dimension_unit": "ft",
                    "surface": fields.get("SURFACE_TYPE_CODE", ""),
                    "endpoint_raw_fields": [end.fields for end in pair],
                    "displaced_thresholds": displaced,
                    "supporting_provenance": [_support(end) for end in pair],
                },
                provenance=row.provenance,
            )
        )
        report.success += 1
    return records


def _navigation(tables, expected, report) -> list[ResearchRecord]:
    records = []
    for table, kind, key_columns, identifier_column in [
        ("NAV_BASE.csv", "navaid", ("NAV_ID", "NAV_TYPE", "CITY"), "NAV_ID"),
        ("FIX_BASE.csv", "waypoint", ("FIX_ID", "ICAO_REGION_CODE"), "FIX_ID"),
    ]:
        rows = tables.get(table, [])
        _index(rows, key_columns)
        for row in rows:
            try:
                coordinates = _coordinate(row.fields)
            except ValueError as exc:
                row.error = row.error or f"Invalid navigation coordinate: {exc}"
            if report.invalid(row):
                continue
            fields = row.fields
            records.append(
                ResearchRecord(
                    id=_identifier(kind, row.key(key_columns)),
                    kind=kind,
                    name=fields.get("NAME") or fields[identifier_column],
                    identifier=fields[identifier_column],
                    geometry={"type": "Point", "coordinates": coordinates},
                    properties={
                        **_properties(row, expected),
                        "type": fields.get("NAV_TYPE", ""),
                        "state": fields.get("STATE_CODE", ""),
                        "country": fields.get("COUNTRY_CODE", ""),
                        "icao_region": fields.get("ICAO_REGION_CODE", ""),
                    },
                    provenance=row.provenance,
                )
            )
            report.success += 1
    return records


def _dms(value: str, latitude: bool) -> float:
    match = re.fullmatch(r"(\d{2,3})-(\d{2})-(\d{2}(?:\.\d+)?)([NSEW])", value.strip())
    if not match:
        raise ValueError("Invalid AWY2 DMS coordinate")
    degrees, minutes, seconds = map(float, match.groups()[:3])
    hemisphere = match[4]
    limit = 90 if latitude else 180
    if (
        hemisphere not in ("NS" if latitude else "EW")
        or minutes >= 60
        or seconds >= 60
        or degrees > limit
        or (degrees == limit and (minutes or seconds))
    ):
        raise ValueError("AWY2 DMS coordinate out of range")
    return (degrees + minutes / 60 + seconds / 3600) * (-1 if hemisphere in "SW" else 1)


def _awy_points(assets, report) -> dict[tuple[str, str, str], _Row]:
    if "AWY_POINTS" not in assets:
        report.issue(
            "nasr-missing-asset", "Missing AWY_POINTS asset", severity="error", auxiliary=True
        )
        return {}
    path, sha = assets["AWY_POINTS"]
    rows = []
    try:
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.rsplit("/", 1)[-1] == "AWY.txt"]
            if len(members) != 1:
                raise ValueError("Expected exactly one AWY.txt")
            with archive.open(members[0]) as stream:
                for line, raw in enumerate(io.TextIOWrapper(stream, encoding="ascii"), 1):
                    raw = raw.rstrip("\r\n")
                    if not raw.startswith("AWY2"):
                        continue
                    fields = {
                        "AWY_ID": raw[4:9].strip(),
                        "AWY_LOCATION": raw[9:10].strip() or "C",
                        "POINT_SEQ": raw[10:15].strip(),
                        "LAT_DMS": raw[83:97].strip(),
                        "LONG_DMS": raw[97:111].strip(),
                        "raw_record": raw,
                    }
                    error = None
                    if len(raw) != 315:
                        error = "AWY2 record must have exactly 315 characters"
                    elif fields["AWY_LOCATION"] not in {"C", "A", "H"}:
                        error = "Unsupported AWY2 scope"
                    try:
                        fields["POINT_SEQ"] = str(int(fields["POINT_SEQ"]))
                    except ValueError:
                        error = error or "Invalid AWY2 point sequence"
                    rows.append(
                        _Row(
                            fields,
                            Provenance(
                                asset_sha256=sha,
                                member=members[0],
                                line=line,
                                locator="AWY2 fixed-width point; key [4:15], "
                                "latitude [83:97], longitude [97:111]",
                            ),
                            error,
                        )
                    )
        if not rows:
            raise ValueError("No AWY2 point records")
    except (OSError, zipfile.BadZipFile, ValueError, UnicodeError) as exc:
        report.issue("nasr-invalid-awy-points", str(exc), severity="error", auxiliary=True)
    index = _index(rows, ("AWY_LOCATION", "AWY_ID", "POINT_SEQ"))
    for row in rows:
        report.invalid(row, auxiliary=True)
    return index


def _airways(tables, points, expected, report) -> list[ResearchRecord]:
    bases = tables.get("AWY_BASE.csv", [])
    base_index = _index(bases, ROUTE_KEY)
    for base in bases:
        report.invalid(base, auxiliary=True)
    fixed_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for scope, airway, sequence in points:
        fixed_groups[(scope, airway)].append(int(sequence))
    fixed_next = {}
    for group, sequences in fixed_groups.items():
        sequences.sort()
        fixed_next.update(
            {
                (*group, first): second
                for first, second in zip(sequences, sequences[1:], strict=False)
            }
        )
    rows = tables.get("AWY_SEG_ALT.csv", [])
    # Normalize sequence only for keys. Raw fields remain byte-for-byte CSV values.
    groups: dict[tuple[str, ...], list[_Row]] = defaultdict(list)
    for row in rows:
        try:
            if not re.fullmatch(r"[0-9]+", row.fields["POINT_SEQ"].strip()):
                raise ValueError("Invalid airway point sequence")
        except (KeyError, ValueError) as exc:
            row.error = row.error or str(exc)
        if row.key(ROUTE_KEY) not in base_index:
            row.error = row.error or "Airway point lacks a unique valid AWY_BASE route"
        if not row.fields.get("FROM_POINT", "").strip():
            row.error = row.error or "Empty FROM_POINT"
        groups[row.key(ROUTE_KEY)].append(row)
    _index(rows, POINT_KEY)
    records = []
    for group, members in groups.items():
        if any(not r.fields.get("POINT_SEQ", "").strip().isdigit() for r in members):
            # Ordering is unknowable; no lines may bridge this malformed intermediate row.
            for row in members:
                if not report.invalid(row):
                    report.issue(
                        "nasr-airway-unknown-order", "Route has a malformed point sequence", row
                    )
            continue
        members.sort(key=lambda r: int(r.fields["POINT_SEQ"]))
        sequence_counts = Counter(int(r.fields["POINT_SEQ"]) for r in members)
        for row in members:
            if sequence_counts[int(row.fields["POINT_SEQ"])] > 1:
                row.error = row.error or "Duplicate numeric airway point sequence"
        for position, row in enumerate(members):
            if report.invalid(row):
                continue
            fields = row.fields
            if group[0] != "Y" or group[1] not in {"C", "A", "H"}:
                report.issue(
                    "nasr-airway-no-fixed-scope", "No supported regulatory AWY2 scope", row
                )
                continue
            if not fields["TO_POINT"].strip():
                report.issue(
                    "nasr-airway-terminal",
                    "Terminal point has no outgoing segment",
                    row,
                    severity="info",
                )
                continue
            if fields["AWY_SEG_GAP_FLAG"].strip() == "Y" or fields["DOGLEG"].strip() == "Y":
                report.issue(
                    "nasr-airway-explicit-gap", "Gap/dogleg segment has no direct line", row
                )
                continue
            following = members[position + 1] if position + 1 < len(members) else None
            if (
                following is None
                or following.error
                or fields["TO_POINT"].strip() != following.fields["FROM_POINT"].strip()
                or fixed_next.get((group[1], group[2], int(fields["POINT_SEQ"])))
                != int(following.fields["POINT_SEQ"])
            ):
                report.issue(
                    "nasr-airway-disconnected", "Next ordered point is absent or mismatched", row
                )
                continue
            pair = [
                points.get((group[1], group[2], str(int(r.fields["POINT_SEQ"]))))
                for r in (row, following)
            ]
            if any(point is None for point in pair):
                report.issue("nasr-airway-missing-point", "AWY2 endpoint missing or invalid", row)
                continue
            try:
                coordinates = [
                    [_dms(p.fields["LONG_DMS"], False), _dms(p.fields["LAT_DMS"], True)]
                    for p in pair
                ]
            except ValueError:
                report.issue(
                    "nasr-airway-missing-coordinate", "AWY2 endpoint coordinate unavailable", row
                )
                continue
            records.append(
                ResearchRecord(
                    id=_identifier("airway", (*group, str(int(fields["POINT_SEQ"])))),
                    kind="airway",
                    name=f"{fields['AWY_ID']} {fields['FROM_POINT']}–{fields['TO_POINT']}",
                    identifier=fields["AWY_ID"],
                    sequence=int(fields["POINT_SEQ"]),
                    geometry={"type": "LineString", "coordinates": coordinates},
                    properties={
                        **_properties(row, expected),
                        "from_point": fields["FROM_POINT"],
                        "to_point": fields["TO_POINT"],
                        "scope": group[1],
                        "distance_unit": "NM",
                        "altitude_unit": "ft",
                        "endpoint_raw_fields": [p.fields for p in pair],
                        "next_point_raw_fields": following.fields,
                        "supporting_provenance": [
                            *[_support(p) for p in pair],
                            _support(following),
                        ],
                    },
                    provenance=row.provenance,
                )
            )
            report.success += 1
    return records


def _frequency(raw: str) -> tuple[str, str, bool]:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(R?)", raw.strip())
    if not match:
        raise ValueError("Frequency is not one decimal value with optional receive-only R")
    value = _number(match[1])
    # Conservative aviation VHF and UHF ranges, including radio-navigation ATIS.
    # Other numeric ranges cannot be assigned units from the FRQ CSV alone.
    if not (108 <= value <= 137 or 225 <= value <= 400):
        raise ValueError("Frequency unit is not established for this range")
    return match[1], "MHz", bool(match[2])


def _communications(tables, airports, expected, report) -> list[ResearchRecord]:
    index: dict[tuple[str, str], list[ResearchRecord]] = defaultdict(list)
    for airport in airports:
        source = airport.properties["raw_fields"]
        index[(source["ARPT_ID"], source["SITE_TYPE_CODE"])].append(airport)
    records = []
    occurrences: Counter[str] = Counter()
    for row in tables.get("FRQ.csv", []):
        if not row.fields.get("SERVICED_FACILITY", "").strip():
            row.error = row.error or "Empty required SERVICED_FACILITY identity"
        if report.invalid(row):
            continue
        fields = row.fields
        if fields["SERVICED_SITE_TYPE"].strip() != "AIRPORT":
            report.issue(
                "nasr-frequency-site-type", "Only evidenced AIRPORT site mapping is enabled", row
            )
            continue
        candidates = index.get((fields["SERVICED_FACILITY"].strip(), "A"), [])
        candidates = [
            airport
            for airport in candidates
            if all(
                not fields[frq_field].strip()
                or not airport.properties.get(apt_field)
                or fields[frq_field].strip() == airport.properties[apt_field]
                for frq_field, apt_field in [
                    ("SERVICED_COUNTRY", "country"),
                    ("SERVICED_STATE", "state"),
                ]
            )
        ]
        if len(candidates) != 1:
            report.issue(
                "nasr-frequency-airport-association",
                "Expected one airport matching serviced identifier/type and country/state",
                row,
            )
            continue
        service = fields["FREQ_USE"]
        if not service.strip():
            report.issue(
                "nasr-frequency-missing-use", "Frequency usage is empty or whitespace", row
            )
            continue
        try:
            frequency, unit, receive_only = _frequency(fields["FREQ"])
        except ValueError as exc:
            code = "nasr-frequency-unit" if "unit" in str(exc) else "nasr-frequency-format"
            report.issue(code, str(exc), row)
            continue
        airport = candidates[0]
        digest = hashlib.sha256(
            json.dumps(
                [airport.id, fields],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        occurrences[digest] += 1
        common = bool(
            re.search(
                r"\b(?:TOWER|LCL|GND|CD|APCH|DEP|CTAF|UNICOM|ATIS|AWOS|ASOS|"
                r"WEATHER|EMERG)\b",
                service,
            )
        )
        records.append(
            ResearchRecord(
                id=_identifier("communication", (digest, str(occurrences[digest]))),
                kind="communication",
                name=service,
                identifier=frequency,
                airport_id=airport.id,
                airport_ident=airport.airport_ident,
                geometry=None,
                properties={
                    **_properties(row, expected),
                    "service": service,
                    "frequency": frequency,
                    "unit": unit,
                    "remarks": fields["REMARK"],
                    "receive_only": receive_only,
                    "sectorization": fields["SECTORIZATION"],
                    "common_use": common,
                    "association_source": "APT_BASE",
                    "supporting_provenance": [airport.provenance.model_dump(mode="json")],
                },
                provenance=row.provenance,
            )
        )
        report.success += 1
    return records


def parse_nasr_layers(assets: dict[str, tuple[Path, str]], expected_date: date) -> ParseResult:
    """Parse six layers, retaining bounded diagnostics for unsupported source rows.

    Required asset keys: APT, NAV, FIX, AWY, AWY_POINTS and FRQ. Each value contains
    the source ZIP path and its SHA-256. All data CSV edition dates are checked;
    the caller must establish the AWY_POINTS ZIP's same-edition provenance.
    """
    report = _Report()
    tables = _load_tables(assets, expected_date, report)
    airports = _airports(assets, tables, expected_date, report)
    records = list(airports)
    records.extend(_runways(tables, airports, expected_date, report))
    records.extend(_navigation(tables, expected_date, report))
    records.extend(_airways(tables, _awy_points(assets, report), expected_date, report))
    records.extend(_communications(tables, airports, expected_date, report))
    return report.result(records)
