"""Synthetic structural fixtures; they do not establish real FAA program support."""

from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
from flightmap_ingestion.cifp import (
    iter_cifp_frames,
    parse_cifp,
    parse_cifp_validity,
    parse_coordinate,
)

README = """FAA/Aeronautical Information Services CIFP Readme
Volume: 2609
Effective: 0901Z
03 September 2026
To: 0901Z
01 October 2026
"""


def synthetic(family="PA", identifier="SYN1", scope="SYN1", continuation="0"):
    """Build invented records from the field table, not by calling production code."""
    raw = list(" " * 132)

    def put(start, stop, value):
        assert len(value) <= stop - start
        raw[start:stop] = value.ljust(stop - start)

    put(0, 4, "SUSA")
    if family.startswith("P"):
        put(4, 5, family[0])
        put(12, 13, family[1])
    else:
        put(4, 6, family)
    put(6, 10, scope)
    put(10, 12, "K2")
    if family in {"PD", "PE", "PF", "ER"}:
        put(13, 18 if family == "ER" else 19, identifier)
        put(19, 20, "H" if family == "PF" else "1")
        put(20, 25, "TRANS")
        put(25 if family == "ER" else 26, 29, "010")
        put(29, 34, "ALPHA")
        put(34, 36, "K2")
        put(36, 38, "EA")
        put(38, 39, continuation)
        if continuation in {"0", "1"}:
            put(47, 49, "IF")
            put(82, 83, "+")
            put(84, 89, "05000")
            put(118, 119, "F" if family == "PF" else " ")
        else:
            put(39, 40, "E")
    else:
        if family == "PA":
            put(6, 10, identifier)
            put(13, 16, "ZZ1")
            put(93, 123, "SYNTHETIC AIRPORT")
        else:
            put(13, 17 if family in {"D ", "DB"} else 18, identifier)
            put(19, 21, "K2")
        put(21, 22, continuation)
        if continuation in {"0", "1"}:
            put(32, 41, "N37451234")
            put(41, 51, "W122301234")
        else:
            put(22, 23, "A")
    put(123, 128, "A1  Z")
    put(128, 132, "2501")
    return "".join(raw)


def parse_rows(tmp_path, rows):
    path = tmp_path / "synthetic-cifp.txt"
    path.write_bytes(("\r\n".join(rows) + "\r\n").encode("ascii"))
    return parse_cifp(path, "a" * 64)


@pytest.mark.parametrize(
    "value,axis,expected",
    [("N37451234", "latitude", 37 + 45 / 60 + 12.34 / 3600),
     ("W122301234", "longitude", -(122 + 30 / 60 + 12.34 / 3600)),
     ("S90000000", "latitude", -90), ("E180000000", "longitude", 180),
     ("S00000000", "latitude", 0)],
)
def test_coordinate_golden_values(value, axis, expected):
    assert parse_coordinate(value, axis) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "value,axis",
    [("N90600000", "latitude"), ("E180000001", "longitude"),
     ("N00600000", "latitude"), ("N00006000", "latitude"),
     ("N12.34567", "latitude"), ("N１２３４５６７８", "latitude"),
     ("E37451234", "latitude"), (" N37451234", "latitude"),
     ("N37451234", "x")],
)
def test_coordinates_fail_without_coercion(value, axis):
    with pytest.raises(ValueError):
        parse_coordinate(value, axis)


def test_readme_product_interval_keeps_exact_official_time():
    result = parse_cifp_validity(README)
    assert result["airac"] == "2609"
    assert result["valid_from"] == datetime(2026, 9, 3, 9, 1, tzinfo=UTC)
    assert result["valid_to"] == datetime(2026, 10, 1, 9, 1, tzinfo=UTC)
    assert result["evidence"]


def test_readme_has_no_0901_or_calendar_fallback():
    result = parse_cifp_validity(README.replace("0901Z", "1230Z"))
    assert result["valid_from"].hour == 12
    with pytest.raises(ValueError):
        parse_cifp_validity(README.replace("0901Z", ""))
    with pytest.raises(ValueError):
        parse_cifp_validity(README + README.replace("2609", "2610"))


def test_frame_reader_preserves_spaces_nonnumeric_numbers_and_line_positions():
    first = synthetic()
    second = first[:123] + " " * 9
    frames = list(iter_cifp_frames(BytesIO((first + "\r\n" + second + "\n").encode())))
    assert [frame.line_number for frame in frames] == [1, 2]
    assert frames[1].raw.endswith(" " * 9)
    assert all(frame.error is None for frame in frames)


def test_bad_frame_is_retained_and_does_not_shift_later_positions():
    frames = list(iter_cifp_frames(BytesIO(b"bad\n" + synthetic().encode() + b"\n")))
    assert frames[0].raw == "bad"
    assert frames[0].error
    assert frames[1].line_number == 2
    assert frames[1].family == "PA"


def test_airport_fields_are_candidates_and_cannot_publish(tmp_path):
    result = parse_rows(tmp_path, [synthetic()])
    airport = result.records[0]
    assert airport.kind == "airport"
    assert airport.identifier == "SYN1"
    assert airport.name == "SYNTHETIC AIRPORT"
    assert airport.properties["faa_identifier"] == "ZZ1"
    assert airport.properties["file_record_number"] == "A1  Z"
    assert airport.properties["coordinate_candidate"]["latitude"] == pytest.approx(
        37 + 45 / 60 + 12.34 / 3600
    )
    assert airport.geometry is None
    assert airport.provenance.line == 1
    assert result.report.blocking
    assert result.report.capabilities == []
    assert result.report.input_count == result.report.unsupported_count == 1
    assert result.report.success_count == 0
    assert result.report.issues[0]["code"] == "cifp-evidence-incomplete"


@pytest.mark.parametrize("family,identifier,kind", [
    ("PG", "RW01", "runway"), ("EA", "ALPHA", "waypoint"),
    ("PC", "ALPHA", "waypoint"), ("D ", "ZZZ", "navaid"), ("DB", "YYY", "navaid"),
])
def test_primary_record_families_preserve_raw_coordinate_candidates(
    tmp_path, family, identifier, kind
):
    raw = synthetic(family, identifier)
    result = parse_rows(tmp_path, [raw])
    record = result.records[0]
    assert record.kind == kind
    assert record.properties["raw"] == raw
    assert record.geometry is None
    assert result.report.error_count == 0
    assert result.report.blocking


def test_same_named_waypoints_in_different_scopes_remain_distinct(tmp_path):
    result = parse_rows(tmp_path, [synthetic("EA", "ALPHA", "ENRT"),
                                   synthetic("PC", "ALPHA", "SYN1"),
                                   synthetic("PC", "ALPHA", "SYN2")])
    assert len({record.id for record in result.records}) == 3
    assert result.report.error_count == 0


@pytest.mark.parametrize("family,category", [("PD", "SID"), ("PE", "STAR"), ("PF", "APPROACH")])
def test_program_prefixes_preserve_raw_legs_without_guessing_branches(tmp_path, family, category):
    result = parse_rows(tmp_path, [synthetic(family, "SYNTH1")])
    program, record = result.records
    assert program.kind == "procedure"
    assert program.properties["procedure_type"] == category
    assert record.parent_id == program.id
    assert record.properties["path_terminator"] == "IF"
    assert record.properties["altitude_1"] == "05000"
    assert record.properties["fix_resolution"] == "unverified"
    assert record.branch_id is None
    assert record.geometry is None
    if family == "PF":
        assert record.properties["route_type"] == "H"
        assert record.properties["route_qualifier_1"] == "F"


def test_continuation_payload_is_never_a_primary_leg(tmp_path):
    result = parse_rows(tmp_path, [synthetic("PF", "SYNTH1", continuation="2")])
    record = result.records[-1]
    assert record.properties["is_continuation"] is True
    assert record.properties["application_type"] == "E"
    assert "path_terminator" not in record.properties
    assert "coordinate_candidate" not in record.properties
    assert record.branch_id is None


def test_airway_fields_do_not_imply_adjacency(tmp_path):
    result = parse_rows(tmp_path, [synthetic("ER", "V1")])
    record = result.records[0]
    assert record.kind == "airway"
    assert record.identifier == "V1"
    assert record.sequence == 10
    assert record.properties["fix_identifier"] == "ALPHA"
    assert record.properties["fix_section"] == "EA"
    assert record.geometry is None


def test_duplicate_and_bad_rows_are_all_accounted_for(tmp_path):
    result = parse_rows(tmp_path, [synthetic(), synthetic(), "bad", synthetic("PN", "ABCD")])
    assert result.report.input_count == 4
    assert result.report.unsupported_count == 2
    assert result.report.error_count == 2
    assert len(result.records) == 2
    assert result.records[0].id != result.records[1].id
    unknown = next(
        issue for issue in result.report.issues if issue["code"] == "cifp-unsupported-family"
    )
    assert unknown["context"]["line"] == 4
    assert unknown["context"]["raw"] == synthetic("PN", "ABCD")


def test_bad_primary_field_keeps_original_record_in_report(tmp_path):
    raw = synthetic()
    raw = raw[:32] + "N90600000" + raw[41:]
    result = parse_rows(tmp_path, [raw])
    assert result.report.error_count == 1
    assert not result.records
    assert result.report.issues[-1]["context"]["raw"] == raw


def test_zip_selection_preserves_member_without_extracting_files(tmp_path):
    path = tmp_path / "synthetic.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("folder/FAACIFP18", synthetic() + "\n")
        archive.writestr("notes.txt", "This archive is a synthetic test fixture")
    result = parse_cifp(path, "a" * 64)
    assert result.records[0].provenance.member == "folder/FAACIFP18"
    assert not (tmp_path / "folder").exists()
    with pytest.raises(ValueError, match="exactly one"):
        parse_cifp(path, "a" * 64, member="missing")


def test_empty_input_and_invalid_asset_identity_cannot_be_silent_success(tmp_path):
    path = tmp_path / "empty"
    path.write_bytes(b"")
    result = parse_cifp(path, "a" * 64)
    assert result.report.blocking
    assert result.report.input_count == 0
    assert result.report.issues[-1]["code"] == "cifp-empty-file"
    with pytest.raises(ValueError):
        parse_cifp(path, "bad")
