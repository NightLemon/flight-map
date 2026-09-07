"""Coverage describes acquisition and publication states independently."""

import yaml
from fastapi.testclient import TestClient
from flightmap_api.main import create_app
from flightmap_storage import Repository
from research_helpers import END, NOW, airport, candidate, report
from test_research_api import configured


def test_coverage_distinguishes_no_import_failure_and_evidence_block(tmp_path):
    configured(tmp_path)  # Reuse only the isolated synthetic source policy.
    data_dir = tmp_path / "empty"
    repo = Repository(data_dir)
    client = TestClient(
        create_app(data_dir=data_dir, registry_path=tmp_path / "sources.yml", clock=lambda: NOW)
    )
    assert client.get("/api/v1/coverage").json()[0]["status"] == "not-imported"
    for attempt, expected in [
        ("failed", "failed"),
        ("needs-user-action", "blocked"),
        ("blocked", "blocked"),
    ]:
        repo.record_attempt("nasr", attempt, f"Synthetic {attempt} reason")
        row = client.get("/api/v1/coverage").json()[0]
        assert row["status"] == expected
        assert row["note"] == f"Synthetic {attempt} reason"
        assert row["latest_attempt"]["status"] == attempt


def test_failed_update_keeps_available_current_and_explains_failure(tmp_path):
    client, repo, _, release, _ = configured(tmp_path)
    repo.record_attempt("nasr", "failed", "Synthetic download failure")
    row = client.get("/api/v1/coverage").json()[0]
    assert row["status"] == "current"
    assert row["release_id"] == release.id
    assert row["note"] == "Synthetic download failure"


def test_expired_publication_has_explicit_coverage_state(tmp_path):
    client, _, _, release, time = configured(tmp_path)
    time[0] = END
    row = client.get("/api/v1/coverage").json()[0]
    assert row["status"] == "expired"
    assert row["release_id"] == release.id
    assert client.get("/api/v1/status").json()["current_releases"] == {}


def test_failed_candidate_retains_last_successful_cycle_and_official_notice_link(tmp_path):
    client, repo, raw, release, time = configured(tmp_path)
    failed = candidate(raw, "failed-correction", quality_status="quarantined")
    failed_report = report(
        success_count=0,
        error_count=1,
        issues=[{"code": "synthetic-error", "severity": "error", "message": "Test failure"}],
    )
    repo.stage(failed, [airport(raw)], failed_report)
    repo.record_attempt("nasr", "failed", "Synthetic correction failure", failed.id)
    registry_path = tmp_path / "sources.yml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["sources"][0]["products"].append(
        {
            "id": "safety-notices",
            "name": "Synthetic notice index",
            "landing_page": "https://www.faa.gov/test-fixture/notices/",
            "kind": "safety-notice",
            "categories": ["corrections"],
            "license_status": "link-only",
            "redistribution": "Synthetic source policy only",
        }
    )
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    time[0] = END

    row = next(r for r in client.get("/api/v1/coverage").json() if r["product_id"] == "nasr")
    assert row["status"] == "quarantined"
    assert row["last_successful_release"] == {
        "id": release.id,
        "airac": release.airac,
        "valid_from": release.valid_from.isoformat().replace("+00:00", "Z"),
        "valid_to": release.valid_to.isoformat().replace("+00:00", "Z"),
        "state": "history",
    }
    assert row["note"] == "Synthetic correction failure"
    assert row["notices_url"] == "https://www.faa.gov/test-fixture/notices/"
    assert client.get("/api/v1/status").json()["current_releases"] == {}
