import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flightmap_ingestion.acquisition import EvidenceRequired, build_local, update_product
from flightmap_ingestion.cli import app
from flightmap_ingestion.download import VerifiedDownload
from flightmap_ingestion.dtpp import dtpp_validity
from flightmap_ingestion.faa import DiscoveryCandidate
from flightmap_schema import ImportManifest, load_sources
from flightmap_storage import Repository
from typer.testing import CliRunner

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://aeronav.faa.gov/d-tpp/2609/xml_data/d-tpp_Metafile.xml"


def product(identifier):
    return next(
        p for s in load_sources("sources/us/faa.yml") for p in s.products if p.id == identifier
    )


def manifest():
    return ImportManifest(
        product_id="dtpp", source_url=URL, **dtpp_validity(FIXTURES / "dtpp_synthetic.xml")
    )


def test_local_build_stages_and_repeated_import_is_unchanged(tmp_path):
    repository = Repository(tmp_path)
    first = build_local(repository, product("dtpp"), FIXTURES / "dtpp_synthetic.xml", manifest())
    second = build_local(repository, product("dtpp"), FIXTURES / "dtpp_synthetic.xml", manifest())
    assert first["status"] == "staged"
    assert second["status"] == "unchanged"
    assert first["release_id"] == second["release_id"]
    run = json.loads(Path(first["run_file"]).read_text())
    assert run["stage"] == "stage"
    assert set(run["completed"]) == {
        "discover",
        "acquire",
        "verify",
        "parse",
        "normalize",
        "validate",
        "stage",
    }
    repository.promote(first["release_id"], product("dtpp"), at=datetime(2026, 9, 7, tzinfo=UTC))
    repository.revoke(first["release_id"], "test correction")
    assert repository.report(first["release_id"])


def test_manifest_conflict_is_rejected_before_build(tmp_path):
    wrong = manifest().model_copy(update={"valid_to": datetime(2026, 10, 2, 9, 1, tzinfo=UTC)})
    with pytest.raises(ValueError, match="conflicts"):
        build_local(Repository(tmp_path), product("dtpp"), FIXTURES / "dtpp_synthetic.xml", wrong)


def test_dtpp_update_uses_xml_asset_and_does_not_promote(tmp_path, monkeypatch):
    from flightmap_ingestion.acquisition import AssetDownloader, FaaDiscovery

    monkeypatch.setattr(
        FaaDiscovery,
        "fetch",
        lambda *_: [DiscoveryCandidate(URL, "Catalog", None, "asset", "chart-catalog")],
    )
    monkeypatch.setattr(
        AssetDownloader,
        "acquire",
        lambda *_args, **_kwargs: VerifiedDownload(
            FIXTURES / "dtpp_synthetic.xml", "a" * 64, 100, "application/xml", URL
        ),
    )
    result = update_product(
        Repository(tmp_path), product("dtpp"), at=datetime(2026, 9, 7, tzinfo=UTC)
    )
    assert result["status"] == "staged"
    assert result["report"]["input_count"] == 5
    assert result["promotion"] == "not-requested"


def test_cifp_does_not_follow_agreement_or_fetch(tmp_path, monkeypatch):
    from flightmap_ingestion.acquisition import FaaDiscovery

    monkeypatch.setattr(
        FaaDiscovery, "fetch", lambda *_: pytest.fail("Agreement must not be followed")
    )
    with pytest.raises(EvidenceRequired):
        update_product(Repository(tmp_path), product("cifp"))


def test_discovery_network_failure_is_saved_and_exit_nonzero(tmp_path, monkeypatch):
    from flightmap_ingestion.cli import FaaDiscovery

    def fail(*_):
        raise RuntimeError("offline fixture")

    monkeypatch.setattr(FaaDiscovery, "fetch", fail)
    output = tmp_path / "discovery.json"
    result = CliRunner().invoke(app, ["discover-faa", "--product", "dtpp", "--output", str(output)])
    assert result.exit_code == 1
    assert json.loads(output.read_text())[0]["status"] == "failed"


def test_cifp_update_explains_required_action_and_preserves_current(tmp_path):
    result = CliRunner().invoke(app, ["update", "--product", "cifp", "--data-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "needs-user-action"


def test_nasr_without_time_evidence_retains_download_and_balanced_report(tmp_path, monkeypatch):
    from flightmap_ingestion.acquisition import AssetDownloader, FaaDiscovery

    url = "https://nfdc.faa.gov/extra/03_Sep_2026_APT_CSV.zip"
    monkeypatch.setattr(
        FaaDiscovery,
        "fetch",
        lambda *_: [DiscoveryCandidate(url, "Airports", None, "asset", "airport-csv")],
    )
    monkeypatch.setattr(
        AssetDownloader,
        "acquire",
        lambda *_args, **_kwargs: VerifiedDownload(
            FIXTURES / "nasr_synthetic.csv", "a" * 64, 100, "text/csv", url
        ),
    )
    with pytest.raises(EvidenceRequired, match="validity-evidence-missing"):
        update_product(Repository(tmp_path), product("nasr"), at=datetime(2026, 9, 7, tzinfo=UTC))
    reports = list(tmp_path.glob("nasr-*.report.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text())["input_count"] == 2
    assert len(list((tmp_path / "assets").iterdir())) == 1
