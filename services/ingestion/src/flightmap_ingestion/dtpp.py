"""FAA d-TPP catalog parsing; charts remain distinct from coded procedures."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from flightmap_schema import ParseResult, Provenance, ResearchRecord, ValidationReport

CATEGORIES = {
    "DP": "sid",
    "STR": "star",
    "IAP": "approaches",
    "APD": "airport-diagrams",
    "MIN": "minima",
    "ODP": "obstacle-departures",
    "HOT": "hot-spots",
    "LAH": "lahso",
    "DAU": "departure-authorizations",
}


def _root(path: Path) -> ET.Element:
    with path.open("rb") as stream:
        if b"<!DOCTYPE" in stream.read(4096).upper():
            raise ValueError("DTD declarations are not supported")
    root = ET.parse(path).getroot()
    if root.tag != "digital_tpp":
        raise ValueError("Expected digital_tpp root")
    return root


def dtpp_validity(path: Path) -> dict:
    root = _root(path)
    cycle = root.get("cycle", "")
    if not re.fullmatch(r"\d{4}", cycle):
        raise ValueError("Invalid d-TPP cycle")
    values = []
    for attr in ("from_edate", "to_edate"):
        value = " ".join(root.get(attr, "").split())
        values.append(datetime.strptime(value, "%H%MZ %m/%d/%y").replace(tzinfo=UTC))
    if values[0] >= values[1]:
        raise ValueError("Empty or reversed d-TPP validity")
    return {
        "airac": cycle,
        "valid_from": values[0],
        "valid_to": values[1],
        "validity_evidence": [
            f"digital_tpp/@from_edate={root.get('from_edate')}; "
            f"@to_edate={root.get('to_edate')}; @cycle={cycle}"
        ],
    }


def parse_dtpp(path: Path, asset_sha256: str) -> ParseResult:
    root = _root(path)
    cycle = dtpp_validity(path)["airac"]
    records, issues = [], []
    seen: set[str] = set()
    total = errors = unsupported = 0
    for airport in root.iter("airport_name"):
        apt_ident = airport.get("apt_ident", "").strip()
        for position, element in enumerate(airport.findall("record"), start=1):
            total += 1
            raw = {child.tag: (child.text or "").strip() for child in element}
            locator = f"airport_name[@apt_ident='{apt_ident}']/record[{position}]"
            try:
                code, name, pdf = (
                    raw.get("chart_code", ""),
                    raw.get("chart_name", ""),
                    raw.get("pdf_name", ""),
                )
                if not apt_ident or not name or not code:
                    raise ValueError("Missing chart or airport identity")
                deleted = raw.get("useraction") == "D"
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.PDF", pdf, re.I):
                    raise ValueError("Unsafe or invalid official PDF filename")
                identity = [apt_ident, code, raw.get("chartseq"), raw.get("procuid"), pdf, name]
                digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
                identifier = f"faa-aeronav:dtpp:chart:{apt_ident}:{digest}"
                if identifier in seen:
                    raise ValueError("Duplicate scoped chart identity")
                seen.add(identifier)
                supported = code in CATEGORIES
                if not supported:
                    unsupported += 1
                    issues.append(
                        {
                            "code": "chart-type-unsupported",
                            "severity": "warning",
                            "message": f"Unknown chart category {code}",
                            "record_key": identifier,
                        }
                    )
                records.append(
                    ResearchRecord(
                        id=identifier,
                        kind="chart",
                        name=name,
                        identifier=raw.get("procuid") or pdf,
                        airport_ident=apt_ident,
                        properties={
                            "chart_code": code,
                            "chart_name": name,
                            "category": CATEGORIES.get(code, "unsupported"),
                            "pdf_url": None
                            if deleted
                            else f"https://aeronav.faa.gov/d-tpp/{cycle}/{pdf}",
                            "deleted": deleted,
                            "cycle": cycle,
                            "icao_id": airport.get("icao_ident", "").strip() or None,
                            "airport_name": airport.get("ID", ""),
                            "procedure_code": raw.get("faanfd18") or None,
                            "association_status": "unconfirmed",
                            "raw_fields": raw,
                            "airport_attributes": dict(airport.attrib),
                        },
                        provenance=Provenance(asset_sha256=asset_sha256, locator=locator),
                    )
                )
            except ValueError as exc:
                errors += 1
                issues.append(
                    {
                        "code": "dtpp-invalid-record",
                        "severity": "error",
                        "message": str(exc),
                        "record_key": locator,
                        "context": {"raw_fields": raw},
                    }
                )
    if not total:
        issues.append({"code": "empty-dataset", "severity": "fatal", "message": "No chart records"})
    return ParseResult(
        records=records,
        report=ValidationReport(
            input_count=total,
            success_count=total - errors - unsupported,
            unsupported_count=unsupported,
            error_count=errors,
            issues=issues,
            capabilities=["charts"],
        ),
    )
