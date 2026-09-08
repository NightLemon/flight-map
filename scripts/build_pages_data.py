"""Build the static, public-domain OurAirports reference for GitHub Pages.

The generator deliberately reads only the immutable OurAirports CSV revision.  It
does not read, combine, or publish the local FAA research database.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import urlopen

REVISION = "269b3557e2c784cc41673b77c7fae211d3f61668"
UPSTREAM = "https://raw.githubusercontent.com/davidmegginson/ourairports-data"
SOURCE_PAGE = "https://ourairports.com/data/"
UPDATED_AT = "2026-09-08T01:53:12Z"
INPUT_NAMES = ("airports.csv", "airport-frequencies.csv", "runways.csv", "navaids.csv", "LICENSE")
CSV_NAMES = INPUT_NAMES[:-1]
PINNED_INPUT_HASHES = {
    "airports.csv": "ca72a3404144b9478f51ff145910f2533c18b02a2c77c4a59e8f2274674a26c0",
    "airport-frequencies.csv": "785871bae512cd3d183288b4ba4639108cd4a8e8ab634d5fe3e491e4e516c740",
    "runways.csv": "47afb109bb0b7fa4e3d0b8da909e92ee4e41ee892dbc8cf5a6336e09272188dd",
    "navaids.csv": "57fb332b75be1173c45fd97447611eb3fba07b2c508c2f330961b9a8976e24cb",
    "LICENSE": "6b0382b16279f26ff69014300541967a356a666eb0b91b422f6862f6b7dad17e",
}
REQUIRED_COLUMNS = {
    "airports.csv": {
        "id",
        "ident",
        "type",
        "name",
        "latitude_deg",
        "longitude_deg",
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
        "le_latitude_deg",
        "le_longitude_deg",
        "he_latitude_deg",
        "he_longitude_deg",
    },
    "navaids.csv": {"id", "ident", "name", "type", "latitude_deg", "longitude_deg"},
}


def compact_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(compact_json(value), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_url(name: str, revision: str = REVISION) -> str:
    return f"{UPSTREAM}/{revision}/{name}"


def cached_input(cache_dir: Path, name: str, revision: str = REVISION) -> tuple[Path, str, str]:
    """Download one immutable source, verifying cache bytes before every reuse."""
    destination = cache_dir / revision / name
    checksum_path = destination.with_name(f"{name}.sha256")
    url = source_url(name, revision)
    expected_hash = PINNED_INPUT_HASHES[name]
    if destination.is_file() and checksum_path.is_file():
        expected = checksum_path.read_text(encoding="ascii").strip()
        actual = sha256_file(destination)
        if expected == expected_hash and actual == expected_hash:
            return destination, actual, url
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=90) as response:  # nosec B310: pinned GitHub HTTPS URL
        data = response.read()
    if not data:
        raise ValueError(f"empty upstream input: {name}")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        temporary = Path(temporary_name)
        digest = sha256_file(temporary)
        if digest != expected_hash:
            raise ValueError(f"{name}: SHA-256 does not match the pinned input")
        os.replace(temporary, destination)
        checksum_path.write_text(f"{digest}\n", encoding="ascii")
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return destination, digest, url


def acquire_inputs(
    cache_dir: Path, revision: str = REVISION
) -> tuple[dict[str, Path], list[dict[str, str]]]:
    paths: dict[str, Path] = {}
    inputs: list[dict[str, str]] = []
    if revision != REVISION:
        raise ValueError("only the fixed OurAirports revision is supported")
    for name in INPUT_NAMES:
        path, digest, url = cached_input(cache_dir, name, revision)
        paths[name] = path
        inputs.append({"name": name, "url": url, "sha256": digest})
    return paths, inputs


def text(row: dict[str, str], key: str) -> str | None:
    value = row.get(key, "").strip()
    return value or None


def number(row: dict[str, str], key: str) -> float | None:
    value = text(row, key)
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def coordinates(
    row: dict[str, str], latitude: str = "latitude_deg", longitude: str = "longitude_deg"
) -> list[float] | None:
    lat, lon = number(row, latitude), number(row, longitude)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return [lon, lat]


def required_id(row: dict[str, str], filename: str, line: int) -> str:
    value = text(row, "id")
    if value is None or not value.isdecimal():
        raise ValueError(f"{filename}:{line}: invalid numeric id")
    return value


def csv_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    if path.stat().st_size == 0:
        raise ValueError(f"empty input: {path.name}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS[path.name].issubset(reader.fieldnames):
            raise ValueError(f"{path.name}: missing required columns")
        rows = [(line, dict(row)) for line, row in enumerate(reader, start=2)]
    if not rows:
        raise ValueError(f"{path.name}: contains no data rows")
    return rows


def provenance(filename: str, line: int, digest: str) -> dict[str, Any]:
    return {
        "asset_sha256": digest,
        "member": filename,
        "line": line,
        "locator": f"{filename}:line:{line}",
    }


def record(
    *,
    record_id: str,
    kind: str,
    name: str | None,
    identifier: str | None,
    airport_id: str | None,
    airport_ident: str | None,
    parent_id: str | None,
    geometry: dict[str, Any] | None,
    properties: dict[str, Any],
    source_name: str,
    line: int,
    digest: str,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": kind,
        "name": name or "",
        "identifier": identifier or "",
        "airport_ident": airport_ident,
        "airport_id": airport_id,
        "parent_id": parent_id,
        "branch_id": None,
        "sequence": None,
        "geometry": geometry,
        "properties": properties,
        "provenance": provenance(source_name, line, digest),
    }


def public_properties(record_value: dict[str, Any]) -> dict[str, Any]:
    properties = dict(record_value["properties"])
    properties.update(
        {
            "id": record_value["id"],
            "kind": record_value["kind"],
            "name": record_value["name"],
            "identifier": record_value["identifier"],
            "airport_id": record_value["airport_id"],
            "airport_ident": record_value["airport_ident"],
        }
    )
    return properties


def point_feature(record_value: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": record_value["id"],
        "properties": public_properties(record_value),
        "geometry": record_value["geometry"],
    }


def tile_index(point: list[float]) -> tuple[int, int]:
    x = min(71, max(0, math.floor((point[0] + 180) / 5)))
    y = min(35, max(0, math.floor((point[1] + 90) / 5)))
    return x, y


def clip_segment(
    a: list[float], b: list[float], left: float, right: float, bottom: float, top: float
) -> list[list[float]] | None:
    """Clip a segment to a closed tile rectangle with Liang-Barsky clipping."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    start, end = 0.0, 1.0
    for p, q in ((-dx, a[0] - left), (dx, right - a[0]), (-dy, a[1] - bottom), (dy, top - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        ratio = q / p
        if p < 0:
            if ratio > end:
                return None
            start = max(start, ratio)
        else:
            if ratio < start:
                return None
            end = min(end, ratio)
    if start > end:
        return None
    first, second = [a[0] + start * dx, a[1] + start * dy], [a[0] + end * dx, a[1] + end * dy]
    if first == second:
        return None
    return [first, second]


def runway_geometry(first: list[float], second: list[float]) -> dict[str, Any]:
    """Return the short antimeridian arc while retaining both real endpoints."""
    longitude_delta = second[0] - first[0]
    if -180 <= longitude_delta <= 180:
        return {"type": "LineString", "coordinates": [first, second]}
    boundary = 180.0 if longitude_delta < -180 else -180.0
    adjusted_second = second[0] + (360 if boundary == 180 else -360)
    fraction = (boundary - first[0]) / (adjusted_second - first[0])
    latitude = first[1] + fraction * (second[1] - first[1])
    opposite_boundary = -180.0 if boundary == 180 else 180.0
    return {
        "type": "MultiLineString",
        "coordinates": [
            [first, [boundary, latitude]],
            [[opposite_boundary, latitude], second],
        ],
    }


def runway_segments(geometry: dict[str, Any]) -> list[list[list[float]]]:
    if geometry["type"] == "LineString":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def runway_tile_features(record_value: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    geometry = record_value["geometry"]
    if geometry is None:
        return {}
    tiles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for first, second in runway_segments(geometry):
        min_x = max(0, math.floor((min(first[0], second[0]) + 180) / 5))
        max_x = min(71, math.floor((max(first[0], second[0]) + 180) / 5))
        min_y = max(0, math.floor((min(first[1], second[1]) + 90) / 5))
        max_y = min(35, math.floor((max(first[1], second[1]) + 90) / 5))
        if min_x > max_x or min_y > max_y:
            continue
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                if (
                    clip_segment(
                        first, second, -180 + x * 5, -175 + x * 5, -90 + y * 5, -85 + y * 5
                    )
                    is None
                ):
                    continue
                key = f"{x}-{y}"
                feature = {
                    "type": "Feature",
                    "id": record_value["id"],
                    "properties": public_properties(record_value),
                    "geometry": geometry,
                }
                if feature not in tiles[key]:
                    tiles[key].append(feature)
    return tiles


def airport_properties(row: dict[str, str]) -> dict[str, Any]:
    properties = {
        key: text(row, key)
        for key in (
            "gps_code",
            "iata_code",
            "local_code",
            "municipality",
            "iso_country",
            "iso_region",
            "continent",
            "type",
            "scheduled_service",
            "elevation_ft",
            "home_link",
            "wikipedia_link",
            "keywords",
        )
    }
    properties["icao_id"] = text(row, "icao_code")
    properties["city"] = properties["municipality"]
    properties["country"] = properties["iso_country"]
    return properties


def runway_properties(row: dict[str, str]) -> dict[str, Any]:
    return {
        key: text(row, key)
        for key in (
            "length_ft",
            "width_ft",
            "surface",
            "lighted",
            "closed",
            "le_ident",
            "le_elevation_ft",
            "le_heading_degT",
            "le_displaced_threshold_ft",
            "he_ident",
            "he_elevation_ft",
            "he_heading_degT",
            "he_displaced_threshold_ft",
        )
    }


def navaid_properties(row: dict[str, str]) -> dict[str, Any]:
    properties = {
        key: text(row, key)
        for key in (
            "filename",
            "type",
            "frequency_khz",
            "elevation_ft",
            "iso_country",
            "dme_frequency_khz",
            "dme_channel",
            "dme_latitude_deg",
            "dme_longitude_deg",
            "dme_elevation_ft",
            "slaved_variation_deg",
            "magnetic_variation_deg",
            "usageType",
            "power",
            "associated_airport",
        )
    }
    properties["country"] = properties["iso_country"]
    return properties


def build(
    source_paths: dict[str, Path],
    output_dir: Path,
    revision: str = REVISION,
    inputs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build an immutable version directory from local CSV paths and return its manifest."""
    if set(source_paths) != set(INPUT_NAMES):
        raise ValueError("source paths must contain exactly the four CSV files and LICENSE")
    for name, path in source_paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing or empty input: {name}")
    output_path = output_dir.resolve()
    if any(path.resolve().is_relative_to(output_path) for path in source_paths.values()):
        raise ValueError("source inputs must not be inside the generated output")
    if output_path.exists() and any(output_path.iterdir()):
        manifest_path = output_path / "manifest.json"
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError(
                "refusing to replace a non-generated non-empty output directory"
            ) from None
        source = existing_manifest.get("source", {})
        if (
            existing_manifest.get("schema") != 1
            or source.get("name") != "OurAirports"
            or source.get("url") != SOURCE_PAGE
            or source.get("license") != "Public Domain"
        ):
            raise ValueError("refusing to replace a non-generated non-empty output directory")
    computed_inputs = [
        {"name": name, "url": source_url(name, revision), "sha256": sha256_file(source_paths[name])}
        for name in INPUT_NAMES
    ]
    input_entries = sorted(inputs or computed_inputs, key=lambda item: item["name"])
    if {item["name"] for item in input_entries} != set(INPUT_NAMES):
        raise ValueError("input metadata is incomplete")
    input_hashes = {item["name"]: item["sha256"] for item in input_entries}
    rows = {name: csv_rows(source_paths[name]) for name in CSV_NAMES}
    airports: dict[str, dict[str, Any]] = {}
    for line, row in rows["airports.csv"]:
        source_id = required_id(row, "airports.csv", line)
        record_id = f"ourairports:airport:{source_id}"
        if record_id in airports:
            raise ValueError(f"airports.csv:{line}: duplicate id")
        point = coordinates(row)
        geometry = {"type": "Point", "coordinates": point} if point else None
        airports[record_id] = record(
            record_id=record_id,
            kind="airport",
            name=text(row, "name"),
            identifier=text(row, "ident"),
            airport_id=None,
            airport_ident=text(row, "ident"),
            parent_id=None,
            geometry=geometry,
            properties=airport_properties(row),
            source_name="airports.csv",
            line=line,
            digest=input_hashes["airports.csv"],
        )
    communications: list[dict[str, Any]] = []
    for line, row in rows["airport-frequencies.csv"]:
        source_id = required_id(row, "airport-frequencies.csv", line)
        parent_source_id = text(row, "airport_ref")
        parent_id = (
            f"ourairports:airport:{parent_source_id}"
            if parent_source_id and parent_source_id.isdecimal()
            else None
        )
        communications.append(
            record(
                record_id=f"ourairports:communication:{source_id}",
                kind="communication",
                name=text(row, "description") or text(row, "type"),
                identifier=text(row, "airport_ident") or source_id,
                airport_id=parent_id,
                airport_ident=text(row, "airport_ident"),
                parent_id=parent_id,
                geometry=None,
                properties={
                    "service": text(row, "type"),
                    "frequency": text(row, "frequency_mhz"),
                    "unit": "MHz",
                    "remarks": text(row, "description"),
                },
                source_name="airport-frequencies.csv",
                line=line,
                digest=input_hashes["airport-frequencies.csv"],
            )
        )
    runways: list[dict[str, Any]] = []
    for line, row in rows["runways.csv"]:
        source_id = required_id(row, "runways.csv", line)
        parent_source_id = text(row, "airport_ref")
        parent_id = (
            f"ourairports:airport:{parent_source_id}"
            if parent_source_id and parent_source_id.isdecimal()
            else None
        )
        endpoints = (
            coordinates(row, "le_latitude_deg", "le_longitude_deg"),
            coordinates(row, "he_latitude_deg", "he_longitude_deg"),
        )
        geometry = runway_geometry(endpoints[0], endpoints[1]) if all(endpoints) else None
        runways.append(
            record(
                record_id=f"ourairports:runway:{source_id}",
                kind="runway",
                name=text(row, "le_ident") or text(row, "he_ident") or source_id,
                identifier=text(row, "le_ident") or text(row, "he_ident") or source_id,
                airport_id=parent_id,
                airport_ident=text(row, "airport_ident"),
                parent_id=parent_id,
                geometry=geometry,
                properties=runway_properties(row),
                source_name="runways.csv",
                line=line,
                digest=input_hashes["runways.csv"],
            )
        )
    navaids: list[dict[str, Any]] = []
    for line, row in rows["navaids.csv"]:
        source_id = required_id(row, "navaids.csv", line)
        point = coordinates(row)
        navaids.append(
            record(
                record_id=f"ourairports:navaid:{source_id}",
                kind="navaid",
                name=text(row, "name"),
                identifier=text(row, "ident"),
                airport_id=None,
                airport_ident=text(row, "associated_airport"),
                parent_id=None,
                geometry={"type": "Point", "coordinates": point} if point else None,
                properties=navaid_properties(row),
                source_name="navaids.csv",
                line=line,
                digest=input_hashes["navaids.csv"],
            )
        )
    by_airport: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"communications": [], "runways": []}
    )
    for item in communications:
        if item["airport_id"]:
            by_airport[item["airport_id"]]["communications"].append(item)
    for item in runways:
        if item["airport_id"]:
            by_airport[item["airport_id"]]["runways"].append(item)
    tile_data: dict[str, dict[str, list[dict[str, Any]]]] = {
        "airports": defaultdict(list),
        "runways": defaultdict(list),
        "navaids": defaultdict(list),
    }
    visible_airports = []
    for item in airports.values():
        if item["geometry"] and item["properties"].get("type") != "closed":
            x, y = tile_index(item["geometry"]["coordinates"])
            tile_data["airports"][f"{x}-{y}"].append(point_feature(item))
            visible_airports.append(item)
    for item in runways:
        for key, features in runway_tile_features(item).items():
            tile_data["runways"][key].extend(features)
    visible_navaids = [item for item in navaids if item["geometry"]]
    for item in visible_navaids:
        point = item["geometry"]["coordinates"]
        tile_data["navaids"][f"{tile_index(point)[0]}-{tile_index(point)[1]}"].append(
            point_feature(item)
        )
    tile_names = {
        layer: sorted(tiles, key=lambda value: tuple(map(int, value.split("-"))))
        for layer, tiles in tile_data.items()
    }
    manifest = {
        "schema": 1,
        "source": {
            "name": "OurAirports",
            "url": SOURCE_PAGE,
            "license": "Public Domain",
            "license_url": SOURCE_PAGE,
            "revision": revision,
            "updated_at": UPDATED_AT,
        },
        "inputs": input_entries,
        "counts": {
            "airports": len(visible_airports),
            "runways": sum(len(value) for value in tile_data["runways"].values()),
            "navaids": len(visible_navaids),
            "communications": len(communications),
        },
        "source_counts": {
            "airports": len(airports),
            "runways": len(runways),
            "navaids": len(navaids),
            "communications": len(communications),
        },
        "tiles": tile_names,
        "disclaimer": (
            "OurAirports data is in the Public Domain and comes with no guarantee of accuracy "
            "or fitness for use. This static reference excludes FAA data, procedures, waypoints, "
            "and airways."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pages-reference-", dir=output_path.parent))
    try:
        version_dir = staging / revision
        for layer, tiles in tile_data.items():
            for key, features in tiles.items():
                write_json(
                    version_dir / "tiles" / layer / f"{key}.json",
                    {
                        "type": "FeatureCollection",
                        "features": sorted(features, key=lambda value: value["id"]),
                    },
                )
        search = [
            {
                "id": item["id"],
                "identifier": item["identifier"],
                "name": item["name"],
                "icao_id": item["properties"].get("icao_id"),
                "iata_code": item["properties"].get("iata_code"),
                "municipality": item["properties"].get("municipality"),
                "country": item["properties"].get("iso_country"),
                "coordinates": item["geometry"]["coordinates"],
            }
            for item in visible_airports
        ]
        write_json(
            version_dir / "search.json",
            sorted(search, key=lambda value: (value["identifier"], value["id"])),
        )
        buckets: dict[int, dict[str, Any]] = defaultdict(dict)
        for airport_id, airport in airports.items():
            source_id = int(airport_id.rsplit(":", 1)[1])
            related = by_airport[airport_id]
            buckets[source_id % 256][airport_id] = {
                "airport": airport,
                "communications": sorted(related["communications"], key=lambda value: value["id"]),
                "runways": sorted(related["runways"], key=lambda value: value["id"]),
            }
        for bucket, values in buckets.items():
            write_json(version_dir / "airports" / f"{bucket}.json", values)
        shutil.copyfile(source_paths["LICENSE"], version_dir / "LICENSE")
        write_json(staging / "manifest.json", manifest)
        if output_path.exists():
            shutil.rmtree(output_path)
        os.replace(staging, output_path)
    except Exception:
        if staging.parent == output_path.parent and staging.name.startswith(".pages-reference-"):
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".cache/pages-public/reference"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/pages-input"))
    args = parser.parse_args()
    paths, inputs = acquire_inputs(args.cache)
    manifest = build(paths, args.output, REVISION, inputs)
    print(
        compact_json(
            {"output": str(args.output), "revision": REVISION, "counts": manifest["counts"]}
        )
    )


if __name__ == "__main__":
    main()
