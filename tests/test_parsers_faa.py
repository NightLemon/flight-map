from datetime import UTC, date, datetime
from pathlib import Path

from flightmap_ingestion.dtpp import dtpp_validity, parse_dtpp
from flightmap_ingestion.nasr import nasr_effective_date, parse_nasr

FIXTURES = Path(__file__).parent / "fixtures"
SHA = "a" * 64


def test_nasr_coordinate_identity_and_missing_icao():
    result = parse_nasr(FIXTURES / "nasr_synthetic.csv", SHA, date(2026, 9, 3))
    assert result.report.success_count == 2
    assert result.report.error_count == 0
    first, second = result.records
    assert first.geometry["coordinates"] == [-85.25, 31.5]
    assert first.properties["icao_id"] is None
    assert first.id.endswith("TEST1:A")
    assert second.properties["icao_id"] == "XTST"
    assert second.geometry["coordinates"] == [85.25, -31.5]
    assert first.provenance.line == 2
    assert nasr_effective_date(FIXTURES / "nasr_synthetic.csv") == date(2026, 9, 3)


def test_nasr_bad_coordinate_and_duplicate_identity_block(tmp_path):
    text = (FIXTURES / "nasr_synthetic.csv").read_text(encoding="utf-8-sig")
    path = tmp_path / "bad.csv"
    path.write_text(text.replace("TEST2", "TEST1"), encoding="utf-8")
    assert parse_nasr(path, SHA).report.error_count == 1
    path.write_text(text.replace("31.5,-85.25", "nan,-85.25"), encoding="utf-8")
    assert parse_nasr(path, SHA).report.error_count == 1
    assert (
        parse_nasr(FIXTURES / "nasr_synthetic.csv", SHA, date(2026, 10, 1)).report.error_count == 2
    )


def test_dtpp_uses_explicit_utc_validity_and_retains_chart_categories():
    path = FIXTURES / "dtpp_synthetic.xml"
    validity = dtpp_validity(path)
    assert validity["valid_from"] == datetime(2026, 9, 3, 9, 1, tzinfo=UTC)
    assert validity["valid_to"] == datetime(2026, 10, 1, 9, 1, tzinfo=UTC)
    result = parse_dtpp(path, SHA)
    assert result.report.success_count == 4
    assert [r.properties["category"] for r in result.records] == [
        "sid",
        "star",
        "approaches",
        "approaches",
    ]
    assert (
        result.records[0].properties["pdf_url"] == "https://aeronav.faa.gov/d-tpp/2609/TESTDP.PDF"
    )
    assert result.records[0].airport_ident == "TST"
    assert result.records[0].properties["association_status"] == "unconfirmed"
    assert result.records[-1].properties["pdf_url"] is None
    assert result.records[-1].properties["deleted"]


def test_dtpp_unknown_code_preserves_record_and_unsafe_pdf_blocks(tmp_path):
    text = (FIXTURES / "dtpp_synthetic.xml").read_text(encoding="utf-8-sig")
    path = tmp_path / "bad.xml"
    path.write_text(text.replace("<chart_code>DP</chart_code>", "<chart_code>NEW</chart_code>"))
    result = parse_dtpp(path, SHA)
    assert result.report.unsupported_count == 1
    assert len(result.records) == 4
    path.write_text(text.replace("TESTDP.PDF", "../other.pdf"))
    assert parse_dtpp(path, SHA).report.error_count == 1
