from __future__ import annotations

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
    assert manifest["counts"] == {"airports": 1, "runways": 2, "navaids": 1, "communications": 1}
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
