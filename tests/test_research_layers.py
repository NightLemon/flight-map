"""Research-2 layer and airport communications contracts; synthetic originals only."""

import pytest
from flightmap_schema import ResearchRecord
from flightmap_schema.research_layers import LAYER_KINDS
from flightmap_storage import StoreError
from research_helpers import NOW, airport, product, report
from test_research_snapshots import snapshot
from test_snapshot_api import configured_snapshot


def layer_records(raw):
    parent = airport(raw)
    records = [parent]
    for kind in LAYER_KINDS.values():
        if kind == "airport":
            continue
        geometry = {"type": "Point", "coordinates": [-100, 40]}
        properties = {"raw_fields": {"note": "SYNTHETIC ONLY"}}
        if kind in {"runway", "airway"}:
            geometry = {"type": "LineString", "coordinates": [[-102, 40], [-98, 40]]}
        if kind == "communication":
            geometry = None
            properties.update(service="TOWER", frequency="119.100", unit="MHz", remarks="TEST")
        records.append(
            ResearchRecord(
                id=f"synthetic:{kind}",
                kind=kind,
                name=f"Synthetic {kind}",
                identifier="TEST",
                airport_id=parent.id if kind in {"runway", "communication"} else None,
                geometry=geometry,
                properties=properties,
                provenance=parent.provenance,
            )
        )
    return records


def extended(tmp_path):
    client, repo, raw, old, _ = configured_snapshot(tmp_path)
    item = snapshot(raw, schema_version="research-2", capabilities=list(LAYER_KINDS))
    records = layer_records(raw)
    counts = report(len(records), capabilities=list(LAYER_KINDS))
    repo.stage_snapshot(item, records, counts)
    repo.activate_snapshot(item.id, product(), at=NOW)
    return client, repo, raw, item, records, old


def test_layers_use_fixed_version_and_lines_crossing_the_viewport(tmp_path):
    client, repo, raw, item, records, old = extended(tmp_path)
    assert item.id != old.id
    assert repo.get_snapshot(old.id).schema_version == "research-1"
    for layer, kind in LAYER_KINDS.items():
        if kind == "communication":
            continue
        response = client.get(
            "/api/v1/research/features",
            params={
                "snapshot_id": item.id,
                "layer": layer,
                "bbox": "-101,39,-99,41",
                "limit": 1,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot_id"] == item.id
        assert len(payload["features"]) == 1
        assert payload["features"][0]["properties"]["kind"] == kind
        assert "raw_fields" not in payload["features"][0]["properties"]
        assert payload["features"][0]["properties"]["provenance"]["asset_sha256"] == raw.sha256
    assert (
        client.get("/api/v1/research/features", params={"snapshot_id": old.id}).status_code == 409
    )
    assert (
        client.get(
            "/api/v1/research/features",
            params={
                "snapshot_id": old.id,
                "mode": "history",
                "layer": "runways",
            },
        ).status_code
        == 422
    )


def test_communication_detail_and_search_exclusion(tmp_path):
    client, _, _, item, records, _ = extended(tmp_path)
    parent = records[0]
    url = f"/api/v1/research/airports/{parent.id}/communications"
    response = client.get(url, params={"snapshot_id": item.id})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rows = response.json()["items"]
    assert len(rows) == 1 and rows[0]["properties"]["frequency"] == "119.100"
    assert rows[0]["airport_id"] == parent.id
    assert (
        client.get(
            "/api/v1/research/airports/synthetic:runway/communications",
            params={
                "snapshot_id": item.id,
            },
        ).status_code
        == 404
    )
    detail = client.get(
        "/api/v1/research/records/synthetic:runway",
        params={
            "snapshot_id": item.id,
        },
    ).json()
    assert detail["record"]["properties"]["raw_fields"] == {"note": "SYNTHETIC ONLY"}
    found = client.get("/api/v1/research/search", params={"snapshot_id": item.id, "q": "TEST"})
    assert all(r["kind"] != "communication" for r in found.json()["items"])


@pytest.mark.parametrize("change", ["parent", "geometry", "frequency", "unit", "capability"])
def test_malformed_extended_records_are_rejected(tmp_path, change):
    _, repo, raw, _, _, _ = extended(tmp_path)
    records = layer_records(raw)
    item = snapshot(
        raw,
        schema_version="research-2",
        capabilities=list(LAYER_KINDS),
        parser_version="synthetic-invalid",
    )
    if change == "parent":
        records[-1].airport_id = "outside-this-snapshot"
    elif change == "geometry":
        records[1].geometry["coordinates"] = [[True, 40], [-98, 40]]
    elif change == "frequency":
        records[-1].properties["frequency"] = "NaN"
    elif change == "unit":
        records[-1].properties["unit"] = "unknown"
    else:
        records[1].kind = "procedure"
    with pytest.raises(StoreError):
        repo.stage_snapshot(item, records, report(len(records), capabilities=list(LAYER_KINDS)))


def test_dateline_segment_does_not_cross_greenwich(tmp_path):
    _, repo, raw, _, _, _ = extended(tmp_path)
    records = layer_records(raw)
    records[-2].geometry["coordinates"] = [[179, 40], [-179, 40]]
    item = snapshot(
        raw,
        schema_version="research-2",
        capabilities=list(LAYER_KINDS),
        parser_version="synthetic-dateline",
    )
    repo.stage_snapshot(item, records, report(len(records), capabilities=list(LAYER_KINDS)))
    assert len(repo.list_snapshot_records(item.id, kind="airway", bounds=(178, 39, -178, 41))) == 1
    assert repo.list_snapshot_records(item.id, kind="airway", bounds=(-1, 39, 1, 41)) == []


@pytest.mark.parametrize("action,expected", [("switch", 409), ("revoke", 410), ("original", 403)])
def test_communications_recheck_the_snapshot_after_loading(tmp_path, monkeypatch, action, expected):
    client, repo, raw, item, records, old = extended(tmp_path)
    original = repo.list_snapshot_records

    def racing_read(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("kind") == "communication":
            if action == "switch":
                repo.activate_snapshot(old.id, product(), at=NOW)
            elif action == "revoke":
                repo.revoke_snapshot(item.id, "SYNTHETIC withdrawal")
            else:
                (repo.assets_dir / raw.sha256).write_text("SYNTHETIC corrupt")
        return result

    monkeypatch.setattr(repo, "list_snapshot_records", racing_read)
    # create_app owns a separate Repository, so install the race on that shared class method.
    original_class = type(repo).list_snapshot_records

    def api_read(self, *args, **kwargs):
        result = original_class(self, *args, **kwargs)
        if kwargs.get("kind") == "communication":
            racing_read(*args, **kwargs)
        return result

    monkeypatch.setattr(type(repo), "list_snapshot_records", api_read)
    response = client.get(
        f"/api/v1/research/airports/{records[0].id}/communications",
        params={
            "snapshot_id": item.id,
        },
    )
    assert response.status_code == expected
    assert "items" not in response.json()
