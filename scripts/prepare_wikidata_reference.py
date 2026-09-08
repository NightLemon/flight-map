"""Freeze a Wikidata airport-name snapshot; no live query is made during a Pages build.

Inputs are complete SPARQL JSON responses, not HTML/Wikipedia prose.  Structured
Wikidata records are CC0. Coordinates are used only to reject mismatched aliases.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path


def normalize(bindings: dict, countries: dict) -> list[dict]:
    codes: dict[str, set[str]] = {}
    for row in countries["results"]["bindings"]:
        code = row["code"]["value"]
        if re.fullmatch(r"[A-Z]{2}", code):
            codes.setdefault(row["country"]["value"], set()).add(code)
    records: dict[str, dict] = {}
    for row in bindings["results"]["bindings"]:
        value = lambda key, row=row: row.get(key, {}).get("value", "")  # noqa: E731
        entity = value("airport").rsplit("/", 1)[-1]
        icao = value("icao").upper()
        country_codes = codes.get(value("country"), set())
        coordinate = re.fullmatch(r"Point\(([-+\d.eE]+) ([-+\d.eE]+)\)", value("coord"))
        if not re.fullmatch(r"Q\d+", entity) or not re.fullmatch(r"[A-Z0-9]{4}", icao):
            continue
        if len(country_codes) != 1 or coordinate is None:
            continue
        lon, lat = map(float, coordinate.groups())
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            continue
        record = {
            "record_id": entity,
            "url": f"https://www.wikidata.org/wiki/{entity}",
            "icao_id": icao,
            "country": next(iter(country_codes)),
            "coordinates": [lon, lat],
            "name": value("labelEn"),
            "name_zh": value("labelZh"),
        }
        # Retain conflicting rows for the matcher to reject, rather than picking
        # a coordinate or identifier because it happens to be first in the input.
        records[json.dumps(record, sort_keys=True, ensure_ascii=False)] = record
    return [records[key] for key in sorted(records)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw_names = {
        "airports-complete.json": "airports.json.gz",
        "country-codes.json": "countries.json.gz",
    }
    inputs = []
    for name, target in raw_names.items():
        raw = (args.input / name).read_bytes()
        compressed = gzip.compress(raw, mtime=0)
        (args.output / target).write_bytes(compressed)
        inputs.append(
            {
                "path": f"wikidata/{target}",
                "sha256": hashlib.sha256(compressed).hexdigest(),
                "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    records = normalize(
        json.loads((args.input / "airports-complete.json").read_bytes()),
        json.loads((args.input / "country-codes.json").read_bytes()),
    )
    compressed = gzip.compress(
        json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
        mtime=0,
    )
    (args.output / "records.json.gz").write_bytes(compressed)
    for source, target in [
        ("query-complete.rq", "airports.rq"),
        ("country-query.rq", "countries.rq"),
    ]:
        (args.output / target).write_bytes((args.input / source).read_bytes())
    print(
        json.dumps(
            {
                "record_count": len(records),
                "sha256": hashlib.sha256(compressed).hexdigest(),
                "snapshot": "wikidata/records.json.gz",
                "inputs": inputs,
            }
        )
    )


if __name__ == "__main__":
    main()
