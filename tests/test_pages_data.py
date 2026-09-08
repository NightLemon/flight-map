from __future__ import annotations

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
    revision = pages.REVISION
    assert manifest["counts"] == {"airports": 1, "runways": 2, "navaids": 1, "communications": 1}
    assert manifest["source_counts"] == {
        "airports": 3,
        "runways": 2,
        "navaids": 2,
        "communications": 1,
    }
    assert (
        json.loads((first / "manifest.json").read_text())["inputs"][0]["sha256"]
        == hashlib.sha256(paths["LICENSE"].read_bytes()).hexdigest()
    )
    assert (first / revision / "LICENSE").read_text() == paths["LICENSE"].read_text()
    assert json.loads((first / revision / "search.json").read_text()) == [
        {
            "coordinates": [-73.0, 40.0],
            "country": "US",
            "iata_code": "OPN",
            "icao_id": "KICAO",
            "id": "ourairports:airport:1",
            "identifier": "OPEN",
            "municipality": "Town",
            "name": "Open",
        }
    ]
    bucket = json.loads((first / revision / "airports" / "1.json").read_text())[
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
    pages.build(write_sources(tmp_path / "input"), output)
    tiles = output / pages.REVISION / "tiles" / "runways"
    west = json.loads((tiles / "71-20.json").read_text())["features"]
    east = json.loads((tiles / "0-20.json").read_text())["features"]
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
    assert not any("runway:8" in file.read_text() for file in tiles.rglob("*.json"))


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
