import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flightmap_ingestion.cli import app
from flightmap_ingestion.research_acquisition import build_research_from_asset
from flightmap_schema import load_sources
from flightmap_storage import Repository
from typer.testing import CliRunner

FIXTURE = Path(__file__).parent / "fixtures/nasr_synthetic.csv"
NOW = datetime(2026, 9, 8, tzinfo=UTC)
URL = "https://nfdc.faa.gov/webContent/28DaySub/extra/03_Sep_2026_APT_CSV.zip"


def nasr_product():
    return next(p for s in load_sources("sources/us/faa.yml") for p in s.products if p.id == "nasr")


def airport_zip(directory, *, text=None):
    path = directory / "nasr-synthetic.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            zipfile.ZipInfo("CSV_Data/APT_BASE.csv", (2026, 9, 3, 0, 0, 0)),
            text if text is not None else FIXTURE.read_text(encoding="utf-8"),
        )
    return path


def acquired(repository, path, **changes):
    return repository.store_asset(
        path,
        source_id=changes.get("source_id", "faa-aeronav"),
        product_id=changes.get("product_id", "nasr"),
        source_url=changes.get("source_url", URL),
        retrieved_at=NOW,
        content_type="application/zip",
    )


def acquisition_count(repository):
    with sqlite3.connect(repository.db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM acquisitions").fetchone()[0]


def test_cached_build_is_immutable_and_never_downloads_or_reacquires(tmp_path, monkeypatch):
    from flightmap_ingestion.download import AssetDownloader
    from flightmap_ingestion.faa import FaaDiscovery

    repository = Repository(tmp_path / "data")
    asset = acquired(repository, airport_zip(tmp_path))
    monkeypatch.setattr(
        FaaDiscovery, "fetch", lambda *_: pytest.fail("Cached build discovered links")
    )
    monkeypatch.setattr(
        AssetDownloader, "acquire", lambda *_a, **_k: pytest.fail("Cached build downloaded data")
    )
    first = build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)
    second = build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)
    assert first["status"] == "staged"
    assert second["status"] == "unchanged"
    assert first["snapshot_id"] == second["snapshot_id"]
    assert acquisition_count(repository) == 1
    assert repository.snapshot()["pointers"] == {}
    assert repository.list_releases() == []
    snapshot = repository.get_snapshot(first["snapshot_id"])
    assert snapshot.official_effective_date.isoformat() == "2026-09-03"
    assert snapshot.exact_validity_status == "unknown"
    assert snapshot.update_interval_days == 28
    assert "AIRAC CYCLE PERIOD: 28 DAY CLARIFICATION" in snapshot.update_interval_evidence[1]
    assert (
        snapshot.date_evidence[0] == f"sha256:{asset.sha256}!CSV_Data/APT_BASE.csv#column=EFF_DATE"
    )
    records = repository.list_snapshot_records(first["snapshot_id"])
    assert len(records) == first["report"]["input_count"] == first["report"]["success_count"] == 2
    assert records[0].properties["icao_id"] is None
    assert records[0].provenance.member == "CSV_Data/APT_BASE.csv"
    run = json.loads(Path(first["run_file"]).read_text())
    assert run["stage"] == "stage"
    assert set(run["completed"]) == {"reuse", "verify", "parse", "validate", "stage"}


@pytest.mark.parametrize("changes", [{"product_id": "dtpp"}, {"source_id": "another-source"}])
def test_cached_build_rejects_foreign_acquisition_identity(tmp_path, changes):
    repository = Repository(tmp_path / "data")
    asset = acquired(repository, airport_zip(tmp_path), **changes)
    with pytest.raises(ValueError):
        build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)
    assert repository.list_releases() == []


def test_cached_corruption_is_rejected_before_parse(tmp_path, monkeypatch):
    from flightmap_ingestion import research_acquisition

    repository = Repository(tmp_path / "data")
    asset = acquired(repository, airport_zip(tmp_path))
    Path(asset.storage_uri).write_bytes(b"corrupt ZIP")
    monkeypatch.setattr(
        research_acquisition, "parse_nasr", lambda *_: pytest.fail("Parsed corruption")
    )
    with pytest.raises((ValueError, RuntimeError)):
        build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)
    assert repository.snapshot()["pointers"] == {}


def test_parsing_error_remains_a_reported_quarantined_candidate(tmp_path):
    repository = Repository(tmp_path / "data")
    asset = acquired(
        repository,
        airport_zip(tmp_path, text=FIXTURE.read_text().replace("31.5,-85.25", "99,-85.25")),
    )
    result = build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)
    assert result["status"] == "quarantined"
    assert result["report"]["input_count"] == 2
    assert result["report"]["success_count"] == result["report"]["error_count"] == 1
    assert repository.snapshot_report(result["snapshot_id"])["report"]["error_count"] == 1
    assert len(repository.list_snapshot_records(result["snapshot_id"])) == 1
    with pytest.raises(ValueError):
        repository.activate_snapshot(result["snapshot_id"], nasr_product(), at=NOW)


def test_cached_future_requires_preview_and_clock_uses_utc_date(tmp_path):
    repository = Repository(tmp_path / "data")
    asset = acquired(repository, airport_zip(tmp_path))
    before = datetime.fromisoformat("2026-09-03T01:00:00+08:00")
    with pytest.raises(ValueError, match="preview"):
        build_research_from_asset(repository, nasr_product(), asset.sha256, at=before)
    preview = build_research_from_asset(
        repository, nasr_product(), asset.sha256, at=before, preview=True
    )
    assert preview["official_effective_date"] == "2026-09-03"
    with pytest.raises(ValueError):
        repository.activate_snapshot(preview["snapshot_id"], nasr_product(), at=before)


@pytest.mark.parametrize(
    "flags",
    [
        ["--asset-sha256", "a" * 64],
        ["--research", "--manifest", str(FIXTURE)],
    ],
)
def test_research_cli_rejects_conflicting_flags_before_opening_database(tmp_path, flags):
    directory = tmp_path / "must-not-initialize"
    result = CliRunner().invoke(
        app, ["update", "--product", "nasr", "--data-dir", str(directory), *flags]
    )
    assert result.exit_code == 2
    assert not directory.exists()


def test_cached_cli_success_uses_research_attempts_and_retains_strict_failure(tmp_path):
    repository = Repository(tmp_path / "data")
    asset = acquired(repository, airport_zip(tmp_path))
    repository.record_attempt("nasr", "needs-user-action", "Exact product time remains unknown")
    result = CliRunner().invoke(
        app,
        [
            "update",
            "--product",
            "nasr",
            "--research",
            "--asset-sha256",
            asset.sha256,
            "--data-dir",
            str(repository.data_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    response = json.loads(result.stdout)
    assert response["status"] == "staged"
    assert response["activation"] == response["promotion"] == "not-requested"
    assert acquisition_count(repository) == 1
    assert repository.snapshot()["attempts"][0]["status"] == "needs-user-action"
