"""Audit the pinned OurAirports mainland-China reference without network access.

The report describes the frozen input and the generator's display semantics.  It
does not determine an airport's current operational status or frequency validity.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REVISION = "269b3557e2c784cc41673b77c7fae211d3f61668"
UPSTREAM = "https://raw.githubusercontent.com/davidmegginson/ourairports-data"
UPSTREAM_BROWSER = "https://github.com/davidmegginson/ourairports-data/blob"
INPUT_NAMES = ("airports.csv", "airport-frequencies.csv", "runways.csv", "navaids.csv", "LICENSE")
PINNED_INPUT_HASHES = {
    "airports.csv": "ca72a3404144b9478f51ff145910f2533c18b02a2c77c4a59e8f2274674a26c0",
    "airport-frequencies.csv": "785871bae512cd3d183288b4ba4639108cd4a8e8ab634d5fe3e491e4e516c740",
    "runways.csv": "47afb109bb0b7fa4e3d0b8da909e92ee4e41ee892dbc8cf5a6336e09272188dd",
    "navaids.csv": "57fb332b75be1173c45fd97447611eb3fba07b2c508c2f330961b9a8976e24cb",
    "LICENSE": "6b0382b16279f26ff69014300541967a356a666eb0b91b422f6862f6b7dad17e",
}
TARGET_IDENTS = (
    "ZBAA",
    "ZBAD",
    "ZSPD",
    "ZSSS",
    "ZGGG",
    "ZGSZ",
    "ZUUU",
    "ZUTF",
    "ZUCK",
    "ZHCC",
    "ZHHH",
    "ZLXY",
    "ZPPP",
    "ZSHC",
    "ZSNJ",
    "ZSQD",
    "ZSJN",
    "ZSAM",
    "ZSYA",
    "ZJSY",
    "ZJHK",
    "ZWWW",
    "ZWSH",
    "ZWTN",
    "ZWAK",
    "ZBNZ",
    "ZSOF",
    "ZBHH",
    "ZBHZ",
    "ZBSJ",
    "ZSFZ",
    "ZSLG",
)
CANDIDATE_NAME_TERMS = (
    "Ezhou",
    "Heze",
    "Hohhot Shengle",
    "Shache",
    "Taxkorgan",
    "Alar",
    "Zhaosu",
    "Yutian",
    "Liuting",
    "Urumqi",
)
EXTRA_TARGET_SOURCE_IDS = (
    "525766",  # Hohhot Shengle / CN-0418
    "337834",  # Xiamen Xiang'an / CN-0399
    "44232",  # Jiaxing / CN-0154
    "354722",  # Ruijin / CN-0347
    "525151",  # Bozhou / CN-0413
    "525774",  # Lishui / CN-0422
    "598595",  # Bengbu / CN-0476
    "600647",  # Dejiang / ZUDJ
    "605890",  # Balikun / ZWLK
)
REQUIRED_NAVIGATION_FREQUENCY_IDS = frozenset(
    {
        "ourairports:communication:539127",
        "ourairports:communication:539128",
        "ourairports:communication:539129",
        "ourairports:communication:539130",
        "ourairports:communication:539132",
        "ourairports:communication:539400",
        "ourairports:communication:539401",
        "ourairports:communication:539402",
    }
)
FREQUENCY_COLLECTIONS = (
    "communications",
    "navigation_frequencies",
    "unclassified_frequencies",
)
REVIEW_CATALOG = (
    Path(__file__).resolve().parents[1] / "reference-sources" / "ourairports-review.json"
)
REQUIRED_COLUMNS = {
    "airports.csv": {
        "id",
        "ident",
        "type",
        "name",
        "latitude_deg",
        "longitude_deg",
        "iso_country",
        "scheduled_service",
        "icao_code",
    },
    "airport-frequencies.csv": {
        "id",
        "airport_ref",
        "airport_ident",
        "type",
        "description",
        "frequency_mhz",
    },
    "runways.csv": {
        "id",
        "airport_ref",
        "airport_ident",
        "length_ft",
        "surface",
        "closed",
        "le_ident",
        "le_latitude_deg",
        "le_longitude_deg",
        "he_ident",
        "he_latitude_deg",
        "he_longitude_deg",
    },
}


def clean(row: dict[str, str], field: str) -> str | None:
    value = row.get(field, "").strip()
    return value or None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS[path.name].issubset(reader.fieldnames):
            raise ValueError(f"{path}: required columns are missing")
        return [(line, dict(row)) for line, row in enumerate(reader, start=2)]


def finite_number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def coordinate(row: dict[str, str], latitude: str, longitude: str) -> list[float] | None:
    lat = finite_number(clean(row, latitude))
    lon = finite_number(clean(row, longitude))
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return [lon, lat]


def source_url(filename: str, line: int | None = None) -> str:
    return f"{UPSTREAM}/{REVISION}/{filename}"


def browse_url(filename: str, line: int) -> str:
    return f"{UPSTREAM_BROWSER}/{REVISION}/{filename}#L{line}"


def haversine_km(first: list[float], second: list[float]) -> float:
    lat1, lat2 = math.radians(first[1]), math.radians(second[1])
    dlat, dlon = lat2 - lat1, math.radians(second[0] - first[0])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, value))))


def point_to_segment_km(point: list[float], first: list[float], second: list[float]) -> float:
    """Approximate the nearest point on a short runway in a local tangent plane."""
    km_per_degree = 111.195
    cos_latitude = math.cos(math.radians(point[1]))
    first_x = (first[0] - point[0]) * km_per_degree * cos_latitude
    first_y = (first[1] - point[1]) * km_per_degree
    second_x = (second[0] - point[0]) * km_per_degree * cos_latitude
    second_y = (second[1] - point[1]) * km_per_degree
    dx, dy = second_x - first_x, second_y - first_y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(first_x, first_y)
    fraction = max(0.0, min(1.0, -(first_x * dx + first_y * dy) / length_squared))
    return math.hypot(first_x + fraction * dx, first_y + fraction * dy)


def count_by(rows_to_count: list[tuple[int, dict[str, str]]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(clean(row, field) or "(empty)" for _, row in rows_to_count).items()))


def temporal_columns(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        names = csv.reader(handle).__next__()
    return [name for name in names if re.search(r"(?:date|time|updated|modified)", name, re.I)]


def runway_tile_occurrences(tiles_dir: Path) -> tuple[int, Counter[str]]:
    """Count actual exported GeoJSON features, retaining repeated features across tiles."""
    total = 0
    occurrences: Counter[str] = Counter()
    for path in sorted(tiles_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("type") != "FeatureCollection" or not isinstance(
            document.get("features"), list
        ):
            raise ValueError(f"invalid runway tile: {path}")
        for feature in document["features"]:
            record_id = feature.get("id")
            if not isinstance(record_id, str):
                raise ValueError(f"runway tile feature without an id: {path}")
            total += 1
            occurrences[record_id] += 1
    return total, occurrences


def is_reviewed_export(manifest: dict[str, Any]) -> bool:
    """Recognize the reviewed export contract without consulting generator source code."""
    counts = manifest.get("counts")
    return isinstance(counts, dict) and all(key in counts for key in FREQUENCY_COLLECTIONS)


def cn_detail_records(
    export_dir: Path, mainland_ids: set[str]
) -> tuple[dict[str, dict[str, Any]], dict[int, Path]]:
    """Read each required airport-detail bucket once and return only CN records."""
    bucket_paths = {
        int(airport_id) % 256: export_dir / "airports" / f"{int(airport_id) % 256}.json"
        for airport_id in mainland_ids
    }
    records: dict[str, dict[str, Any]] = {}
    for bucket, path in sorted(bucket_paths.items()):
        if not path.is_file():
            raise ValueError(f"missing CN airport detail bucket {bucket}: {path}")
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"invalid CN airport detail bucket {path}")
        for record_id, detail in document.items():
            source_id = record_id.removeprefix("ourairports:airport:")
            if source_id in mainland_ids:
                if not isinstance(detail, dict):
                    raise ValueError(f"invalid airport detail for {record_id}")
                records[record_id] = detail
    expected = {f"ourairports:airport:{airport_id}" for airport_id in mainland_ids}
    if set(records) != expected:
        raise ValueError("CN airport detail buckets do not contain exactly the source airport ids")
    return records, bucket_paths


def reviewed_frequency_export(
    export_dir: Path,
    mainland: list[tuple[int, dict[str, str]]],
    mainland_frequency_rows: list[tuple[int, dict[str, str]]],
    visible_ids: set[str],
    input_hash: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Verify reviewed frequency detail records by their immutable source identities.

    This intentionally checks the emitted categories, rather than classifying source text again.
    """
    mainland_ids = {clean(row, "id") or "" for _, row in mainland}
    details, bucket_paths = cn_detail_records(export_dir, mainland_ids)
    expected: dict[str, tuple[int, dict[str, str]]] = {}
    for line, row in mainland_frequency_rows:
        source_id = clean(row, "id")
        if source_id is None:
            raise ValueError(f"airport-frequencies.csv:{line}: missing id")
        record_id = f"ourairports:communication:{source_id}"
        if record_id in expected:
            raise ValueError(f"airport-frequencies.csv:{line}: duplicate id")
        expected[record_id] = (line, row)

    emitted: dict[str, tuple[str, dict[str, Any]]] = {}
    category_summary: dict[str, dict[str, Any]] = {}
    for category in FREQUENCY_COLLECTIONS:
        all_records: list[dict[str, Any]] = []
        for airport_id, detail in details.items():
            values = detail.get(category)
            if not isinstance(values, list):
                raise ValueError(f"{airport_id}: missing or invalid {category}")
            for value in values:
                if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                    raise ValueError(f"{airport_id}: invalid {category} record")
                record_id = value["id"]
                if record_id in emitted:
                    raise ValueError(
                        f"frequency record appears in multiple detail categories: {record_id}"
                    )
                emitted[record_id] = (category, value)
                all_records.append(value)
        visible_records = [
            value
            for value in all_records
            if (value.get("airport_id") or "").removeprefix("ourairports:airport:") in visible_ids
        ]
        category_summary[category] = {
            "all_CN": {
                "records": len(all_records),
                "airports": len({value.get("airport_id") for value in all_records}),
            },
            "visible_CN": {
                "records": len(visible_records),
                "airports": len({value.get("airport_id") for value in visible_records}),
            },
        }

    if set(emitted) != set(expected):
        missing = sorted(set(expected) - set(emitted))
        unexpected = sorted(set(emitted) - set(expected))
        raise ValueError(
            "CN frequency detail/source id mismatch: "
            f"missing={missing[:3]}, unexpected={unexpected[:3]}"
        )
    for record_id, (line, source) in expected.items():
        category, value = emitted[record_id]
        parent_id = f"ourairports:airport:{clean(source, 'airport_ref') or ''}"
        properties = value.get("properties")
        provenance = value.get("provenance")
        if (
            value.get("kind") != "communication"
            or value.get("airport_id") != parent_id
            or value.get("parent_id") != parent_id
            or not isinstance(properties, dict)
            or not isinstance(provenance, dict)
            or properties.get("service") != clean(source, "type")
            or properties.get("frequency") != clean(source, "frequency_mhz")
            or properties.get("unit") != "MHz"
            or properties.get("remarks") != clean(source, "description")
            or provenance.get("member") != "airport-frequencies.csv"
            or provenance.get("line") != line
            or provenance.get("asset_sha256") != input_hash
        ):
            raise ValueError(f"CN frequency provenance/value mismatch: {record_id} ({category})")

    return {
        "detail_bucket_count": len(bucket_paths),
        "detail_bucket_cache": "each required CN bucket is loaded once",
        "categories": category_summary,
        "source_records": len(expected),
        "emitted_records": len(emitted),
        "source_identity_union_matches_details": True,
        "no_cross_category_duplicates": True,
        "provenance_and_raw_values_match": True,
    }, details


def require_reviewed_acceptance(
    manifest: dict[str, Any],
    export_dir: Path,
    details: dict[str, dict[str, Any]],
    map_tile_occurrences: Counter[str],
    mainland_runway_rows: list[tuple[int, dict[str, str]]],
    airports_by_id: dict[str, tuple[int, dict[str, str]]],
    visible_ids: set[str],
) -> dict[str, Any]:
    """Apply the explicit release gate for a reviewed export."""
    review = manifest.get("review")
    if not isinstance(review, dict):
        raise ValueError("--require-reviewed requires manifest.review")
    required_review = {"reviewed_at", "source_revision", "sha256", "correction_count", "note_count"}
    if set(review) != required_review or review.get("source_revision") != REVISION:
        raise ValueError("manifest.review is incomplete or references another source revision")
    review_path = export_dir / "review.json"
    if not REVIEW_CATALOG.is_file():
        raise ValueError(f"approved review catalog is missing: {REVIEW_CATALOG}")
    if not review_path.is_file() or review_path.read_bytes() != REVIEW_CATALOG.read_bytes():
        raise ValueError("published review.json does not match the approved review catalog bytes")
    if sha256(review_path) != review.get("sha256"):
        raise ValueError("manifest.review SHA-256 does not match review.json")
    review_catalog = json.loads(review_path.read_text(encoding="utf-8"))
    if (
        review.get("reviewed_at") != review_catalog.get("reviewed_at")
        or review.get("source_revision") != review_catalog.get("source_revision")
        or review.get("correction_count") != len(review_catalog.get("corrections", []))
        or review.get("note_count") != len(review_catalog.get("notes", []))
    ):
        raise ValueError("manifest.review does not match the approved review catalog metadata")
    corrections = review_catalog.get("corrections")
    if (
        not isinstance(corrections, list)
        or len(corrections) != 1
        or review.get("correction_count") != 1
    ):
        raise ValueError("reviewed export must contain exactly the approved Bozhou name correction")
    correction = corrections[0]
    if (
        not isinstance(correction, dict)
        or correction.get("airport_id") != "ourairports:airport:525151"
        or correction.get("record_id") != "ourairports:airport:525151"
        or correction.get("field") != "name"
        or correction.get("original_value") != "Bozhou Airport (under construction)"
        or correction.get("value") != "Bozhou Airport"
        or not correction.get("evidence")
    ):
        raise ValueError("reviewed export has no valid Bozhou correction evidence")
    bozhou = details.get("ourairports:airport:525151", {}).get("airport")
    if not isinstance(bozhou, dict) or bozhou.get("name") != "Bozhou Airport":
        raise ValueError("Bozhou name correction is absent from airport detail")
    if bozhou.get("properties", {}).get("original_name") != "Bozhou Airport (under construction)":
        raise ValueError("Bozhou original_name provenance is absent from airport detail")
    source_bozhou = airports_by_id.get("525151")
    if source_bozhou is None or clean(source_bozhou[1], "name") != correction["original_value"]:
        raise ValueError("Bozhou correction original_value does not match airports.csv")

    records_by_id: dict[str, dict[str, Any]] = {}
    expected_notes_by_airport: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in [*corrections, *review_catalog.get("notes", [])]:
        expected_notes_by_airport[entry["airport_id"]].append(
            {**entry, "reviewed_at": review_catalog["reviewed_at"]}
        )
    for airport_id, detail in details.items():
        airport = detail.get("airport")
        if not isinstance(airport, dict):
            raise ValueError(f"{airport_id}: invalid airport review detail")
        records_by_id[airport_id] = airport
        review_notes = detail.get("review_notes")
        if not isinstance(review_notes, list) or any(
            not isinstance(note, dict) for note in review_notes
        ):
            raise ValueError(f"{airport_id}: invalid review_notes")
        if sorted(review_notes, key=lambda entry: entry.get("id", "")) != sorted(
            expected_notes_by_airport.get(airport_id, []), key=lambda entry: entry.get("id", "")
        ):
            raise ValueError(
                "airport detail review_notes do not exactly match the approved catalog"
            )
        runways = detail.get("runways")
        if not isinstance(runways, list):
            raise ValueError(f"{airport_id}: invalid runway detail")
        for runway in runways:
            if not isinstance(runway, dict) or not isinstance(runway.get("id"), str):
                raise ValueError(f"{airport_id}: invalid runway review target")
            records_by_id[runway["id"]] = runway
    for entry in [*corrections, *review_catalog.get("notes", [])]:
        target = records_by_id.get(entry["record_id"])
        if target is None:
            raise ValueError(f"review target is absent from airport details: {entry['record_id']}")
        value: Any = target
        for segment in entry["field"].split("."):
            if not isinstance(value, dict):
                raise ValueError(f"review field path is absent: {entry['id']}")
            value = value.get(segment)
        expected_value = entry.get("value", entry["original_value"])
        if value != expected_value:
            raise ValueError(f"review target value changed: {entry['id']}")

    closed_airport_runways = [
        item
        for item in mainland_runway_rows
        if clean(airports_by_id[clean(item[1], "airport_ref")][1], "type") == "closed"
    ]
    closed_visible_runways = [
        item
        for item in mainland_runway_rows
        if clean(item[1], "airport_ref") in visible_ids and clean(item[1], "closed") == "1"
    ]
    for label, items in (
        ("closed-airport runway", closed_airport_runways),
        ("closed runway at visible airport", closed_visible_runways),
    ):
        exported = [
            clean(row, "id")
            for _, row in items
            if map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0)
        ]
        if exported:
            raise ValueError(f"{label} appears in map tiles: {exported[:3]}")

    categories = {
        record_id: category
        for category in FREQUENCY_COLLECTIONS
        for record_id in [
            value["id"]
            for detail in details.values()
            for value in detail[category]
        ]
    }
    if any(
        categories.get(record_id) != "navigation_frequencies"
        for record_id in REQUIRED_NAVIGATION_FREQUENCY_IDS
    ):
        raise ValueError(
            "the eight explicit CN navigation candidates are not all navigation_frequencies"
        )
    return {
        "bozhou_correction_and_original_name": True,
        "closed_airport_runway_map_features": 0,
        "closed_visible_airport_runway_map_features": 0,
        "required_navigation_frequency_ids": len(REQUIRED_NAVIGATION_FREQUENCY_IDS),
        "required_navigation_candidates_reclassified": True,
        "review_catalog_sha256_matches_manifest": True,
        "approved_review_catalog_bytes_match_export": True,
        "detail_review_notes_match_catalog": True,
        "review_target_values_match_catalog": True,
    }


def frequency_summary(items: list[tuple[int, dict[str, str]]]) -> dict[str, Any]:
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    groups: dict[tuple[str, str, str], list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for line, row in items:
        raw = clean(row, "frequency_mhz")
        parsed = finite_number(raw)
        status = (
            "valid_positive"
            if parsed is not None and parsed > 0
            else ("blank" if raw is None else "invalid_or_nonpositive")
        )
        service = clean(row, "type") or "(empty)"
        by_type[service]["rows"] += 1
        by_type[service][status] += 1
        groups[(clean(row, "airport_ref") or "", service, raw or "(empty)")].append((line, row))
    shared = []
    for (airport_ref, service, raw), group in sorted(groups.items()):
        if len(group) > 1:
            shared.append(
                {
                    "airport_ref": airport_ref,
                    "airport_ident": clean(group[0][1], "airport_ident"),
                    "type": service,
                    "frequency_mhz_raw": raw,
                    "descriptions": sorted(
                        {clean(row, "description") or "(empty)" for _, row in group}
                    ),
                    "lines": [line for line, _ in group],
                    "browse_urls": [
                        browse_url("airport-frequencies.csv", line) for line, _ in group
                    ],
                }
            )
    return {
        "rows": len(items),
        "by_type": {key: dict(sorted(value.items())) for key, value in sorted(by_type.items())},
        "valid_positive_rows": sum(value["valid_positive"] for value in by_type.values()),
        "blank_frequency_rows": sum(value["blank"] for value in by_type.values()),
        "invalid_or_nonpositive_rows": sum(
            value["invalid_or_nonpositive"] for value in by_type.values()
        ),
        "shared_frequency_candidate_definition": "same airport_ref + type + raw frequency_mhz",
        "shared_frequency_candidates": shared,
        "shared_frequency_candidate_excess_rows": sum(len(item["lines"]) - 1 for item in shared),
    }


def runway_observation(
    item: tuple[int, dict[str, str]],
    airport: tuple[int, dict[str, str]],
    map_tile_occurrences: dict[str, int],
) -> dict[str, Any]:
    line, row = item
    airport_line, airport_row = airport
    low = coordinate(row, "le_latitude_deg", "le_longitude_deg")
    high = coordinate(row, "he_latitude_deg", "he_longitude_deg")
    return {
        "airport": {
            "id": clean(airport_row, "id"),
            "ident": clean(airport_row, "ident"),
            "name": clean(airport_row, "name"),
            "type": clean(airport_row, "type"),
            "line": airport_line,
            "browse_url": browse_url("airports.csv", airport_line),
        },
        "runway": {
            "id": clean(row, "id"),
            "line": line,
            "browse_url": browse_url("runways.csv", line),
            "identifiers": {"le": clean(row, "le_ident"), "he": clean(row, "he_ident")},
            "length_ft": clean(row, "length_ft"),
            "surface": clean(row, "surface"),
            "closed_raw": clean(row, "closed"),
            "endpoints": {"le": low, "he": high},
            "has_complete_endpoints": low is not None and high is not None,
            "map_tile_feature_occurrences": map_tile_occurrences.get(
                f"ourairports:runway:{clean(row, 'id') or ''}", 0
            ),
        },
    }


def airport_evidence(
    line: int,
    airport: dict[str, str],
    frequencies: list[tuple[int, dict[str, str]]],
    runways: list[tuple[int, dict[str, str]]],
    map_tile_occurrences: dict[str, int],
) -> dict[str, Any]:
    airport_id = clean(airport, "id") or ""

    def frequency_evidence(item: tuple[int, dict[str, str]]) -> dict[str, Any]:
        frequency_line, row = item
        raw = clean(row, "frequency_mhz")
        parsed = finite_number(raw)
        status = (
            "valid_positive"
            if parsed is not None and parsed > 0
            else ("blank" if raw is None else "invalid_or_nonpositive")
        )
        return {
            "id": clean(row, "id"),
            "line": frequency_line,
            "source_url": source_url("airport-frequencies.csv", frequency_line),
            "browse_url": browse_url("airport-frequencies.csv", frequency_line),
            "type": clean(row, "type"),
            "description": clean(row, "description"),
            "frequency_mhz_raw": raw,
            "validation": status,
        }

    def runway_evidence(item: tuple[int, dict[str, str]]) -> dict[str, Any]:
        runway_line, row = item
        low = coordinate(row, "le_latitude_deg", "le_longitude_deg")
        high = coordinate(row, "he_latitude_deg", "he_longitude_deg")
        return {
            "id": clean(row, "id"),
            "line": runway_line,
            "source_url": source_url("runways.csv", runway_line),
            "browse_url": browse_url("runways.csv", runway_line),
            "airport_ref": clean(row, "airport_ref"),
            "airport_ident": clean(row, "airport_ident"),
            "identifiers": {"le": clean(row, "le_ident"), "he": clean(row, "he_ident")},
            "length_ft": clean(row, "length_ft"),
            "width_ft": clean(row, "width_ft"),
            "surface": clean(row, "surface"),
            "closed_raw": clean(row, "closed"),
            "endpoints": {"le": low, "he": high},
            "has_complete_endpoints": low is not None and high is not None,
            "map_tile_feature_occurrences": map_tile_occurrences.get(
                f"ourairports:runway:{clean(row, 'id') or ''}", 0
            ),
        }

    point = coordinate(airport, "latitude_deg", "longitude_deg")
    return {
        "id": airport_id,
        "line": line,
        "source_url": source_url("airports.csv", line),
        "browse_url": browse_url("airports.csv", line),
        "ident": clean(airport, "ident"),
        "icao_code": clean(airport, "icao_code"),
        "iata_code": clean(airport, "iata_code"),
        "gps_code": clean(airport, "gps_code"),
        "name": clean(airport, "name"),
        "type": clean(airport, "type"),
        "scheduled_service": clean(airport, "scheduled_service"),
        "coordinates": point,
        "is_visible_source_candidate": point is not None and clean(airport, "type") != "closed",
        "runways": [runway_evidence(item) for item in runways],
        "frequencies": [frequency_evidence(item) for item in frequencies],
    }


def audit(cache_root: Path, require_reviewed: bool = False) -> dict[str, Any]:
    input_dir = cache_root / "pages-input" / REVISION
    public_root = cache_root / "pages-public" / "reference"
    manifest_path = public_root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"missing generated manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source", {}).get("revision") != REVISION:
        raise ValueError("manifest source revision does not match the fixed audit revision")
    dataset_revision = manifest.get("dataset_revision")
    if not isinstance(dataset_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", dataset_revision):
        raise ValueError("manifest has no valid dataset_revision")
    export_dir = public_root / dataset_revision
    if not export_dir.is_dir():
        raise ValueError("manifest dataset_revision directory is missing")
    reviewed_export = is_reviewed_export(manifest)
    if require_reviewed and not reviewed_export:
        raise ValueError("--require-reviewed rejects the legacy export contract")

    inputs: dict[str, dict[str, Any]] = {}
    manifest_inputs = {
        entry.get("name"): entry.get("sha256") for entry in manifest.get("inputs", [])
    }
    for name in INPUT_NAMES:
        path = input_dir / name
        if not path.is_file():
            raise ValueError(f"missing fixed input: {path}")
        actual = sha256(path)
        inputs[name] = {
            "path": str(path),
            "source_url": source_url(name),
            "sha256": actual,
            "generator_pinned_sha256": PINNED_INPUT_HASHES[name],
            "manifest_sha256": manifest_inputs.get(name),
            "matches_generator_pin": actual == PINNED_INPUT_HASHES[name],
            "matches_manifest": actual == manifest_inputs.get(name),
        }
    if not all(
        item["matches_generator_pin"] and item["matches_manifest"] for item in inputs.values()
    ):
        raise ValueError(
            "one or more fixed input SHA-256 values do not match generator and manifest"
        )

    airport_rows = rows(input_dir / "airports.csv")
    frequency_rows = rows(input_dir / "airport-frequencies.csv")
    runway_rows = rows(input_dir / "runways.csv")
    mainland = [(line, row) for line, row in airport_rows if clean(row, "iso_country") == "CN"]
    airports_by_id = {clean(row, "id"): (line, row) for line, row in mainland if clean(row, "id")}
    visible = [
        (line, row)
        for line, row in mainland
        if coordinate(row, "latitude_deg", "longitude_deg") is not None
        and clean(row, "type") != "closed"
    ]
    visible_ids = {clean(row, "id") for _, row in visible}
    frequencies_by_ref: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for item in frequency_rows:
        frequencies_by_ref[clean(item[1], "airport_ref") or ""].append(item)
    runways_by_ref: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for item in runway_rows:
        runways_by_ref[clean(item[1], "airport_ref") or ""].append(item)
    mainland_frequency_rows = [
        item for item in frequency_rows if clean(item[1], "airport_ref") in airports_by_id
    ]
    mainland_runway_rows = [
        item for item in runway_rows if clean(item[1], "airport_ref") in airports_by_id
    ]
    visible_frequency_rows = [
        item for item in mainland_frequency_rows if clean(item[1], "airport_ref") in visible_ids
    ]
    visible_runway_rows = [
        item for item in mainland_runway_rows if clean(item[1], "airport_ref") in visible_ids
    ]
    all_frequency_summary = frequency_summary(mainland_frequency_rows)
    visible_frequency_summary = frequency_summary(visible_frequency_rows)
    drawable_runways = [
        (line, row)
        for line, row in mainland_runway_rows
        if coordinate(row, "le_latitude_deg", "le_longitude_deg") is not None
        and coordinate(row, "he_latitude_deg", "he_longitude_deg") is not None
    ]
    drawable_visible_runways = [
        (line, row)
        for line, row in visible_runway_rows
        if coordinate(row, "le_latitude_deg", "le_longitude_deg") is not None
        and coordinate(row, "he_latitude_deg", "he_longitude_deg") is not None
    ]
    tiles_total, map_tile_occurrences = runway_tile_occurrences(export_dir / "tiles" / "runways")
    if tiles_total != manifest.get("counts", {}).get("runways"):
        raise ValueError("exported runway tile feature count does not match manifest")
    index_path = export_dir / "search" / "CN.json"
    if not index_path.is_file():
        raise ValueError(f"missing CN export index: {index_path}")
    exported_index = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(exported_index, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in exported_index
    ):
        raise ValueError("invalid CN export index")
    exported_ids = {item.get("id") for item in exported_index}
    if len(exported_ids) != len(exported_index):
        raise ValueError("CN export index contains duplicate airport ids")
    expected_visible_ids = {f"ourairports:airport:{airport_id}" for airport_id in visible_ids}
    coverage = next(
        (entry for entry in manifest.get("coverage", []) if entry.get("country") == "CN"), None
    )
    manifest_cn_expected = {
        "airports": len(visible),
        "airports_with_communications": sum(
            bool(frequencies_by_ref[clean(row, "id") or ""]) for _, row in visible
        ),
        "runways": sum(len(runways_by_ref[clean(row, "id") or ""]) for _, row in visible),
    }

    reviewed_frequency_summary: dict[str, Any] | None = None
    reviewed_details: dict[str, dict[str, Any]] | None = None
    reviewed_acceptance: dict[str, Any] | None = None
    if reviewed_export:
        counts = manifest.get("counts", {})
        source_counts = manifest.get("source_counts", {})
        if (
            not isinstance(source_counts, dict)
            or source_counts.get("communications") != len(frequency_rows)
            or any(
                not isinstance(counts.get(key), int) or counts[key] < 0
                for key in FREQUENCY_COLLECTIONS
            )
            or sum(counts[key] for key in FREQUENCY_COLLECTIONS) != source_counts["communications"]
        ):
            raise ValueError(
                "reviewed manifest frequency counts do not conserve source frequency rows"
            )
        reviewed_frequency_summary, reviewed_details = reviewed_frequency_export(
            export_dir,
            mainland,
            mainland_frequency_rows,
            visible_ids,
            inputs["airport-frequencies.csv"]["sha256"],
        )
        manifest_cn_expected |= {
            "airports_with_communications": reviewed_frequency_summary["categories"][
                "communications"
            ]["visible_CN"]["airports"],
            "airports_with_frequencies": len(
                {
                    value.get("airport_id")
                    for detail in reviewed_details.values()
                    for category in FREQUENCY_COLLECTIONS
                    for value in detail[category]
                    if (value.get("airport_id") or "").removeprefix("ourairports:airport:")
                    in visible_ids
                }
            ),
        }
        if coverage is None or any(
            coverage.get(key) != value for key, value in manifest_cn_expected.items()
        ):
            raise ValueError(
                "reviewed manifest CN coverage does not match exported airport details"
            )
        if require_reviewed:
            reviewed_acceptance = require_reviewed_acceptance(
                manifest,
                export_dir,
                reviewed_details,
                map_tile_occurrences,
                mainland_runway_rows,
                airports_by_id,
                visible_ids,
            )

    def visible_group_coverage(items: list[tuple[int, dict[str, str]]]) -> dict[str, int]:
        ids = [clean(row, "id") or "" for _, row in items]
        return {
            "airports": len(items),
            "airports_with_any_frequency_row": sum(bool(frequencies_by_ref[item]) for item in ids),
            "frequency_rows": sum(len(frequencies_by_ref[item]) for item in ids),
            "airports_with_any_runway_row": sum(bool(runways_by_ref[item]) for item in ids),
            "runway_rows": sum(len(runways_by_ref[item]) for item in ids),
        }

    visible_group_coverages = {
        "scheduled_service_yes": visible_group_coverage(
            [(line, row) for line, row in visible if clean(row, "scheduled_service") == "yes"]
        ),
        "large_airport": visible_group_coverage(
            [(line, row) for line, row in visible if clean(row, "type") == "large_airport"]
        ),
        "medium_airport": visible_group_coverage(
            [(line, row) for line, row in visible if clean(row, "type") == "medium_airport"]
        ),
    }
    navigation_like_frequencies = []
    navigation_type_pattern = re.compile(r"(?:\bGP\b|\bLOC\b|\bILS\b|\bDME\b|\bVOR\b)", re.I)
    for line, row in mainland_frequency_rows:
        service = clean(row, "type") or ""
        if not navigation_type_pattern.search(service):
            continue
        airport = airports_by_id[clean(row, "airport_ref")]
        airport_line, airport_row = airport
        navigation_like_frequencies.append(
            {
                "airport_id": clean(airport_row, "id"),
                "airport_ident": clean(airport_row, "ident"),
                "airport_name": clean(airport_row, "name"),
                "airport_is_visible_source_candidate": clean(airport_row, "id") in visible_ids,
                "line": line,
                "browse_url": browse_url("airport-frequencies.csv", line),
                "type": service,
                "frequency_mhz_raw": clean(row, "frequency_mhz"),
                "description": clean(row, "description"),
                "classification": "navigation_like_type_candidate",
            }
        )
    closed_airport_runways = [
        item
        for item in mainland_runway_rows
        if clean(airports_by_id[clean(item[1], "airport_ref")][1], "type") == "closed"
    ]
    closed_runways_at_visible_airports = [
        item for item in visible_runway_rows if clean(item[1], "closed") == "1"
    ]

    length_difference_candidates = []
    airport_distance_candidates = []
    for item in drawable_runways:
        runway_line, runway = item
        airport = airports_by_id[clean(runway, "airport_ref")]
        airport_line, airport_row = airport
        low = coordinate(runway, "le_latitude_deg", "le_longitude_deg")
        high = coordinate(runway, "he_latitude_deg", "he_longitude_deg")
        airport_point = coordinate(airport_row, "latitude_deg", "longitude_deg")
        assert low is not None and high is not None
        geometry_length_ft = haversine_km(low, high) * 3280.839895
        source_length_ft = finite_number(clean(runway, "length_ft"))
        if source_length_ft is not None and source_length_ft > 0:
            delta_ft = abs(geometry_length_ft - source_length_ft)
            relative_delta = delta_ft / source_length_ft
            if delta_ft >= 1000 and relative_delta >= 0.25:
                length_difference_candidates.append(
                    {
                        **runway_observation(item, airport, map_tile_occurrences),
                        "source_length_ft": source_length_ft,
                        "endpoint_geodesic_length_ft": round(geometry_length_ft, 1),
                        "absolute_difference_ft": round(delta_ft, 1),
                        "relative_difference": round(relative_delta, 4),
                    }
                )
        if airport_point is not None:
            distance_km = point_to_segment_km(airport_point, low, high)
            if distance_km >= 5:
                airport_distance_candidates.append(
                    {
                        **runway_observation(item, airport, map_tile_occurrences),
                        "airport_point_to_runway_segment_km": round(distance_km, 3),
                    }
                )

    ident_vs_icao = Counter()
    for _, row in mainland:
        ident, icao = clean(row, "ident"), clean(row, "icao_code")
        ident_vs_icao[
            "equal_nonempty"
            if ident and icao and ident == icao
            else "different_nonempty"
            if ident and icao
            else "ident_only"
            if ident
            else "icao_only"
            if icao
            else "both_empty"
        ] += 1
    target_by_ident = defaultdict(list)
    for item in mainland:
        target_by_ident[clean(item[1], "ident") or ""].append(item)
    named_candidates = [
        (line, row)
        for line, row in mainland
        if any(
            term.casefold() in (clean(row, "name") or "").casefold()
            for term in CANDIDATE_NAME_TERMS
        )
    ]
    sample_items: list[tuple[str, list[tuple[int, dict[str, str]]]]] = [
        (f"ident:{ident}", target_by_ident[ident]) for ident in TARGET_IDENTS
    ]
    for source_id in EXTRA_TARGET_SOURCE_IDS:
        sample_items.append(
            (f"source_id:{source_id}", [airports_by_id[source_id]])
            if source_id in airports_by_id
            else (f"source_id:{source_id}", [])
        )
    for term in CANDIDATE_NAME_TERMS:
        matches = [
            (line, row)
            for line, row in named_candidates
            if term.casefold() in (clean(row, "name") or "").casefold()
        ]
        sample_items.append((f"name_contains:{term}", matches))
    samples = []
    missing_targets = []
    for query, matches in sample_items:
        if not matches and query.startswith("ident:"):
            missing_targets.append(query.removeprefix("ident:"))
        records = []
        for line, row in matches:
            airport_id = clean(row, "id")
            records.append(
                airport_evidence(
                    line,
                    row,
                    frequencies_by_ref[airport_id or ""],
                    runways_by_ref[airport_id or ""],
                    map_tile_occurrences,
                )
            )
        samples.append({"query": query, "found": bool(matches), "records": records})

    missing_export = []
    for line, row in mainland:
        airport_id = clean(row, "id") or ""
        record_id = f"ourairports:airport:{airport_id}"
        if record_id not in exported_ids:
            missing_export.append(
                {
                    "id": airport_id,
                    "ident": clean(row, "ident"),
                    "name": clean(row, "name"),
                    "type": clean(row, "type"),
                    "line": line,
                    "source_url": source_url("airports.csv", line),
                    "browse_url": browse_url("airports.csv", line),
                    "reason_by_generator": "closed_type"
                    if clean(row, "type") == "closed"
                    else "invalid_or_missing_airport_coordinates",
                }
            )

    result = {
        "audit": {
            "scope": "CN only; HK, MO, and TW are separate ISO-country records and excluded",
            "network_used": False,
            "published_data_generated": False,
            "export_contract": "reviewed_frequency_categories_v1"
            if reviewed_export
            else "legacy_single_communications_collection",
            "generator_semantics": {
                "visible_airport": (
                    "valid longitude/latitude and type != closed; scheduled_service does not filter"
                ),
                "communications": "voice communication rows only"
                if reviewed_export
                else "legacy export: all source frequency rows in communications",
                "runway": (
                    "reviewed export excludes closed runways and runways whose parent airport "
                    "is not visible; legacy export behavior is represented only by actual "
                    "tile counts"
                    if reviewed_export
                    else "legacy export eligibility is not inferred from source code; actual "
                    "tile counts are reported"
                ),
            },
        },
        "source": {
            "name": manifest.get("source", {}).get("name"),
            "revision": REVISION,
            "dataset_revision": dataset_revision,
            "source_updated_at": manifest.get("source", {}).get("updated_at"),
            "inputs": inputs,
            "time_fields": {
                "airports.csv": temporal_columns(input_dir / "airports.csv"),
                "runways.csv": temporal_columns(input_dir / "runways.csv"),
                "airport-frequencies.csv": temporal_columns(input_dir / "airport-frequencies.csv"),
                "interpretation": (
                    "The source-level updated_at exists; these CSV headers contain no per-record "
                    "time field when their lists are empty."
                ),
            },
        },
        "mainland_airports": {
            "source_total": len(mainland),
            "source_by_type": count_by(mainland, "type"),
            "source_by_scheduled_service": count_by(mainland, "scheduled_service"),
            "visible_total": len(visible),
            "visible_by_type": count_by(visible, "type"),
            "visible_by_scheduled_service": count_by(visible, "scheduled_service"),
            "ident_vs_icao_code": dict(sorted(ident_vs_icao.items())),
            "visible_group_coverage": visible_group_coverages,
            "visible_group_coverage_note": (
                "Frequency coverage is airports with one or more linked source frequency rows; "
                "runway_rows is a row count, separately from airports_with_any_runway_row."
            ),
        },
        "frequencies": {
            "all_CN_source_airports": {
                **all_frequency_summary,
                "airport_count_with_any_frequency_row": sum(
                    bool(frequencies_by_ref[clean(row, "id") or ""]) for _, row in mainland
                ),
            },
            "visible_CN_airports": {
                **visible_frequency_summary,
                "airport_count_with_any_frequency_row": sum(
                    bool(frequencies_by_ref[clean(row, "id") or ""]) for _, row in visible
                ),
            },
            "navigation_like_type_pattern": navigation_type_pattern.pattern,
            "navigation_like_frequency_rows": navigation_like_frequencies,
            "navigation_like_interpretation": (
                "Legacy snapshot observation: these source-type candidates are in its sole "
                "communications collection."
                if not reviewed_export
                else "Historical source candidates are retained for comparison; reviewed category "
                "membership is verified from the emitted detail records."
            ),
            "reviewed_export_detail_audit": reviewed_frequency_summary,
        },
        "runways": {
            "all_CN_source_airports": {
                "rows": len(mainland_runway_rows),
                "airport_count_with_any_runway_row": sum(
                    bool(runways_by_ref[clean(row, "id") or ""]) for _, row in mainland
                ),
                "has_complete_endpoints": len(drawable_runways),
                "lacks_complete_endpoints": len(mainland_runway_rows)
                - len(drawable_runways),
                "closed_raw_counts": dict(
                    sorted(
                        Counter(
                            clean(row, "closed") or "(empty)" for _, row in mainland_runway_rows
                        ).items()
                    )
                ),
                "surface_counts": count_by(mainland_runway_rows, "surface"),
                "map_tile_feature_occurrences": sum(
                    map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0)
                    for _, row in mainland_runway_rows
                ),
            },
            "visible_CN_airports": {
                "rows": len(visible_runway_rows),
                "airport_count_with_any_runway_row": sum(
                    bool(runways_by_ref[clean(row, "id") or ""]) for _, row in visible
                ),
                "has_complete_endpoints": len(drawable_visible_runways),
                "lacks_complete_endpoints": len(visible_runway_rows)
                - len(drawable_visible_runways),
                "closed_raw_counts": dict(
                    sorted(
                        Counter(
                            clean(row, "closed") or "(empty)" for _, row in visible_runway_rows
                        ).items()
                    )
                ),
                "surface_counts": count_by(visible_runway_rows, "surface"),
                "map_tile_feature_occurrences": sum(
                    map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0)
                    for _, row in visible_runway_rows
                ),
            },
            "all_exported_runway_tile_feature_occurrences": tiles_total,
            "tile_feature_count_matches_manifest": tiles_total
            == manifest.get("counts", {}).get("runways"),
            "closed_airport_runways_still_in_map": {
                "source_rows": len(closed_airport_runways),
                "drawable_rows": sum(
                    map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0) > 0
                    for _, row in closed_airport_runways
                ),
                "map_tile_feature_occurrences": sum(
                    map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0)
                    for _, row in closed_airport_runways
                ),
                "details": [
                    runway_observation(
                        item, airports_by_id[clean(item[1], "airport_ref")], map_tile_occurrences
                    )
                    for item in closed_airport_runways
                ],
            },
            "closed_runways_at_visible_airports_still_in_map": {
                "source_rows": len(closed_runways_at_visible_airports),
                "drawable_rows": sum(
                    map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0) > 0
                    for _, row in closed_runways_at_visible_airports
                ),
                "map_tile_feature_occurrences": sum(
                    map_tile_occurrences.get(f"ourairports:runway:{clean(row, 'id') or ''}", 0)
                    for _, row in closed_runways_at_visible_airports
                ),
                "details": [
                    runway_observation(
                        item, airports_by_id[clean(item[1], "airport_ref")], map_tile_occurrences
                    )
                    for item in closed_runways_at_visible_airports
                ],
            },
            "geometric_consistency_candidates": {
                "not_official_findings": True,
                "length_method": (
                    "Haversine distance between complete endpoints; candidate when absolute "
                    "difference "
                    ">= 1000 ft and relative difference >= 25% of positive source length_ft."
                ),
                "airport_distance_method": (
                    "Nearest point on the endpoint segment in a local equirectangular plane; "
                    "candidate when airport point distance >= 5 km."
                ),
                "length_candidates": length_difference_candidates,
                "airport_point_distance_candidates": airport_distance_candidates,
            },
        },
        "export_comparison": {
            "cn_search_index_path": str(index_path),
            "cn_search_index_count": len(exported_index),
            "expected_visible_count": len(expected_visible_ids),
            "source_total_minus_export_count": len(mainland) - len(exported_index),
            "index_matches_expected_visible_ids": exported_ids == expected_visible_ids,
            "manifest_coverage": coverage,
            "expected_manifest_coverage": manifest_cn_expected,
            "manifest_coverage_matches_generator_semantics": coverage is not None
            and all(coverage.get(key) == value for key, value in manifest_cn_expected.items()),
            "source_not_in_cn_search_index": missing_export,
            "reviewed_acceptance": reviewed_acceptance,
        },
        "review_samples": samples,
        "suspected_anomalies_for_official_check": {
            "not_official_findings": True,
            "missing_requested_idents": missing_targets,
            "missing_requested_source_ids": [
                source_id
                for source_id in EXTRA_TARGET_SOURCE_IDS
                if source_id not in airports_by_id
            ],
            "closed_or_coordinate_excluded_rows": missing_export,
            "note": (
                "These are frozen-source observations and generator outcomes only. They do not "
                "establish current operating status, civil-transport classification, active "
                "frequency assignment, or official runway condition."
            ),
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(".cache"),
        help="fixed local cache root; never downloaded or changed",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache/mainland-review/mainland-reference-audit.json"),
        help="report path (default: .cache/mainland-review/mainland-reference-audit.json)",
    )
    parser.add_argument(
        "--require-reviewed",
        "--expect-reviewed",
        dest="require_reviewed",
        action="store_true",
        help="require the reviewed frequency/export contract and its correction acceptance checks",
    )
    args = parser.parse_args()
    result = audit(args.cache_root, require_reviewed=args.require_reviewed)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
