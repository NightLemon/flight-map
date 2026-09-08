import csv
import io
import zipfile
from copy import deepcopy
from datetime import date

import pytest
from flightmap_ingestion.nasr_layers import CAPABILITIES, TABLES, parse_nasr_layers

DATE = date(2026, 9, 3)
SHA = "a" * 64


def _row(**fields):
    return {"EFF_DATE": "2026/09/03", **fields}


def _end(name, lat, lon):
    return _row(
        SITE_NO="100.",
        SITE_TYPE_CODE="A",
        ARPT_ID="TST",
        RWY_ID="04/22",
        RWY_END_ID=name,
        LAT_DECIMAL=lat,
        LONG_DECIMAL=lon,
        LAT_DISPLACED_THR_DECIMAL="40.1",
        LONG_DISPLACED_THR_DECIMAL="-74.1",
        DISPLACED_THR_LEN="460",
    )


def _segment(seq, start, end, **extra):
    return _row(
        REGULATORY="Y",
        AWY_LOCATION="C",
        AWY_ID="J70",
        POINT_SEQ=str(seq),
        FROM_POINT=start,
        TO_POINT=end,
        AWY_SEG_GAP_FLAG="N",
        DOGLEG="N",
        **extra,
    )


def _point(seq, lat="40-30-00.000N", lon="074-00-00.00W", scope=" ", route="J70"):
    line = list(" " * 315)
    for offset, width, value in [
        (0, 4, "AWY2"),
        (4, 5, route),
        (9, 1, scope),
        (10, 5, str(seq)),
        (83, 14, lat),
        (97, 14, lon),
    ]:
        line[offset : offset + width] = value.ljust(width)
    return "".join(line)


def _frequency(value="118.00", sector="NORTH", **extra):
    fields = dict(
        SERVICED_FACILITY="TST",
        SERVICED_SITE_TYPE="AIRPORT",
        SERVICED_STATE="NY",
        SERVICED_COUNTRY="US",
        FREQ=value,
        FREQ_USE="LCL/P",
        SECTORIZATION=sector,
        REMARK="Original remarks",
    )
    fields.update(extra)
    return _row(**fields)


@pytest.fixture
def source():
    return {
        "APT_BASE.csv": [
            _row(
                SITE_NO="100.",
                SITE_TYPE_CODE="A",
                ARPT_ID="TST",
                ARPT_NAME="Test airport",
                ICAO_ID="KTST",
                COUNTRY_CODE="US",
                STATE_CODE="NY",
                LAT_DECIMAL="40",
                LONG_DECIMAL="-74",
            )
        ],
        "APT_RWY.csv": [
            _row(
                SITE_NO="100.",
                SITE_TYPE_CODE="A",
                ARPT_ID="TST",
                RWY_ID="04/22",
                RWY_LEN="12000",
                RWY_WIDTH="200",
                SURFACE_TYPE_CODE="CONC",
            )
        ],
        "APT_RWY_END.csv": [_end("04", "40", "-74"), _end("22", "40.02", "-73.98")],
        "NAV_BASE.csv": [
            _row(
                NAV_ID="AAA",
                NAV_TYPE="VOR/DME",
                CITY="CITY ONE",
                NAME="Alpha",
                LAT_DECIMAL="40.8",
                LONG_DECIMAL="-75.3",
            )
        ],
        "FIX_BASE.csv": [
            _row(FIX_ID="ALPHA", ICAO_REGION_CODE="K6", LAT_DECIMAL="-40.2", LONG_DECIMAL="75.3")
        ],
        "AWY_BASE.csv": [
            _row(REGULATORY="Y", AWY_LOCATION="C", AWY_ID="J70", AIRWAY_STRING="AAA BBB CCC")
        ],
        "AWY_SEG_ALT.csv": [
            _segment(10, "AAA", "BBB"),
            _segment(20, "BBB", "CCC"),
            _segment(30, "CCC", ""),
        ],
        "FRQ.csv": [_frequency()],
        "AWY.txt": [
            _point(10),
            _point(20, "40-36-00.000N", "073-54-00.00W"),
            _point(30, "40-42-00.000N", "073-48-00.00W"),
        ],
    }


def _bundle(tmp_path, source, *, omit=None, drop_column=None):
    assets = {}
    for product, members in TABLES.items():
        path = tmp_path / f"{product}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for member, required in members.items():
                if member == omit:
                    continue
                rows = source[member]
                columns = sorted(required | {key for row in rows for key in row})
                if drop_column and member == drop_column[0]:
                    columns.remove(drop_column[1])
                stream = io.StringIO(newline="")
                writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
                archive.writestr(f"nested/{member}", stream.getvalue())
        assets[product] = path, SHA
    path = tmp_path / "AWY_POINTS.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AWY.txt", "\r\n".join(source["AWY.txt"]) + "\r\n")
    assets["AWY_POINTS"] = path, "b" * 64
    return assets


def _kind(result, kind):
    return [r for r in result.records if r.kind == kind]


def _check_balance(result):
    r = result.report
    assert r.input_count == r.success_count + r.unsupported_count + r.error_count
    assert r.success_count == len(result.records)
    assert len({record.id for record in result.records}) == len(result.records)


def test_six_layers_geometry_units_identity_and_provenance(tmp_path, source):
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not result.report.blocking
    assert result.report.capabilities == CAPABILITIES
    assert result.report.input_count == 8
    assert result.report.success_count == 7
    assert result.report.unsupported_count == 1  # terminal airway point
    airport = _kind(result, "airport")[0]
    runway = _kind(result, "runway")[0]
    communication = _kind(result, "communication")[0]
    assert airport.id == "faa-aeronav:nasr:airport:100.:A"
    assert runway.airport_id == communication.airport_id == airport.id
    assert communication.geometry is None
    assert runway.geometry["coordinates"] == [[-74, 40], [-73.98, 40.02]]
    assert runway.properties["displaced_thresholds"][0]["coordinates"] == [-74.1, 40.1]
    assert runway.properties["length_ft"] == 12000
    assert runway.properties["width_ft"] == 200
    assert runway.properties["dimension_unit"] == "ft"
    assert len(runway.properties["supporting_provenance"]) == 2
    assert communication.properties["frequency"] == "118.00"
    assert communication.properties["service"] == "LCL/P"
    assert communication.properties["sectorization"] == "NORTH"
    assert communication.properties["remarks"] == "Original remarks"
    assert communication.properties["unit"] == "MHz"
    navaid = _kind(result, "navaid")[0]
    waypoint = _kind(result, "waypoint")[0]
    assert navaid.geometry["coordinates"] == [-75.3, 40.8]
    assert waypoint.geometry["coordinates"] == [75.3, -40.2]
    assert "datum" not in navaid.properties and "datum" not in waypoint.properties
    airway = _kind(result, "airway")[0]
    assert airway.geometry["coordinates"] == [[-74, 40.5], [-73.9, 40.6]]
    assert airway.provenance.member == "nested/AWY_SEG_ALT.csv"
    supports = airway.properties["supporting_provenance"]
    assert [p["member"] for p in supports] == ["AWY.txt", "AWY.txt", "nested/AWY_SEG_ALT.csv"]
    assert supports[0]["asset_sha256"] == "b" * 64
    assert [p["line"] for p in supports] == [1, 2, 3]
    for record in result.records:
        assert record.properties["raw_fields"]
        assert record.provenance.line >= 2
    _check_balance(result)


@pytest.mark.parametrize("change", ["missing", "one_coordinate", "helipad", "wrong_end", "nan"])
def test_runway_never_substitutes_displaced_threshold_or_airport(tmp_path, source, change):
    if change == "missing":
        source["APT_RWY_END.csv"].pop()
    elif change == "one_coordinate":
        source["APT_RWY_END.csv"][1]["LAT_DECIMAL"] = ""
    elif change == "nan":
        source["APT_RWY_END.csv"][1]["LAT_DECIMAL"] = "nan"
    elif change == "wrong_end":
        source["APT_RWY_END.csv"][1]["RWY_END_ID"] = "23"
    else:
        source["APT_RWY.csv"][0]["RWY_ID"] = "H1"
        source["APT_RWY_END.csv"] = [_end("H1", "40", "-74")]
        source["APT_RWY_END.csv"][0]["RWY_ID"] = "H1"
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not _kind(result, "runway")
    assert not result.report.blocking
    assert result.report.unsupported_count == 2
    _check_balance(result)


@pytest.mark.parametrize(
    "table",
    list(TABLES["APT"])
    + ["NAV_BASE.csv", "FIX_BASE.csv", "AWY_BASE.csv", "AWY_SEG_ALT.csv", "FRQ.csv"],
)
def test_every_required_csv_date_is_checked(tmp_path, source, table):
    source[table][0]["EFF_DATE"] = "2026/10/01"
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert result.report.blocking
    assert any(
        "EFF_DATE" in example["reason"]
        for issue in result.report.issues
        for example in issue.get("context", {}).get("examples", [])
    )
    _check_balance(result)


def test_ancillary_csv_date_is_checked(tmp_path, source):
    assets = _bundle(tmp_path, source)
    with zipfile.ZipFile(assets["NAV"][0], "a") as archive:
        archive.writestr("NAV_RMK.csv", "EFF_DATE,NAV_ID,REMARK\n2026/10/01,AAA,bad edition\n")
    result = parse_nasr_layers(assets, DATE)
    assert result.report.blocking
    assert result.report.error_count == 1
    assert result.report.input_count == 9
    _check_balance(result)


@pytest.mark.parametrize(
    "argument", [dict(omit="APT_RWY_END.csv"), dict(drop_column=("FRQ.csv", "FREQ"))]
)
def test_missing_member_or_required_column_blocks(tmp_path, source, argument):
    result = parse_nasr_layers(_bundle(tmp_path, source, **argument), DATE)
    assert result.report.blocking
    _check_balance(result)


@pytest.mark.parametrize(
    "table",
    [
        "APT_BASE.csv",
        "APT_RWY.csv",
        "APT_RWY_END.csv",
        "NAV_BASE.csv",
        "FIX_BASE.csv",
        "AWY_BASE.csv",
        "AWY_SEG_ALT.csv",
        "AWY.txt",
    ],
)
def test_duplicate_key_blocks_including_supporting_rows(tmp_path, source, table):
    source[table].append(deepcopy(source[table][0]))
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert result.report.blocking
    _check_balance(result)


def test_navigation_keys_keep_city_and_region_distinct(tmp_path, source):
    source["NAV_BASE.csv"].append({**source["NAV_BASE.csv"][0], "CITY": "CITY TWO"})
    source["FIX_BASE.csv"].append({**source["FIX_BASE.csv"][0], "ICAO_REGION_CODE": "K7"})
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not result.report.blocking
    assert len(_kind(result, "navaid")) == len(_kind(result, "waypoint")) == 2
    _check_balance(result)


@pytest.mark.parametrize("change", ["coordinate", "point", "mismatch", "gap", "dogleg", "bad_date"])
def test_airway_never_bridges_missing_or_invalid_intermediate_point(tmp_path, source, change):
    if change == "coordinate":
        source["AWY.txt"][1] = _point(20, "", "")
    elif change == "point":
        source["AWY.txt"].pop(1)
    elif change == "mismatch":
        source["AWY_SEG_ALT.csv"][0]["TO_POINT"] = "CCC"
    elif change == "gap":
        source["AWY_SEG_ALT.csv"][0]["AWY_SEG_GAP_FLAG"] = "Y"
    elif change == "dogleg":
        source["AWY_SEG_ALT.csv"][0]["DOGLEG"] = "Y"
    else:
        source["AWY_SEG_ALT.csv"][1]["EFF_DATE"] = "2026/10/01"
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    airways = _kind(result, "airway")
    assert all(r.sequence != 10 for r in airways)
    if change in {"coordinate", "point", "bad_date"}:
        assert not airways
    assert result.report.blocking == (change == "bad_date")
    _check_balance(result)


def test_airway_scope_and_nonregulatory_rows_are_not_invented(tmp_path, source):
    source["AWY_BASE.csv"].append({**source["AWY_BASE.csv"][0], "REGULATORY": "N"})
    source["AWY_SEG_ALT.csv"].extend([{**r, "REGULATORY": "N"} for r in source["AWY_SEG_ALT.csv"]])
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert len(_kind(result, "airway")) == 2
    assert result.report.unsupported_count == 4
    assert not result.report.blocking
    _check_balance(result)


def test_frequency_formats_sectors_and_duplicate_rows_are_preserved(tmp_path, source):
    source["FRQ.csv"] = [
        _frequency("122.1R"),
        _frequency("118.00", "NORTH"),
        _frequency("118.00", "SOUTH"),
        _frequency("118.00", "NORTH"),
        _frequency("348.600", FREQ_USE="GND/S"),
        _frequency("8903X"),
        _frequency("115.4/106X"),
        _frequency("8903"),
        _frequency("nan"),
        _frequency(""),
        _frequency("123.45", FREQ_USE="ODD USAGE/P"),
    ]
    assets = _bundle(tmp_path, source)
    first = parse_nasr_layers(assets, DATE)
    second = parse_nasr_layers(assets, DATE)
    rows = _kind(first, "communication")
    assert len(rows) == 6
    assert rows[0].properties["frequency"] == "122.1"
    assert rows[0].properties["receive_only"]
    assert rows[4].properties["frequency"] == "348.600"
    assert rows[4].properties["service"] == "GND/S"
    assert rows[5].properties["service"] == "ODD USAGE/P"
    assert not rows[5].properties["common_use"]
    assert [r.id for r in rows] == [r.id for r in _kind(second, "communication")]
    assert not first.report.blocking
    _check_balance(first)


@pytest.mark.parametrize("usage", [None, "", "  \t  "])
def test_missing_frequency_usage_is_unsupported_with_original_provenance(tmp_path, source, usage):
    source["FRQ.csv"] = [_frequency(FREQ_USE=usage), _frequency(FREQ_USE="LCL/P")]
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    communications = _kind(result, "communication")
    assert len(communications) == 1
    assert communications[0].properties["service"] == "LCL/P"
    assert communications[0].provenance.line == 3
    assert result.report.unsupported_count == 2  # Empty usage plus terminal airway point.
    assert result.report.error_count == 0
    assert not result.report.blocking
    issue = next(i for i in result.report.issues if i["code"] == "nasr-frequency-missing-use")
    assert issue["context"]["count"] == 1
    example = issue["context"]["examples"][0]
    assert example["identity"]["FREQ_USE"] == (usage or "")
    assert example["provenance"]["asset_sha256"] == SHA
    assert example["provenance"]["member"] == "nested/FRQ.csv"
    assert example["provenance"]["line"] == 2
    _check_balance(result)


@pytest.mark.parametrize("change", ["ambiguous", "state", "country", "type"])
def test_communications_require_unique_evidenced_airport_association(tmp_path, source, change):
    if change == "ambiguous":
        source["APT_BASE.csv"].append({**source["APT_BASE.csv"][0], "SITE_NO": "200."})
    else:
        field, value = {
            "state": ("SERVICED_STATE", "NJ"),
            "country": ("SERVICED_COUNTRY", "CA"),
            "type": ("SERVICED_SITE_TYPE", "NAVAID"),
        }[change]
        source["FRQ.csv"][0][field] = value
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not _kind(result, "communication")
    assert not result.report.blocking
    _check_balance(result)


def test_diagnostics_are_bounded_for_large_unsupported_groups(tmp_path, source):
    source["FRQ.csv"] = [_frequency("8903X") for _ in range(1000)]
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    issue = next(i for i in result.report.issues if i["code"] == "nasr-frequency-format")
    assert issue["context"]["count"] == 1000
    assert len(issue["context"]["examples"]) == 3
    assert len(result.report.model_dump_json()) < 8000
    _check_balance(result)


def test_zero_size_special_runway_is_unsupported_not_a_dataset_error(tmp_path, source):
    source["APT_RWY.csv"][0]["RWY_LEN"] = "0"
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not result.report.blocking
    assert not _kind(result, "runway")
    assert result.report.unsupported_count == 2
    _check_balance(result)


def test_airway_csv_missing_row_cannot_skip_known_fixed_point(tmp_path, source):
    source["AWY_SEG_ALT.csv"].pop(1)
    source["AWY_SEG_ALT.csv"][0]["TO_POINT"] = "CCC"
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not _kind(result, "airway")
    assert not result.report.blocking
    _check_balance(result)


@pytest.mark.parametrize("sequence", ["020", "not-a-number"])
def test_airway_sequence_ambiguity_blocks_and_does_not_bridge(tmp_path, source, sequence):
    source["AWY_SEG_ALT.csv"].append({**source["AWY_SEG_ALT.csv"][1], "POINT_SEQ": sequence})
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert result.report.blocking
    assert not _kind(result, "airway")
    _check_balance(result)


@pytest.mark.parametrize(
    "table,field,value",
    [
        ("NAV_BASE.csv", "LAT_DECIMAL", "nan"),
        ("FIX_BASE.csv", "LONG_DECIMAL", "181"),
        ("APT_RWY.csv", "RWY_WIDTH", "inf"),
        ("FRQ.csv", "SERVICED_FACILITY", ""),
    ],
)
def test_invalid_values_cannot_emit_features(tmp_path, source, table, field, value):
    source[table][0][field] = value
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert result.report.blocking
    _check_balance(result)


@pytest.mark.parametrize("scope", ["A", "H"])
def test_airway_fixed_scope_and_dms_hemispheres(tmp_path, source, scope):
    for table in ["AWY_BASE.csv", "AWY_SEG_ALT.csv"]:
        for row in source[table]:
            row["AWY_LOCATION"] = scope
    source["AWY.txt"] = [
        _point(seq, "40-30-00.000S", "074-00-00.00E", scope=scope) for seq in [10, 20, 30]
    ]
    result = parse_nasr_layers(_bundle(tmp_path, source), DATE)
    assert not result.report.blocking
    assert len(_kind(result, "airway")) == 2
    assert _kind(result, "airway")[0].geometry["coordinates"][0] == [74, -40.5]
    _check_balance(result)
