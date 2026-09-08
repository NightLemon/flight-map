"""Independent snapshot integrity and read-race regressions; synthetic inputs only."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from flightmap_api.research_api import install_research_routes
from flightmap_storage import Repository, StoreError
from research_helpers import NOW, airport, asset, product, report
from test_research_snapshots import snapshot


def environment(tmp_path):
    repo = Repository(tmp_path / "data")
    raw = asset(repo, tmp_path)
    item = snapshot(raw)
    record = airport(raw)
    repo.stage_snapshot(item, [record], report())
    policy = product()
    repo.activate_snapshot(item.id, policy, at=NOW)
    clock = [NOW]
    application = FastAPI()

    @application.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(StoreError)
    async def store_error(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=error.status_code)

    install_research_routes(
        application,
        repo,
        lambda: {("faa-aeronav", "nasr"): policy},
        lambda: clock[0],
        "SYNTHETIC TEST ONLY",
    )
    return SimpleNamespace(
        repo=repo,
        raw=raw,
        item=item,
        record=record,
        policy=policy,
        clock=clock,
        client=TestClient(application),
    )


@pytest.mark.parametrize("coordinates", [None, 17, True, [True, False]])
def test_malformed_coordinate_candidates_are_blocked_without_unhandled_errors(
    tmp_path, coordinates
):
    env = environment(tmp_path)
    invalid = snapshot(env.raw, parser_version="synthetic-invalid-coordinates")
    record = env.record.model_copy(deep=True)
    record.geometry["coordinates"] = coordinates
    env.repo.stage_snapshot(invalid, [record], report())
    with pytest.raises(StoreError) as error:
        env.repo.resolve_snapshot(
            invalid.id,
            env.policy,
            source_id="faa-aeronav",
            mode="history",
            at=NOW,
        )
    assert error.value.status_code == 403
    assert env.repo.resolve_snapshot(env.item.id, env.policy, source_id="faa-aeronav", at=NOW)


def test_invalid_candidate_does_not_hide_the_valid_active_snapshot_from_status(tmp_path):
    env = environment(tmp_path)
    invalid = snapshot(env.raw, parser_version="synthetic-invalid-coordinates")
    record = env.record.model_copy(deep=True)
    record.geometry["coordinates"] = None
    env.repo.stage_snapshot(invalid, [record], report())
    response = env.client.get("/api/v1/research/snapshots")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    status = response.json()
    assert status["active_snapshots"]["nasr"]["id"] == env.item.id
    blocked = next(s for s in status["snapshots"] if s["id"] == invalid.id)
    assert blocked["state"] == "blocked" and blocked["date_status"] == "unavailable"


def test_record_validation_cache_cannot_label_an_older_sqlite_view_as_newer(tmp_path, monkeypatch):
    env = environment(tmp_path)
    original_row = env.repo._snapshot_row
    changed = env.record.model_copy(deep=True)
    changed.geometry["coordinates"] = [17, 53]
    injected = False
    # A second open connection keeps the WAL alive, as during concurrent API/CLI access.
    with env.repo._connect() as writer:

        def concurrent_row(connection, snapshot_id):
            nonlocal injected
            row = original_row(connection, snapshot_id)
            if not injected:
                injected = True
                writer.execute(
                    "UPDATE snapshot_records SET metadata=? WHERE snapshot_id=? AND id=?",
                    (json.dumps(changed.model_dump(mode="json")), snapshot_id, changed.id),
                )
                writer.commit()
            return row

        monkeypatch.setattr(env.repo, "_snapshot_row", concurrent_row)
        # This transaction started before the injected edit and may validate its original view.
        env.repo.resolve_snapshot(env.item.id, env.policy, source_id="faa-aeronav", at=NOW)
        # A later transaction sees altered coordinates with the original immutable digest.
        with pytest.raises(StoreError, match="checksum"):
            env.repo.resolve_snapshot(env.item.id, env.policy, source_id="faa-aeronav", at=NOW)


def test_status_keeps_multiple_validated_snapshots_but_rechecks_database_changes(
    tmp_path, monkeypatch
):
    from flightmap_storage import snapshots as module

    env = environment(tmp_path)
    other = snapshot(env.raw, parser_version="synthetic-second")
    env.repo.stage_snapshot(other, [env.record], report())
    checked = []
    original = module.check_record

    def observed(record, item):
        checked.append(item.id)
        return original(record, item)

    monkeypatch.setattr(module, "check_record", observed)
    policies = {("faa-aeronav", "nasr"): env.policy}
    env.repo.research_status(policies, at=NOW)
    assert set(checked) == {env.item.id, other.id}
    checked.clear()
    env.repo.research_status(policies, at=NOW)
    assert checked == []
    with env.repo._connect() as writer, writer:
        writer.execute(
            "UPDATE snapshot_records SET name='tampered' WHERE snapshot_id=?", (other.id,)
        )
    state = env.repo.research_status(policies, at=NOW)
    assert next(s for s in state["snapshots"] if s["id"] == other.id)["state"] == "blocked"
    assert state["active_snapshots"]["nasr"]["id"] == env.item.id


@pytest.mark.parametrize("endpoint", ["search", "features"])
@pytest.mark.parametrize(
    "change,status",
    [
        ("switch", 409),
        ("revoke", 410),
        ("policy", 403),
        ("future", 409),
        ("original", 403),
    ],
)
def test_data_responses_recheck_the_snapshot_after_reading(
    tmp_path,
    monkeypatch,
    endpoint,
    change,
    status,
):
    env = environment(tmp_path)
    original_read = env.repo.list_snapshot_records

    def changed_read(*args, **kwargs):
        records = original_read(*args, **kwargs)
        if change == "switch":
            correction = snapshot(env.raw, parser_version="synthetic-correction")
            env.repo.stage_snapshot(correction, [env.record], report())
            env.repo.activate_snapshot(correction.id, env.policy, at=NOW)
        elif change == "revoke":
            env.repo.revoke_snapshot(env.item.id, "Synthetic withdrawal during API read")
        elif change == "policy":
            env.policy.local_access.processing = "unknown"
        elif change == "future":
            env.clock[0] -= timedelta(days=7)
        else:
            (env.repo.assets_dir / env.raw.sha256).write_bytes(b"Synthetic corruption")
        return records

    monkeypatch.setattr(env.repo, "list_snapshot_records", changed_read)
    response = env.client.get(
        f"/api/v1/research/{endpoint}",
        params={"snapshot_id": env.item.id, "q": "TEST"},
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "features" not in response.json() and "items" not in response.json()
