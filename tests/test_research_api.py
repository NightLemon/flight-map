from datetime import timedelta

import yaml
from fastapi.testclient import TestClient
from flightmap_api.main import create_app
from flightmap_storage import Repository
from research_helpers import END, NOW, airport, asset, candidate, product, report


def configured(tmp_path):
    data_dir = tmp_path / "data"
    repo = Repository(data_dir)
    raw = asset(repo, tmp_path)
    release = candidate(raw)
    repo.stage(release, [airport(raw)], report())
    repo.promote(release.id, product(), at=NOW)
    registry = tmp_path / "sources.yml"
    registry.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "faa-aeronav",
                        "name": "Test source",
                        "authority": "Test only",
                        "country": "US",
                        "trust_level": "A",
                        "official": True,
                        "products": [product().model_dump(mode="json")],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    time = [NOW]
    client = TestClient(
        create_app(data_dir=data_dir, registry_path=registry, clock=lambda: time[0])
    )
    return client, repo, raw, release, time


def test_api_real_repository_search_bbox_and_provenance(tmp_path):
    client, _, raw, release, _ = configured(tmp_path)
    status = client.get("/api/v1/status")
    assert status.headers["cache-control"] == "no-store"
    assert status.json()["current_releases"]["nasr"]["id"] == release.id
    result = client.get("/api/v1/search", params={"q": "TEST", "release_id": release.id}).json()
    assert result["items"][0]["provenance"]["asset_sha256"] == raw.sha256
    for bbox, count in [("-101,39,-99,41", 1), ("10,30,20,40", 0), ("170,-90,-90,90", 1)]:
        response = client.get(
            "/api/v1/features",
            params={
                "release_id": release.id,
                "layer": "airports",
                "bbox": bbox,
            },
        )
        assert response.status_code == 200
        assert len(response.json()["features"]) == count
    assert client.get("/api/v1/search", params={"q": "TEST"}).status_code == 400


def test_all_default_endpoints_reject_expired_release(tmp_path):
    client, _, _, release, time = configured(tmp_path)
    time[0] = END
    for path, params in [
        ("/api/v1/search", {"q": "TEST"}),
        ("/api/v1/features", {"layer": "airports"}),
        ("/api/v1/airports/TEST/charts", {}),
        ("/api/v1/airports/TEST/procedures", {}),
        ("/api/v1/procedures/anything", {}),
        ("/api/v1/procedures/anything/geometry", {"branch_id": "test"}),
    ]:
        response = client.get(path, params={"release_id": release.id, **params})
        assert response.status_code == 410
        assert response.headers["cache-control"] == "no-store"
    assert not client.get("/api/v1/status").json()["current_releases"]
    historical = client.get(
        "/api/v1/search",
        params={
            "release_id": release.id,
            "q": "TEST",
            "mode": "history",
        },
    )
    assert historical.status_code == 200
    assert historical.json()["mode"] == "history"


def test_pinned_version_conflict_and_future_preview(tmp_path):
    client, repo, raw, release, _ = configured(tmp_path)
    next_release = candidate(raw, "next", valid_from=END, valid_to=END + timedelta(days=28))
    repo.stage(next_release, [airport(raw)], report())
    params = {"q": "TEST", "release_id": next_release.id}
    assert client.get("/api/v1/search", params=params).status_code == 410
    assert client.get("/api/v1/search", params={**params, "mode": "preview"}).status_code == 200
    correction = candidate(raw, "corrected")
    repo.stage(correction, [airport(raw)], report())
    repo.promote(correction.id, product(), at=NOW)
    response = client.get("/api/v1/search", params={"q": "TEST", "release_id": release.id})
    assert response.status_code == 409


def test_bbox_validation_and_query_literal(tmp_path):
    client, _, _, release, _ = configured(tmp_path)
    for bbox in ["1,2,3", "nan,1,2,3", "-180,80,180,-80", "181,0,0,1"]:
        assert (
            client.get(
                "/api/v1/features",
                params={
                    "release_id": release.id,
                    "layer": "airports",
                    "bbox": bbox,
                },
            ).status_code
            == 400
        )
    assert (
        client.get(
            "/api/v1/search",
            params={
                "q": "%",
                "release_id": release.id,
            },
        ).json()["items"]
        == []
    )
