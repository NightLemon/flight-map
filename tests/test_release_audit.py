"""Independent lifecycle and geometry regressions using synthetic local releases."""

import json
import sqlite3

import pytest
import yaml
from fastapi.testclient import TestClient
from flightmap_api.main import create_app
from flightmap_schema import Provenance, ResearchRecord
from flightmap_schema.publication import check_publication
from flightmap_storage import Repository, StoreError
from research_helpers import END, NOW, airport, asset, candidate, product, report


def environment(tmp_path):
    repo = Repository(tmp_path / "data")
    raw = asset(repo, tmp_path)
    registry = tmp_path / "source.yml"
    registry.write_text(yaml.safe_dump({"version": 1, "sources": [{
        "id": "faa-aeronav", "name": "Synthetic test source", "authority": "Synthetic",
        "country": "US", "trust_level": "A", "official": True,
        "products": [product().model_dump(mode="json")],
    }]}), encoding="utf-8")
    time = [NOW]
    application = create_app(data_dir=repo.data_dir, registry_path=registry, clock=lambda: time[0])
    return repo, raw, TestClient(application), application.state.repository, time


def stage(repo, raw, release_id="audit-r1", records=None):
    release = candidate(raw, release_id)
    parsed = [airport(raw)] if records is None else records
    repo.stage(release, parsed, report(len(parsed)))
    return release


def program(raw):
    return ResearchRecord(
        id="audit-program", kind="procedure", name="Synthetic program", identifier="SYNTH",
        properties={"fixture": True, "procedure_type": "SID"},
        provenance=Provenance(asset_sha256=raw.sha256, line=1, locator="synthetic:1"),
    )


def program_leg(raw, identifier, terminator, line, sequence, branch="main"):
    return ResearchRecord(
        id=identifier, kind="leg", name=f"Synthetic {identifier}", parent_id="audit-program",
        branch_id=branch, sequence=sequence,
        provenance=Provenance(asset_sha256=raw.sha256, line=line, locator=f"synthetic:{line}"),
        properties={
            "fixture": True, "path_terminator": terminator, "fix_resolution": "unique",
            "resolved_fix": {"id": f"fix-{line}", "latitude": 40, "longitude": -100 + line},
        },
    )


def geometry(client, release):
    response = client.get("/api/v1/procedures/audit-program/geometry", params={
        "release_id": release.id, "branch_id": "main",
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_geometry_api_keeps_other_branches_between_original_legs(tmp_path):
    repo, raw, client, _, _ = environment(tmp_path)
    records = [program(raw), program_leg(raw, "begin", "IF", 2, 10),
               program_leg(raw, "other-branch", "RF", 3, 15, "missed"),
               program_leg(raw, "finish", "TF", 4, 20)]
    release = stage(repo, raw, records=records)
    repo.promote(release.id, product(), at=NOW)
    result = geometry(client, release)
    assert [feature["id"] for feature in result["features"]] == ["begin"]
    assert result["gaps"] == [{"leg_id": "finish", "branch_id": "main",
                                "reason": "branch-boundary", "coordinates": [-96.0, 40.0]}]


def test_geometry_api_uses_raw_positions_instead_of_sequence_to_make_adjacency(tmp_path):
    repo, raw, client, _, _ = environment(tmp_path)
    records = [program(raw), program_leg(raw, "begin", "IF", 2, 10),
               program_leg(raw, "unknown", "RF", 3, 30),
               program_leg(raw, "finish", "TF", 4, 20)]
    release = stage(repo, raw, records=records)
    repo.promote(release.id, product(), at=NOW)
    result = geometry(client, release)
    assert [feature["id"] for feature in result["features"]] == ["begin"]
    assert [gap["leg_id"] for gap in result["gaps"]] == ["unknown", "finish"]


def test_active_unpromoted_candidate_cannot_be_read_by_claiming_history(tmp_path):
    repo, raw, client, _, _ = environment(tmp_path)
    release = stage(repo, raw)
    state = next(
        r for r in client.get("/api/v1/status").json()["releases"] if r["id"] == release.id
    )
    assert state["state"] == "staged"
    response = client.get("/api/v1/search", params={
        "q": "TEST", "release_id": release.id, "mode": "history",
    })
    assert response.status_code == 409


def test_expired_historical_import_does_not_require_impossible_current_promotion(tmp_path):
    repo, raw, client, _, time = environment(tmp_path)
    release = stage(repo, raw)
    time[0] = END
    response = client.get("/api/v1/search", params={
        "q": "TEST", "release_id": release.id, "mode": "history",
    })
    assert response.status_code == 200
    assert response.json()["mode"] == "history"


def test_repository_rejects_unknown_mode_at_runtime(tmp_path):
    repo, raw, _, _, _ = environment(tmp_path)
    release = stage(repo, raw)
    with pytest.raises(StoreError):
        repo.resolve(release.id, product(), source_id="faa-aeronav", mode="typo", at=NOW)


@pytest.mark.parametrize("broken_report", [
    {},
    {"input_count": 1, "success_count": 0, "unsupported_count": 0, "error_count": 1,
     "issues": [], "capabilities": ["airports"]},
    {"input_count": 1, "success_count": 1, "unsupported_count": 0, "error_count": 0,
     "issues": [], "capabilities": []},
])
def test_persisted_report_damage_fails_closed_on_reads_and_status(tmp_path, broken_report):
    repo, raw, client, _, _ = environment(tmp_path)
    release = stage(repo, raw)
    repo.promote(release.id, product(), at=NOW)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("UPDATE releases SET report=? WHERE id=?",
                           (json.dumps(broken_report), release.id))
    with pytest.raises(StoreError):
        repo.resolve(release.id, product(), source_id="faa-aeronav", at=NOW)
    response = client.get("/api/v1/search", params={"q": "TEST", "release_id": release.id})
    assert 400 <= response.status_code < 500
    status = client.get("/api/v1/status")
    assert status.status_code == 200
    assert not status.json()["current_releases"]
    assert status.json()["releases"][0]["state"] == "blocked"


def test_promotion_rechecks_that_persisted_records_still_exist(tmp_path):
    repo, raw, _, _, _ = environment(tmp_path)
    release = stage(repo, raw)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM records WHERE release_id=?", (release.id,))
    with pytest.raises(StoreError):
        repo.promote(release.id, product(), at=NOW)
    assert not repo.snapshot()["pointers"]


@pytest.mark.parametrize("change,expected", [("correction", 409), ("expiry", 410), ("revoke", 410)])
def test_query_rechecks_release_after_data_read(tmp_path, monkeypatch, change, expected):
    repo, raw, client, api_repo, time = environment(tmp_path)
    release = stage(repo, raw)
    repo.promote(release.id, product(), at=NOW)
    correction = stage(repo, raw, "corrected")
    original = api_repo.list_records

    def changing_read(*args, **kwargs):
        records = original(*args, **kwargs)
        if change == "correction":
            repo.promote(correction.id, product(), at=NOW)
        elif change == "expiry":
            time[0] = END
        else:
            repo.revoke(release.id, "Synthetic mid-request withdrawal")
        return records

    monkeypatch.setattr(api_repo, "list_records", changing_read)
    response = client.get("/api/v1/search", params={"q": "TEST", "release_id": release.id})
    assert response.status_code == expected
    assert "items" not in response.json()
    assert response.headers["cache-control"] == "no-store"


def test_publication_rejects_unknown_audience_at_runtime(tmp_path):
    repo, raw, _, _, _ = environment(tmp_path)
    release = candidate(raw, license_status="public-domain")
    source_product = product().model_copy(update={"license_status": release.license_status})
    with pytest.raises(ValueError):
        check_publication(release, source_product, source_id="faa-aeronav", audience="typo", at=NOW)
