from flightmap_storage import Repository
from research_helpers import NOW, airport, product, report
from test_research_api import configured
from test_research_snapshots import snapshot


def configured_snapshot(tmp_path):
    client, repo, raw, _, time = configured(tmp_path)
    item = snapshot(raw)
    record = airport(raw)
    record.properties.update({"icao_id": "KTEST", "datum": "NAD83"})
    repo.stage_snapshot(item, [record], report())
    repo.activate_snapshot(item.id, product(), at=NOW)
    return client, repo, raw, item, time


def test_status_and_complete_report_keep_current_release_separate(tmp_path):
    client, repo, raw, item, _ = configured_snapshot(tmp_path)
    status = client.get("/api/v1/status").json()
    assert status["research"]["active_snapshots"]["nasr"]["id"] == item.id
    assert status["current_releases"]["nasr"]["id"] == "test-r1"
    research = client.get("/api/v1/research/snapshots")
    assert research.headers["cache-control"] == "no-store"
    assert research.json() == status["research"]
    details = client.get(f"/api/v1/research/snapshots/{item.id}/report").json()
    assert details["report"]["input_count"] == 1
    assert details["inputs"][0]["sha256"] == raw.sha256
    assert details["snapshot"]["exact_validity_status"] == "unknown"
    assert Repository(repo.data_dir).get_snapshot(item.id) == item


def test_research_search_faa_explicit_icao_name_and_version_switch(tmp_path):
    client, repo, raw, item, _ = configured_snapshot(tmp_path)
    for query in ["TEST", "KTEST", "Synthetic airport"]:
        response = client.get(
            "/api/v1/research/search", params={"q": query, "snapshot_id": item.id}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["items"][0]["identifier"] == "TEST"
        assert response.json()["items"][0]["provenance"]["asset_sha256"] == raw.sha256
    assert client.get("/api/v1/research/search", params={"q": "TEST"}).status_code == 400
    new = snapshot(raw, parser_version="correction")
    repo.stage_snapshot(new, [airport(raw)], report())
    repo.activate_snapshot(new.id, product(), at=NOW)
    params = {"q": "TEST", "snapshot_id": item.id}
    assert client.get("/api/v1/research/search", params=params).status_code == 409
    assert (
        client.get("/api/v1/research/search", params={**params, "mode": "history"}).status_code
        == 200
    )
    repo.revoke_snapshot(item.id, "withdrawn")
    assert (
        client.get("/api/v1/research/search", params={**params, "mode": "history"}).status_code
        == 410
    )
