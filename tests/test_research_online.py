import hashlib
import json

import pytest
from flightmap_ingestion.acquisition import EvidenceRequired
from flightmap_ingestion.cli import app
from flightmap_ingestion.download import VerifiedDownload
from flightmap_ingestion.faa import DiscoveryCandidate
from flightmap_ingestion.research_acquisition import update_research_product
from flightmap_storage import Repository
from test_research_acquisition import (
    FIXTURE,
    NOW,
    URL,
    acquisition_count,
    airport_zip,
    nasr_product,
)
from typer.testing import CliRunner

FUTURE_URL = "https://nfdc.faa.gov/webContent/28DaySub/extra/01_Oct_2026_APT_CSV.zip"
OLDER_URL = "https://nfdc.faa.gov/webContent/28DaySub/extra/06_Aug_2026_APT_CSV.zip"


def network_fixture(monkeypatch, path, *, candidates=None):
    from flightmap_ingestion import research_acquisition

    selected = candidates or [DiscoveryCandidate(URL, "Airports", None, "asset", "airport-csv")]
    monkeypatch.setattr(research_acquisition.FaaDiscovery, "fetch", lambda *_: selected)
    requests = []

    def acquire(_self, url, *, require_zip):
        requests.append((url, require_zip))
        return VerifiedDownload(
            path,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            "application/zip",
            url,
        )

    monkeypatch.setattr(research_acquisition.AssetDownloader, "acquire", acquire)
    return requests


def test_online_update_selects_latest_nonfuture_and_rechecks_same_url(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "data")
    requests = network_fixture(
        monkeypatch,
        airport_zip(tmp_path),
        candidates=[
            DiscoveryCandidate(FUTURE_URL, "Future", None, "asset", "airport-csv"),
            DiscoveryCandidate(OLDER_URL, "Older", None, "asset", "airport-csv"),
            DiscoveryCandidate(URL, "Current", None, "asset", "airport-csv"),
            DiscoveryCandidate(URL, "Page", None, "product-page", "edition"),
        ],
    )
    first = update_research_product(repository, nasr_product(), at=NOW)
    second = update_research_product(repository, nasr_product(), at=NOW)
    assert requests == [(URL, True), (URL, True)]
    assert first["status"] == "staged"
    assert second["status"] == "unchanged"
    assert first["snapshot_id"] == second["snapshot_id"]
    assert acquisition_count(repository) == 2
    assert repository.snapshot()["pointers"] == {}
    assert repository.list_releases() == []


def test_online_preview_uses_official_future_date_without_activation(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "data")
    path = airport_zip(tmp_path, text=FIXTURE.read_text().replace("2026/09/03", "2026/10/01"))
    requests = network_fixture(
        monkeypatch,
        path,
        candidates=[
            DiscoveryCandidate(URL, "Current", None, "asset", "airport-csv"),
            DiscoveryCandidate(FUTURE_URL, "Future", None, "asset", "airport-csv"),
        ],
    )
    result = update_research_product(repository, nasr_product(), preview=True, at=NOW)
    assert requests == [(FUTURE_URL, True)]
    assert result["official_effective_date"] == "2026-10-01"
    assert result["activation"] == "not-requested"
    with pytest.raises(ValueError):
        repository.activate_snapshot(result["snapshot_id"], nasr_product(), at=NOW)


def test_online_date_conflict_retains_acquisition_but_does_not_stage(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "data")
    path = airport_zip(tmp_path, text=FIXTURE.read_text().replace("2026/09/03", "2026/08/06"))
    network_fixture(monkeypatch, path)
    monkeypatch.setattr(
        repository, "stage_snapshot", lambda *_: pytest.fail("Staged wrong edition")
    )
    with pytest.raises(ValueError, match="EFF_DATE conflicts"):
        update_research_product(repository, nasr_product(), at=NOW)
    assert acquisition_count(repository) == 1


def test_online_acquisition_requires_permission_before_any_network(tmp_path, monkeypatch):
    from flightmap_ingestion import research_acquisition

    product = nasr_product()
    product.local_access.acquisition = "needs-user-action"
    monkeypatch.setattr(
        research_acquisition.FaaDiscovery, "fetch", lambda *_: pytest.fail("Followed agreement")
    )
    with pytest.raises(EvidenceRequired, match="user action"):
        update_research_product(Repository(tmp_path), product, at=NOW)


def test_online_cli_builds_and_network_failure_does_not_overwrite_strict_attempt(
    tmp_path, monkeypatch
):
    from flightmap_ingestion import research_acquisition

    repository = Repository(tmp_path / "data")
    repository.record_attempt("nasr", "needs-user-action", "Exact UTC remains unknown")
    network_fixture(monkeypatch, airport_zip(tmp_path))
    args = ["update", "--product", "nasr", "--research", "--data-dir", str(repository.data_dir)]
    first = CliRunner().invoke(app, args)
    assert first.exit_code == 0, first.output
    snapshot_id = json.loads(first.stdout)["snapshot_id"]

    def offline(*_):
        raise RuntimeError("Official network unavailable")

    monkeypatch.setattr(research_acquisition.FaaDiscovery, "fetch", offline)
    failure = CliRunner().invoke(app, args)
    assert failure.exit_code == 1
    assert json.loads(failure.stdout)["status"] == "failed"
    assert "Official network unavailable" in json.loads(failure.stdout)["error"]
    assert repository.get_snapshot(snapshot_id).product_id == "nasr"
    assert repository.snapshot()["attempts"][0]["status"] == "needs-user-action"
    assert repository.snapshot()["pointers"] == {}
