"""NASR APT_BASE CSV reader based on the accompanying FAA layout and structure files."""

from __future__ import annotations

import csv
import io
import math
import zipfile
from datetime import date, datetime
from pathlib import Path

from flightmap_schema import ParseResult, Provenance, ResearchRecord, ValidationReport

REQUIRED = {
    "EFF_DATE",
    "SITE_NO",
    "SITE_TYPE_CODE",
    "ARPT_ID",
    "ARPT_NAME",
    "LAT_DECIMAL",
    "LONG_DECIMAL",
    "ICAO_ID",
    "COUNTRY_CODE",
}


def _read(path: Path) -> tuple[list[dict[str, str]], str | None]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.rsplit("/", 1)[-1] == "APT_BASE.csv"]
            if len(members) != 1:
                raise ValueError("NASR package must contain exactly one APT_BASE.csv")
            with archive.open(members[0]) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
                if not REQUIRED.issubset(reader.fieldnames or []):
                    raise ValueError(
                        f"Missing NASR columns: {sorted(REQUIRED - set(reader.fieldnames or []))}"
                    )
                return list(reader), members[0]
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError(
                f"Missing NASR columns: {sorted(REQUIRED - set(reader.fieldnames or []))}"
            )
        return list(reader), None


def nasr_effective_date(path: Path) -> date:
    rows, _ = _read(path)
    dates = {datetime.strptime(row["EFF_DATE"], "%Y/%m/%d").date() for row in rows}
    if len(dates) != 1:
        raise ValueError("NASR must contain exactly one EFF_DATE")
    return dates.pop()


def parse_nasr(path: Path, asset_sha256: str, expected_date: date | None = None) -> ParseResult:
    rows, member = _read(path)
    records, issues = [], []
    seen: set[str] = set()
    errors = 0
    for position, row in enumerate(rows, start=2):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("CSV field count differs from the header")
            required_values = ("SITE_NO", "SITE_TYPE_CODE", "ARPT_ID", "ARPT_NAME")
            if any(not row[key].strip() for key in required_values):
                raise ValueError("Required airport identity/name is empty")
            effective_date = datetime.strptime(row["EFF_DATE"], "%Y/%m/%d").date()
            if expected_date is not None and effective_date != expected_date:
                raise ValueError("EFF_DATE conflicts with product validity evidence")
            lat, lon = float(row["LAT_DECIMAL"]), float(row["LONG_DECIMAL"])
            if not (
                math.isfinite(lat)
                and math.isfinite(lon)
                and -90 <= lat <= 90
                and -180 <= lon <= 180
            ):
                raise ValueError("Invalid airport coordinate")
            identifier = f"faa-aeronav:nasr:airport:{row['SITE_NO']}:{row['SITE_TYPE_CODE']}"
            if identifier in seen:
                raise ValueError("Duplicate SITE_NO/SITE_TYPE_CODE identity")
            seen.add(identifier)
            records.append(
                ResearchRecord(
                    id=identifier,
                    kind="airport",
                    name=row["ARPT_NAME"],
                    identifier=row["ARPT_ID"],
                    airport_ident=row["ARPT_ID"],
                    geometry={"type": "Point", "coordinates": [lon, lat]},
                    properties={
                        "icao_id": row["ICAO_ID"] or None,
                        "city": row.get("CITY", ""),
                        "state": row.get("STATE_CODE", ""),
                        "country": row["COUNTRY_CODE"],
                        "datum": "NAD83",
                        "raw_fields": row,
                        "effective_date": effective_date.isoformat(),
                    },
                    provenance=Provenance(
                        asset_sha256=asset_sha256,
                        member=member,
                        line=position,
                        locator=f"CSV record {position - 1} (header excluded)",
                    ),
                )
            )
        except (ValueError, KeyError) as exc:
            errors += 1
            issues.append(
                {
                    "code": "nasr-invalid-record",
                    "severity": "error",
                    "message": str(exc),
                    "record_key": f"APT_BASE:{position}",
                    "context": {"raw_fields": row},
                }
            )
    if not rows:
        issues.append(
            {"code": "empty-dataset", "severity": "fatal", "message": "No airport records"}
        )
    return ParseResult(
        records=records,
        report=ValidationReport(
            input_count=len(rows),
            success_count=len(records),
            unsupported_count=0,
            error_count=errors,
            issues=issues,
            capabilities=["airports"],
        ),
    )
