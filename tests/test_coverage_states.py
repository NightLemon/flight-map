"""Coverage describes acquisition and publication states independently."""

from fastapi.testclient import TestClient
from flightmap_api.main import create_app
from flightmap_storage import Repository
from research_helpers import END, NOW
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
