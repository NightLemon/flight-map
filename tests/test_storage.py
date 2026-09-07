import sqlite3
from datetime import timedelta

import pytest
from flightmap_schema import LocalAccessPolicy, ValidationIssue
from flightmap_storage import Repository, StoreError
from research_helpers import END, NOW, START, airport, asset, candidate, product, report


def setup_release(tmp_path):
    repo = Repository(tmp_path / "store")
    raw = asset(repo, tmp_path)
    release = candidate(raw)
    repo.stage(release, [airport(raw)], report())
    return repo, raw, release


def test_transactional_promotion_restart_and_expiration(tmp_path):
    repo, _, release = setup_release(tmp_path)
    repo.promote(release.id, product(), at=START)
    reopened = Repository(tmp_path / "store")
    assert reopened.resolve(release.id, product(), source_id="faa-aeronav", at=NOW) == release
    with pytest.raises(StoreError) as expired:
        reopened.resolve(release.id, product(), source_id="faa-aeronav", at=END)
    assert expired.value.status_code == 410
    assert (
        reopened.resolve(release.id, product(), source_id="faa-aeronav", mode="history", at=END)
        == release
    )


def test_failed_promotion_preserves_pointer_and_future_is_preview(tmp_path):
    repo, raw, release = setup_release(tmp_path)
    repo.promote(release.id, product(), at=NOW)
    future = candidate(raw, "future", valid_from=END, valid_to=END + timedelta(days=28))
    repo.stage(future, [airport(raw)], report())
    with pytest.raises(StoreError):
        repo.promote(future.id, product(), at=NOW)
    assert repo.resolve(release.id, product(), source_id="faa-aeronav", at=NOW).id == release.id
    assert (
        repo.resolve(future.id, product(), source_id="faa-aeronav", at=NOW, mode="preview").id
        == future.id
    )


def test_same_cycle_correction_conflicts_with_pinned_old_read(tmp_path):
    repo, raw, release = setup_release(tmp_path)
    repo.promote(release.id, product(), at=NOW)
    correction = candidate(raw, "correction")
    repo.stage(correction, [airport(raw, "CHANGED")], report())
    repo.promote(correction.id, product(), at=NOW)
    with pytest.raises(StoreError) as stale:
        repo.resolve(release.id, product(), source_id="faa-aeronav", at=NOW)
    assert stale.value.status_code == 409
    assert repo.report(correction.id)["diff"]["added"] == 1
    assert repo.report(correction.id)["diff"]["removed"] == 1
    assert (
        repo.resolve(release.id, product(), source_id="faa-aeronav", at=NOW, mode="history").id
        == release.id
    )


def test_revoke_cannot_repromote_or_read_even_history(tmp_path):
    repo, _, release = setup_release(tmp_path)
    repo.promote(release.id, product(), at=NOW)
    repo.revoke(release.id, "test withdrawal")
    for mode in ["current", "history", "preview"]:
        with pytest.raises(StoreError) as error:
            repo.resolve(release.id, product(), source_id="faa-aeronav", at=NOW, mode=mode)
        assert error.value.status_code == 410
    with pytest.raises(StoreError):
        repo.promote(release.id, product(), at=NOW)
    assert not repo.snapshot()["pointers"]


def test_assets_deduplicated_acquisitions_kept(tmp_path):
    repo, raw, _ = setup_release(tmp_path)
    assert asset(repo, tmp_path).sha256 == raw.sha256
    with sqlite3.connect(repo.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM acquisitions").fetchone()[0] == 2


def test_idempotent_stage_and_immutable_collision(tmp_path):
    repo, raw, release = setup_release(tmp_path)
    assert repo.stage(release, [airport(raw)], report()) == release.id
    with pytest.raises(StoreError, match="different immutable"):
        repo.stage(release, [airport(raw, "OTHER")], report())


def test_permissions_rechecked_on_read(tmp_path):
    repo, _, release = setup_release(tmp_path)
    repo.promote(release.id, product(), at=NOW)
    updated = product().model_copy(update={"local_access": LocalAccessPolicy()})
    with pytest.raises(StoreError) as error:
        repo.resolve(release.id, updated, source_id="faa-aeronav", at=NOW)
    assert error.value.status_code == 403


def test_rejects_identity_mismatch_and_corrupt_asset(tmp_path):
    repo, raw, release = setup_release(tmp_path)
    with pytest.raises(StoreError, match="identity"):
        repo.promote(release.id, product("dtpp"), at=NOW)
    (repo.assets_dir / raw.sha256).write_bytes(b"CORRUPT TEST")
    with pytest.raises(StoreError, match="integrity"):
        repo.promote(release.id, product(), at=NOW)
    assert not repo.snapshot()["pointers"]


def test_blocking_release_issue_and_unaccounted_inputs_rejected(tmp_path):
    repo, raw, release = setup_release(tmp_path)
    release = release.model_copy(
        update={
            "id": "bad",
            "issues": [ValidationIssue(code="bad", severity="fatal", message="test")],
        }
    )
    with pytest.raises(StoreError, match="blocking"):
        repo.stage(release, [airport(raw)], report())
    with pytest.raises(ValueError, match="account"):
        report(input_count=2)


def test_missing_or_foreign_asset_and_duplicate_record_rejected(tmp_path):
    repo, raw, release = setup_release(tmp_path)
    with pytest.raises(StoreError, match="Duplicate"):
        repo.stage(candidate(raw, "dup"), [airport(raw), airport(raw)], report(2))
    bad = candidate(raw, "foreign", product_id="dtpp")
    with pytest.raises(StoreError, match="another product"):
        repo.stage(bad, [airport(raw)], report())
    fake = airport(raw).model_copy(
        update={"provenance": airport(raw).provenance.model_copy(update={"asset_sha256": "a" * 64})}
    )
    with pytest.raises(StoreError, match="provenance"):
        repo.stage(candidate(raw, "bad-provenance"), [fake], report())


def test_unknown_database_version_is_not_mutated(tmp_path):
    repo = Repository(tmp_path / "store")
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(StoreError, match="schema version"):
        Repository(tmp_path / "store")
    with sqlite3.connect(repo.db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99
