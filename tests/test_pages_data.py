from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "build_pages_data", Path("scripts/build_pages_data.py")
)
assert SPEC and SPEC.loader
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)


def write_sources(root: Path, airport_latitude: str = "NaN") -> dict[str, Path]:
    # Entirely synthetic inputs; no official aeronautical records are fixtures.
    contents = {
        "airports.csv": "\n".join(
            [
                "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,iso_country,municipality,icao_code,gps_code,iata_code",
                "1,OPEN,small_airport,Open,40.0,-73.0,10,US,Town,KICAO,KGPS,OPN",
                "2,CLOSE,closed,Closed,41,-74,11,US,Else,KCLS,KGPS,CLS",
                f"3,BAD,small_airport,Bad,{airport_latitude},-75,12,US,Else,KBAD,KGPS,BAD",
            ]
        )
        + "\n",
        "airport-frequencies.csv": "\n".join(
            [
                "id,airport_ref,airport_ident,type,description,frequency_mhz",
                "5,1,OPEN,CTAF,Common traffic,122.8",
            ]
        )
        + "\n",
        "runways.csv": "\n".join(
            [
                "id,airport_ref,airport_ident,le_ident,le_latitude_deg,le_longitude_deg,he_ident,he_latitude_deg,he_longitude_deg,length_ft,surface",
                "7,1,OPEN,09,10,179,27,11,-179,1000,ASP",
                "8,1,OPEN,01,,,,19,1,1,800,GRS",
            ]
        )
        + "\n",
        "navaids.csv": "\n".join(
            [
                "id,ident,name,type,frequency_khz,latitude_deg,longitude_deg,iso_country",
                "9,NAV,Nav,VOR,11300,0,0,US",
                "10,BAD,Bad,VOR,11400,NaN,0,US",
            ]
        )
        + "\n",
        "LICENSE": "Public domain test license\n",
    }
    root.mkdir(parents=True)
    paths = {}
    for name, value in contents.items():
        path = root / name
        path.write_text(value, encoding="utf-8")
        paths[name] = path
    return paths


def test_build_is_deterministic_and_preserves_public_boundary(tmp_path: Path) -> None:
    paths = write_sources(tmp_path / "input")
    first, second = tmp_path / "first", tmp_path / "second"
    manifest = pages.build(paths, first)
    pages.build(paths, second)
    revision = manifest["dataset_revision"]
    assert manifest["counts"] == {
        "airports": 1,
        "runways": 2,
        "navaids": 1,
        "communications": 1,
        "navigation_frequencies": 0,
        "unclassified_frequencies": 0,
    }
    assert manifest["source_counts"] == {
        "airports": 3,
        "runways": 2,
        "navaids": 2,
        "communications": 1,
    }
    assert (
        json.loads((first / "manifest.json").read_text(encoding="utf-8"))["inputs"][0]["sha256"]
        == hashlib.sha256(paths["LICENSE"].read_bytes()).hexdigest()
    )
    assert (first / revision / "LICENSE").read_text(encoding="utf-8") == paths["LICENSE"].read_text(
        encoding="utf-8"
    )
    assert json.loads((first / revision / "search.json").read_text(encoding="utf-8")) == [
        {
            "coordinates": [-73.0, 40.0],
            "country": "US",
            "iata_code": "OPN",
            "icao_id": "KICAO",
            "id": "ourairports:airport:1",
            "identifier": "OPEN",
            "municipality": "Town",
            "name": "Open",
            "aliases": [],
            "type": "small_airport",
            "scheduled_service": None,
        }
    ]
    bucket = json.loads((first / revision / "airports" / "1.json").read_text(encoding="utf-8"))[
        "ourairports:airport:1"
    ]
    assert bucket["communications"][0]["parent_id"] == "ourairports:airport:1"
    assert bucket["communications"][0]["properties"]["frequency"] == "122.8"
    assert bucket["runways"][1]["geometry"] is None
    assert bucket["navigation_frequencies"] == bucket["unclassified_frequencies"] == []
    assert bucket["review_notes"] == []
    assert manifest["review"] is None
    assert not (first / revision / "review.json").exists()
    assert not any("C:" in value.read_text(encoding="utf-8") for value in first.rglob("*.json"))
    assert {path.relative_to(first) for path in first.rglob("*") if path.is_file()} == {
        path.relative_to(second) for path in second.rglob("*") if path.is_file()
    }
    for relative in (path.relative_to(first) for path in first.rglob("*") if path.is_file()):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_runway_date_line_is_short_and_missing_endpoints_are_not_tiled(tmp_path: Path) -> None:
    output = tmp_path / "out"
    manifest = pages.build(write_sources(tmp_path / "input"), output)
    tiles = output / manifest["dataset_revision"] / "tiles" / "runways"
    west = json.loads((tiles / "71-20.json").read_text(encoding="utf-8"))["features"]
    east = json.loads((tiles / "0-20.json").read_text(encoding="utf-8"))["features"]
    assert [feature["id"] for feature in west] == ["ourairports:runway:7"]
    assert [feature["id"] for feature in east] == ["ourairports:runway:7"]
    assert (
        west[0]["geometry"]
        == east[0]["geometry"]
        == {
            "type": "MultiLineString",
            "coordinates": [[[179.0, 10.0], [180.0, 10.5]], [[-180.0, 10.5], [-179.0, 11.0]]],
        }
    )
    assert not any("runway:8" in file.read_text(encoding="utf-8") for file in tiles.rglob("*.json"))


def test_crossing_tiles_repeat_the_complete_feature_geometry() -> None:
    geometry = {"type": "LineString", "coordinates": [[-76.0, 40.0], [-69.0, 40.0]]}
    record = {
        "id": "ourairports:runway:11",
        "kind": "runway",
        "name": "01",
        "identifier": "01",
        "airport_id": "ourairports:airport:1",
        "airport_ident": "OPEN",
        "properties": {},
        "geometry": geometry,
    }
    tiles = pages.runway_tile_features(record)
    assert set(tiles) == {"20-26", "21-26", "22-26"}
    assert {item[0]["id"] for item in tiles.values()} == {"ourairports:runway:11"}
    assert all(item[0]["geometry"] == geometry for item in tiles.values())


def test_date_line_interpolation_preserves_the_short_arc_in_both_directions() -> None:
    westbound = pages.runway_geometry([179.0, 10.0], [-179.0, 11.0])
    eastbound = pages.runway_geometry([-179.0, 10.0], [179.0, 11.0])
    assert westbound["coordinates"] == [
        [[179.0, 10.0], [180.0, 10.5]],
        [[-180.0, 10.5], [-179.0, 11.0]],
    ]
    assert eastbound["coordinates"] == [
        [[-179.0, 10.0], [-180.0, 10.5]],
        [[180.0, 10.5], [179.0, 11.0]],
    ]


def test_non_generated_nonempty_output_is_not_removed(tmp_path: Path) -> None:
    paths = write_sources(tmp_path / "input")
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="non-generated"):
        pages.build(paths, output)
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "filename,content",
    [
        ("airports.csv", ""),
        ("runways.csv", "id,airport_ref\n7,1\n"),
    ],
)
def test_invalid_or_empty_inputs_fail_closed(tmp_path: Path, filename: str, content: str) -> None:
    paths = write_sources(tmp_path / "input")
    paths[filename].write_text(content, encoding="utf-8")
    output = tmp_path / "out"
    with pytest.raises(ValueError):
        pages.build(paths, output)
    assert not output.exists()


def test_country_indexes_cover_the_visible_airports_and_count_frequency_gaps(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    manifest = pages.build(write_sources(tmp_path / "input"), output)
    assert manifest["coverage"] == [
        {
            "country": "US",
            "airports": 1,
            "airports_with_communications": 1,
            "airports_with_frequencies": 1,
            "runways": 2,
            "navaids": 1,
            "enriched_airports": 0,
        }
    ]
    version = output / manifest["dataset_revision"]
    assert json.loads((version / "search/US.json").read_text(encoding="utf-8")) == json.loads(
        (version / "search.json").read_text(encoding="utf-8")
    )
    assert manifest["source"]["revision"] == pages.REVISION
    assert manifest["dataset_revision"] != pages.REVISION


def synthetic_reference(**changes: object) -> dict:
    # All values here are synthetic. No live aeronautical records are fixtures.
    return {
        "record_id": "Q1",
        "icao_id": "TEST",
        "country": "US",
        "coordinates": [-73.0, 40.0],
        "name": "Synthetic alias",
        "name_zh": "合成机场",
        "url": "https://example.invalid/Q1",
        **changes,
    }


def synthetic_source(records: list[dict]) -> dict:
    return {
        "id": "synthetic",
        "name": "Synthetic source",
        "records": records,
        "updated_at": "2026-09-08T00:00:00Z",
    }


def test_reference_matching_rejects_country_code_ambiguity_and_distant_coordinates() -> None:
    airport = {
        "id": "ourairports:airport:1",
        "geometry": {"type": "Point", "coordinates": [-73.0, 40.0]},
        "properties": {"icao_id": "TEST", "iso_country": "US"},
    }
    refs, reports = pages.associate_references(
        [airport],
        [
            synthetic_source(
                [
                    synthetic_reference(),
                    synthetic_reference(icao_id="ELSE", country="CA"),
                ]
            )
        ],
    )
    assert refs[airport["id"]][0]["name_zh"] == "合成机场"
    assert reports[0]["matched"] == 1
    assert reports[0]["unmatched"] == 1
    assert "name_zh" not in airport["properties"]
    for records, base, expected in [
        ([synthetic_reference(), synthetic_reference(record_id="Q2")], [airport], "ambiguous"),
        ([synthetic_reference()], [airport, {**airport, "id": "other"}], "ambiguous"),
        ([synthetic_reference(coordinates=[-70.0, 40.0])], [airport], "coordinate_mismatch"),
        ([synthetic_reference(coordinates=None)], [airport], "invalid"),
        ([synthetic_reference(country="CA")], [airport], "unmatched"),
    ]:
        result, report = pages.associate_references(base, [synthetic_source(records)])
        assert not result
        assert report[0][expected] == len(records)


def test_unreviewed_or_tampered_reference_snapshots_cannot_publish(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema": 1,
                "sources": [
                    {
                        "license_status": "review-required",
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="unreviewed"):
        pages.load_reference_sources(catalog)
    (tmp_path / "snapshot.json.gz").write_bytes(b"tampered")
    catalog.write_text(
        json.dumps(
            {
                "schema": 1,
                "sources": [
                    {
                        "license_status": "public-domain",
                        "snapshot": "snapshot.json.gz",
                        "sha256": "0" * 64,
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        pages.load_reference_sources(catalog)


def test_checked_in_reference_snapshots_match_the_reviewed_hashes() -> None:
    sources = pages.load_reference_sources(pages.REFERENCE_CATALOG)
    assert sources
    assert all(source["records"] for source in sources)


def test_reference_export_preserves_original_fields_and_snapshot_clock(tmp_path: Path) -> None:
    paths = write_sources(tmp_path / "input")
    paths["airports.csv"].write_text(
        paths["airports.csv"].read_text(encoding="utf-8").replace("KICAO", "TEST"), encoding="utf-8"
    )
    source = {
        **synthetic_source([synthetic_reference()]),
        "url": "https://example.invalid/",
        "license": "CC0",
        "license_url": "https://example.invalid/license",
        "date_kind": "retrieved_at",
        "scope": "Synthetic names only",
        "sha256": "0" * 64,
    }
    output = tmp_path / "out"
    manifest = pages.build(paths, output, reference_sources=[source])
    assert manifest["sources"][1]["date_kind"] == "retrieved_at"
    assert manifest["sources"][1]["airport_count"] == 1
    assert manifest["coverage"][0]["enriched_airports"] == 1
    version = output / manifest["dataset_revision"]
    bucket = json.loads((version / "airports/1.json").read_text(encoding="utf-8"))
    detail = bucket["ourairports:airport:1"]
    assert detail["airport"]["name"] == "Open"
    assert detail["communications"][0]["properties"]["frequency"] == "122.8"
    assert detail["references"][0]["name_zh"] == "合成机场"
    assert json.loads((version / "search/US.json").read_text(encoding="utf-8"))[0]["aliases"] == [
        "Synthetic alias",
        "合成机场",
    ]
    changed = pages.build(
        paths, tmp_path / "changed", reference_sources=[{**source, "sha256": "1" * 64}]
    )
    assert changed["source"]["revision"] == manifest["source"]["revision"]
    assert changed["dataset_revision"] != manifest["dataset_revision"]


def test_wikidata_normalization_reproduces_frozen_snapshot_from_raw_inputs() -> None:
    spec = importlib.util.spec_from_file_location(
        "prepare_wikidata_reference", Path("scripts/prepare_wikidata_reference.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = pages.REFERENCE_CATALOG.parent / "wikidata"

    def read(name: str) -> object:
        return json.loads(gzip.decompress((root / name).read_bytes()))

    assert module.normalize(read("airports.json.gz"), read("countries.json.gz")) == read(
        "records.json.gz"
    )


def replace_csv(path: Path, rows: list[dict]) -> None:
    """Write synthetic test rows, retaining all supplied raw columns."""
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_detail(output: Path, manifest: dict, airport_id: int = 1) -> dict:
    bucket = output / manifest["dataset_revision"] / "airports" / f"{airport_id % 256}.json"
    return json.loads(bucket.read_text(encoding="utf-8"))[f"ourairports:airport:{airport_id}"]


def test_closed_and_nonvisible_parent_runways_stay_in_details_but_never_on_map(
    tmp_path: Path,
) -> None:
    paths = write_sources(tmp_path / "input")
    original = dict(pages.csv_rows(paths["runways.csv"])[0][1])
    runways = [
        {**original, "id": "7", "closed": "0"},
        {**original, "id": "8", "closed": "1"},
        {**original, "id": "9", "airport_ref": "2", "airport_ident": "CLOSE", "closed": "0"},
        {**original, "id": "10", "airport_ref": "999", "airport_ident": "MISSING"},
        {**original, "id": "11", "airport_ref": "3", "airport_ident": "BAD"},
        {**original, "id": "12", "airport_ref": "", "airport_ident": "NONE"},
    ]
    replace_csv(paths["runways.csv"], runways)
    output = tmp_path / "out"
    manifest = pages.build(paths, output)
    version = output / manifest["dataset_revision"]
    features = [
        feature
        for tile in (version / "tiles/runways").glob("*.json")
        for feature in json.loads(tile.read_text(encoding="utf-8"))["features"]
    ]
    assert {feature["id"] for feature in features} == {"ourairports:runway:7"}
    assert manifest["counts"]["runways"] == 2  # The original date-line tile repetition.
    assert manifest["source_counts"]["runways"] == 6
    assert manifest["coverage"][0]["runways"] == 2  # Includes the closed source detail.
    detail = read_detail(output, manifest)
    assert [runway["id"] for runway in detail["runways"]] == [
        "ourairports:runway:7",
        "ourairports:runway:8",
    ]
    active, closed = detail["runways"]
    assert closed["properties"]["closed"] == "1"
    assert active["geometry"] == closed["geometry"] == features[0]["geometry"]
    for key in ("le_latitude_deg", "le_longitude_deg", "he_latitude_deg", "he_longitude_deg"):
        assert active["properties"][key] == closed["properties"][key] == original[key]
    closed_parent = read_detail(output, manifest, 2)
    assert closed_parent["airport"]["properties"]["type"] == "closed"
    assert closed_parent["runways"][0]["geometry"] == active["geometry"]
    assert read_detail(output, manifest, 3)["runways"][0]["geometry"] == active["geometry"]


@pytest.mark.parametrize(
    "service",
    [
        "TWR",
        "TOWER",
        "TWR01",
        "WuHai TWR",
        "ZUPL_TWR",
        "APP",
        "APPR",
        "GND01",
        "ATIS-I",
        "ATIS-O",
        "ATIS-I/O",
        "ATIS DEP",
        "CLD",
        "DEL",
        "DCL",
        "CTAF",
        "UNIC",
        "AWOS",
        "ASOS",
        "AFIS",
        "A/D",
        "A/G",
        "APP/DEP",
        "RCO",
        "RDO",
        "PMSV",
        "CLNC DEL",
        "LCL",
        "  twr  ",
    ],
)
def test_explicit_communication_source_types(service: str) -> None:
    assert pages.frequency_category(service) == "communication"


@pytest.mark.parametrize(
    "service",
    [
        "ILS",
        "LOC",
        "GP",
        "GS",
        "VOR",
        "NDB",
        "DME",
        "TACAN",
        "GP 19",
        "LOC 19",
        "RWY 13 DME",
        "RWY 31 ILS",
        "WUA VOR/DME",
        "ILS/DME",
        "VOR/TACAN",
        "VOR-DME",
        "ABC VOR-DME",
        "ABC - VOR",
        "ILS - XYZ",
        "ILS Rw 32/14",
        "ILS RWY14",
        "ILS RWY 32",
        "ILS RW27",
    ],
)
def test_explicit_navigation_source_types(service: str) -> None:
    assert pages.frequency_category(service) == "navigation"


@pytest.mark.parametrize(
    "service",
    [
        None,
        "",
        "MISC",
        "VHF",
        "APPLES",
        "HAPPY",
        "APP UNKNOWN",
        "AP01",
        "APN01",
        "ILS/TWR",
        "APP/ILS",
        "TWR ILS",
        "VOR ATIS",
        "ILS mystery",
        "ALIEN VOR THING",
        "ATIS/VOR",
    ],
)
def test_unknown_and_conflicting_frequency_types_are_retained_as_unclassified(service: str) -> None:
    assert pages.frequency_category(service) == "unclassified"


def test_frequency_partition_preserves_ids_raw_values_provenance_and_total_rows(
    tmp_path: Path,
) -> None:
    paths = write_sources(tmp_path / "input", airport_latitude="42")
    values = [
        ("5", "1", "OPEN", "WuHai TWR", "329.3"),  # Deliberately atypical synthetic MHz.
        ("6", "1", "OPEN", "LOC 19", "118.000"),
        ("7", "1", "OPEN", "VOR/DME", "113.20"),
        ("8", "1", "OPEN", "ILS/TWR", "121.7"),
        ("9", "1", "OPEN", "APPLIANCE", "not-a-number"),
        ("10", "2", "CLOSE", "TWR", "121.7"),
        ("11", "3", "BAD", "NDB", "299"),
        ("12", "3", "BAD", "UNKNOWN", ""),
    ]
    replace_csv(
        paths["airport-frequencies.csv"],
        [
            {
                "id": source_id,
                "airport_ref": airport_ref,
                "airport_ident": ident,
                "type": service,
                "description": f"Synthetic remark {source_id}",
                "frequency_mhz": frequency,
            }
            for source_id, airport_ref, ident, service, frequency in values
        ],
    )
    output = tmp_path / "out"
    manifest = pages.build(paths, output)
    expected_counts = {
        "communications": 2,
        "navigation_frequencies": 3,
        "unclassified_frequencies": 3,
    }
    assert {key: manifest["counts"][key] for key in expected_counts} == expected_counts
    assert (
        sum(expected_counts.values()) == manifest["source_counts"]["communications"] == len(values)
    )
    coverage = manifest["coverage"][0]
    assert coverage["airports_with_communications"] == 1
    assert coverage["airports_with_frequencies"] == coverage["airports"] == 2
    exported = {}
    for airport_id in (1, 2, 3):
        detail = read_detail(output, manifest, airport_id)
        for category, collection in pages.FREQUENCY_COLLECTIONS.items():
            for item in detail[collection]:
                assert item["properties"]["frequency_category"] == category
                assert item["id"] not in exported
                exported[item["id"]] = item
    assert len(exported) == len(values)
    for line, (source_id, airport_ref, ident, service, frequency) in enumerate(values, 2):
        item = exported[f"ourairports:communication:{source_id}"]
        assert item["kind"] == "communication"
        assert item["airport_id"] == item["parent_id"] == f"ourairports:airport:{airport_ref}"
        assert item["airport_ident"] == ident
        assert item["properties"]["service"] == service
        assert item["properties"]["frequency"] == (frequency or None)
        assert item["properties"]["unit"] == "MHz"
        assert item["properties"]["remarks"] == f"Synthetic remark {source_id}"
        assert item["provenance"] == {
            "asset_sha256": pages.sha256_file(paths["airport-frequencies.csv"]),
            "member": "airport-frequencies.csv",
            "line": line,
            "locator": f"airport-frequencies.csv:line:{line}",
        }


def synthetic_review() -> dict:
    # Synthetic airport 1 and runway 7, with reserved example.invalid evidence.
    return {
        "schema": 1,
        "source_revision": pages.REVISION,
        "reviewed_at": "2026-09-08",
        "corrections": [
            {
                "id": "synthetic-name",
                "airport_id": "ourairports:airport:1",
                "record_id": "ourairports:airport:1",
                "field": "name",
                "original_value": "Open",
                "value": "Synthetic Bozhou Airport",
                "status": "corrected",
                "message": "Synthetic name correction only",
                "evidence": [
                    {
                        "title": "Synthetic evidence",
                        "url": "https://example.invalid/review",
                        "published_at": "2026-09-01",
                    }
                ],
            }
        ],
        "notes": [
            {
                "id": "synthetic-runway-review",
                "airport_id": "ourairports:airport:1",
                "record_id": "ourairports:runway:7",
                "field": "properties.length_ft",
                "original_value": "1000",
                "status": "needs_review",
                "message": "Synthetic mismatch; keep original dimensions and endpoints",
                "evidence": [
                    {
                        "title": "Synthetic runway evidence",
                        "url": "http://example.invalid/rwy",
                        "published_at": "2026-09-02",
                    }
                ],
            }
        ],
    }


def test_review_name_correction_is_consistent_and_keeps_original_fields_and_exact_catalog(
    tmp_path: Path,
) -> None:
    paths = write_sources(tmp_path / "input")
    old_name = "Synthetic Bozhou Airport (under construction)"
    paths["airports.csv"].write_text(
        paths["airports.csv"].read_text(encoding="utf-8").replace(",Open,", f",{old_name},"),
        encoding="utf-8",
    )
    review = synthetic_review()
    review["corrections"][0]["original_value"] = old_name
    review["notes"].append(
        {
            **review["notes"][0],
            "id": "synthetic-airport-review",
            "record_id": "ourairports:airport:1",
            "field": "properties.scheduled_service",
            "original_value": None,
        }
    )
    catalog = tmp_path / "review.json"
    raw = (json.dumps(review, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    catalog.write_bytes(raw)
    assert pages.load_review_catalog(catalog) == review
    plain_output, output = tmp_path / "plain", tmp_path / "out"
    plain = pages.build(paths, plain_output)
    manifest = pages.build(paths, output, review_catalog=catalog)
    assert manifest["review"] == {
        "reviewed_at": "2026-09-08",
        "source_revision": pages.REVISION,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "correction_count": 1,
        "note_count": 2,
    }
    version = output / manifest["dataset_revision"]
    assert (version / "review.json").read_bytes() == raw
    detail = read_detail(output, manifest)
    original = read_detail(plain_output, plain)
    expected = review["corrections"][0]["value"]
    assert detail["airport"]["name"] == expected
    assert detail["airport"]["properties"]["original_name"] == old_name
    assert detail["airport"]["provenance"] == original["airport"]["provenance"]
    assert detail["airport"]["geometry"] == original["airport"]["geometry"]
    assert detail["runways"] == original["runways"]
    assert detail["communications"] == original["communications"]
    assert detail["review_notes"] == [
        {**entry, "reviewed_at": review["reviewed_at"]}
        for entry in [*review["corrections"], *review["notes"]]
    ]
    for filename in ("search.json", "search/US.json"):
        hit = json.loads((version / filename).read_text(encoding="utf-8"))[0]
        assert hit["name"] == expected
        assert old_name in hit["aliases"]
    feature = json.loads(next((version / "tiles/airports").glob("*.json")).read_text())["features"][
        0
    ]
    assert feature["properties"]["name"] == expected
    assert feature["properties"]["original_name"] == old_name
    assert plain["dataset_revision"] != manifest["dataset_revision"]


@pytest.mark.parametrize(
    "target,key,value,error",
    [
        ("catalog", "schema", 2, "schema"),
        ("catalog", "schema", True, "schema"),
        ("catalog", "source_revision", "0" * 40, "source_revision mismatch"),
        ("catalog", "reviewed_at", "2026-02-30", "reviewed_at date"),
        ("catalog", "reviewed_at", "2026-09-08T00:00:00Z", "reviewed_at date"),
        ("catalog", "unknown", "value", "schema fields"),
        ("correction", "original_value", "outdated value", "original_value mismatch"),
        ("correction", "record_id", "ourairports:airport:999", "record not found"),
        ("correction", "airport_id", "ourairports:airport:2", "association mismatch"),
        ("correction", "field", "geometry.coordinates", "unsupported review field"),
        ("correction", "field", "properties.scheduled_service", "only airport name"),
        ("correction", "status", "needs_review", "status"),
        ("correction", "extra", "unknown", "entry fields"),
        ("note", "original_value", "2000", "original_value mismatch"),
        ("note", "airport_id", "ourairports:airport:2", "association mismatch"),
        ("note", "record_id", "ourairports:runway:999", "record not found"),
        ("note", "value", "2000", "entry fields"),
        ("evidence", "url", "javascript:alert(1)", "unsafe.*URL"),
        ("evidence", "url", "file:///C:/private.txt", "unsafe.*URL"),
        ("evidence", "url", "https://", "unsafe.*URL"),
        ("evidence", "url", "https://example.invalid:bad/", "unsafe.*URL"),
        ("evidence", "url", "https://user:password@example.invalid/", "unsafe.*URL"),
        ("evidence", "url", "https://example.invalid/\n", "unsafe.*URL"),
        ("evidence", "published_at", "2026-13-01", "published_at date"),
        ("evidence", "extra", "unknown", "evidence fields"),
    ],
)
def test_invalid_reviews_fail_before_output(
    tmp_path: Path,
    target: str,
    key: str,
    value: object,
    error: str,
) -> None:
    paths = write_sources(tmp_path / "input")
    review = synthetic_review()
    entry = {
        "catalog": review,
        "correction": review["corrections"][0],
        "note": review["notes"][0],
        "evidence": review["corrections"][0]["evidence"][0],
    }[target]
    entry[key] = value
    output = tmp_path / "out"
    with pytest.raises(ValueError, match=error):
        pages.build(paths, output, review_catalog=review)
    assert not output.exists()


def test_review_content_and_export_semantics_participate_in_dataset_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(tmp_path / "input")
    review = synthetic_review()
    first = pages.build(paths, tmp_path / "first", review_catalog=review)
    review["notes"][0]["message"] += " Updated synthetic review finding."
    second = pages.build(paths, tmp_path / "second", review_catalog=review)
    assert first["review"]["sha256"] != second["review"]["sha256"]
    assert first["dataset_revision"] != second["dataset_revision"]
    assert first["source"] == second["source"]
    assert pages.EXPORT_SCHEMA == 3
    monkeypatch.setattr(pages, "EXPORT_SCHEMA", 2)
    previous_semantics = pages.build(paths, tmp_path / "previous", review_catalog=review)
    assert previous_semantics["dataset_revision"] != second["dataset_revision"]


@pytest.mark.parametrize("duplicate", ["entry_id", "correction_target", "source_record"])
def test_ambiguous_reviews_fail_closed(tmp_path: Path, duplicate: str) -> None:
    paths = write_sources(tmp_path / "input")
    review = synthetic_review()
    if duplicate == "entry_id":
        review["notes"][0]["id"] = review["corrections"][0]["id"]
    elif duplicate == "correction_target":
        review["corrections"].append({**review["corrections"][0], "id": "another-correction"})
    else:
        row = pages.csv_rows(paths["runways.csv"])[0][1]
        replace_csv(paths["runways.csv"], [row, {**row, "length_ft": "2000"}])
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="duplicate review|review record ids are ambiguous"):
        pages.build(paths, output, review_catalog=review)
    assert not output.exists()


def test_cli_supplies_checked_in_review_catalog_without_loading_it_for_synthetic_builds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(tmp_path / "input")
    calls = []
    monkeypatch.setattr(pages, "acquire_inputs", lambda cache: (paths, []))
    monkeypatch.setattr(pages, "load_reference_sources", lambda catalog: [])
    monkeypatch.setattr(pages, "build", lambda *args: calls.append(args) or {"counts": {}})
    monkeypatch.setattr("sys.argv", ["build_pages_data.py", "--output", str(tmp_path / "out")])
    pages.main()
    assert calls[0][-1] == pages.REVIEW_CATALOG
