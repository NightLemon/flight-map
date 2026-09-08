import shutil
import sqlite3
from datetime import date, timedelta

import pytest
from flightmap_schema import ResearchSnapshot
from flightmap_storage import Repository, StoreError
from research_helpers import NOW, airport, asset, product, report


def snapshot(raw, **changes):
    return ResearchSnapshot(
        **{
            "source_id": "faa-aeronav",
            "product_id": "nasr",
            "official_effective_date": date(2026, 9, 3),
            "date_evidence": ["SYNTHETIC EFF_DATE"],
            "input_sha256": [raw.sha256],
            "parser_version": "test-only",
            "local_access": product().local_access,
            "update_interval_evidence": ["SYNTHETIC 28-day subscription"],
            **changes,
        }
    )


def setup_snapshot(tmp_path):
    repo = Repository(tmp_path / "store")
    raw = asset(repo, tmp_path)
    item = snapshot(raw)
    repo.stage_snapshot(item, [airport(raw)], report())
    return repo, raw, item


def test_immutable_snapshot_roundtrip_and_zero_extra_acquisitions(tmp_path):
    repo, raw, item = setup_snapshot(tmp_path)
    original = repo.snapshot_report(item.id)
    assert repo.stage_snapshot(item, [airport(raw)], report()) == item.id
    assert repo.get_snapshot(item.id) == item
    assert repo.list_snapshot_records(item.id) == [airport(raw)]
    assert original["inputs"] == [raw.model_dump(mode="json")]
    assert original["report"] == report().model_dump(mode="json")
    assert repo.get_acquired_asset(raw.sha256, source_id="faa-aeronav", product_id="nasr") == raw
    with sqlite3.connect(repo.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM acquisitions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM research_snapshots").fetchone()[0] == 1
    with pytest.raises(StoreError, match="immutable"):
        repo.stage_snapshot(item, [airport(raw, "DIFFERENT")], report())
    assert repo.snapshot_report(item.id) == original


def test_identity_changes_with_evidence_and_rejects_forgery(tmp_path):
    repo, raw, item = setup_snapshot(tmp_path)
    correction = snapshot(raw, parser_version="test-only-2")
    assert correction.id != item.id
    assert snapshot(raw, date_evidence=["changed"]).id != item.id
    with pytest.raises(ValueError, match="ID"):
        ResearchSnapshot.model_validate({**item.model_dump(), "id": "forged"})
    with pytest.raises(StoreError):
        repo.get_acquired_asset(raw.sha256, source_id="faa-aeronav", product_id="dtpp")
    with pytest.raises(StoreError, match="counts"):
        repo.stage_snapshot(correction, [airport(raw)], report(2))


def test_multiple_inputs_and_blocking_candidate_report_are_preserved(tmp_path):
    repo, first, _ = setup_snapshot(tmp_path)
    other = tmp_path / "other.txt"
    other.write_text("SYNTHETIC SECOND INPUT")
    raw = repo.store_asset(
        other,
        source_id=first.source_id,
        product_id=first.product_id,
        source_url=first.source_url,
        retrieved_at=first.retrieved_at,
        content_type="text/plain",
    )
    item = snapshot(first, input_sha256=[first.sha256, raw.sha256])
    failed = report(2, success_count=1, error_count=1)
    repo.stage_snapshot(item, [airport(first)], failed)
    saved = repo.snapshot_report(item.id)
    assert len(saved["inputs"]) == 2
    assert saved["report"]["input_count"] == 2
    assert saved["report"]["error_count"] == 1


def test_read_gates_recheck_policy_report_source_and_record_integrity(tmp_path):
    repo, _, item = setup_snapshot(tmp_path)
    assert (
        repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", mode="history", at=NOW)
        == item
    )
    denied = product()
    denied.local_access.processing = "unknown"
    for policy, source in [(denied, "faa-aeronav"), (product(), "wrong-source")]:
        with pytest.raises(StoreError) as error:
            repo.resolve_snapshot(item.id, policy, source_id=source, mode="history", at=NOW)
        assert error.value.status_code == 403
    with repo._connect() as connection, connection:
        connection.execute("UPDATE snapshot_records SET name='tampered'")
    with pytest.raises(StoreError, match="records failed"):
        repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", mode="history", at=NOW)


def test_bad_report_original_and_missing_input_are_blocked(tmp_path):
    repo, raw, item = setup_snapshot(tmp_path)
    (repo.assets_dir / raw.sha256).write_bytes(b"corrupt")
    with pytest.raises(StoreError, match="integrity"):
        repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", mode="history", at=NOW)
    (repo.assets_dir / raw.sha256).write_bytes(b"SYNTHETIC TEST ONLY")
    with repo._connect() as connection, connection:
        connection.execute("UPDATE research_snapshots SET report=?", ("{}",))
    with pytest.raises(StoreError, match="report"):
        repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", mode="history", at=NOW)


def test_activation_is_transactional_and_future_is_explicit(tmp_path):
    repo, raw, item = setup_snapshot(tmp_path)
    repo.activate_snapshot(item.id, product(), at=NOW)
    next_item = snapshot(raw, parser_version="correction")
    repo.stage_snapshot(next_item, [airport(raw)], report())
    with repo._connect() as connection, connection:
        connection.execute(
            "CREATE TRIGGER fail_activation BEFORE UPDATE OF activated_at "
            "ON research_snapshots BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        repo.activate_snapshot(next_item.id, product(), at=NOW)
    assert repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", at=NOW) == item
    with repo._connect() as connection, connection:
        connection.execute("DROP TRIGGER fail_activation")
    repo.activate_snapshot(next_item.id, product(), at=NOW)
    with pytest.raises(StoreError) as conflict:
        repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", at=NOW)
    assert conflict.value.status_code == 409
    future = snapshot(raw, official_effective_date=NOW.date() + timedelta(days=1))
    repo.stage_snapshot(future, [airport(raw)], report())
    with pytest.raises(StoreError, match="Future"):
        repo.activate_snapshot(future.id, product(), at=NOW)
    assert (
        repo.resolve_snapshot(future.id, product(), source_id="faa-aeronav", mode="preview", at=NOW)
        == future
    )
    reopened = Repository(repo.data_dir)
    assert reopened.resolve_snapshot(next_item.id, product(), source_id="faa-aeronav", at=NOW)


def test_revocation_survives_restart_and_prevents_reactivation(tmp_path):
    repo, _, item = setup_snapshot(tmp_path)
    repo.activate_snapshot(item.id, product(), at=NOW)
    repo.revoke_snapshot(item.id, "SYNTHETIC withdrawal")
    repo = Repository(repo.data_dir)
    for mode in ["active", "history", "preview"]:
        with pytest.raises(StoreError) as error:
            repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", mode=mode, at=NOW)
        assert error.value.status_code == 410
    with pytest.raises(StoreError, match="revoked"):
        repo.activate_snapshot(item.id, product(), at=NOW)
    with repo._connect() as connection:
        assert not connection.execute("SELECT * FROM active_snapshots").fetchall()
    assert repo.snapshot_report(item.id)["snapshot"]["revoked_reason"] == "SYNTHETIC withdrawal"


def test_snapshot_dates_are_reminders_not_exact_expiration(tmp_path):
    repo, raw, item = setup_snapshot(tmp_path)
    policies = {("faa-aeronav", "nasr"): product()}
    repo.activate_snapshot(item.id, product(), at=NOW)
    now_status = repo.research_status(policies, at=NOW)["active_snapshots"]["nasr"]
    assert now_status["date_status"] == "researchable"
    assert now_status["expected_update_date"] == "2026-10-01"
    assert "valid_to" not in now_status
    later = NOW + timedelta(days=60)
    assert (
        repo.research_status(policies, at=later)["active_snapshots"]["nasr"]["date_status"]
        == "update-due"
    )
    assert repo.resolve_snapshot(item.id, product(), source_id="faa-aeronav", at=later) == item
    future = snapshot(raw, official_effective_date=later.date())
    repo.stage_snapshot(future, [airport(raw)], report())
    assert repo.research_status(policies, at=NOW)["snapshots"][0]["date_status"] == "future"
    policies[("faa-aeronav", "nasr")].local_access.processing = "unknown"
    blocked = repo.research_status(policies, at=NOW)
    assert not blocked["active_snapshots"]
    assert all(s["date_status"] == "unavailable" for s in blocked["snapshots"])


def test_relocated_store_uses_its_own_originals_without_rewriting_acquisition(tmp_path):
    repo, raw, item = setup_snapshot(tmp_path)
    restored_dir = tmp_path / "restored"
    shutil.copytree(repo.data_dir, restored_dir)
    restored = Repository(restored_dir)
    acquired = restored.get_acquired_asset(
        raw.sha256, source_id=raw.source_id, product_id=raw.product_id
    )
    assert acquired.storage_uri == str(restored.assets_dir / raw.sha256)
    assert restored.snapshot_report(item.id)["inputs"][0]["storage_uri"] == raw.storage_uri
    (repo.assets_dir / raw.sha256).unlink()
    assert (
        restored.resolve_snapshot(
            item.id, product(), source_id="faa-aeronav", mode="history", at=NOW
        )
        == item
    )
