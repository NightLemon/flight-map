"""Fixed synthetic acceptance scenarios for release differences and directory recovery."""

import hashlib
import shutil
from datetime import timedelta

import pytest
from flightmap_schema import Provenance
from flightmap_storage import Repository, StoreError
from research_helpers import END, NOW, airport, candidate, product, report


def stored_asset(repo, tmp_path, label):
    path = tmp_path / f"synthetic-{label}.txt"
    path.write_text(f"SYNTHETIC ACCEPTANCE DATA ONLY: {label}", encoding="utf-8")
    return repo.store_asset(
        path, source_id="faa-aeronav", product_id="nasr",
        source_url=f"https://www.faa.gov/test-fixture/{label}.txt",
        retrieved_at=NOW, content_type="text/plain",
    )


def with_provenance(record, raw, line):
    return record.model_copy(update={"provenance": Provenance(
        asset_sha256=raw.sha256, member="synthetic/APT_BASE.csv", line=line,
        locator=f"synthetic:row:{line}",
    )})


def test_correction_and_next_cycle_have_fixed_semantic_difference_counts(tmp_path):
    repo = Repository(tmp_path / "data")
    original_raw = stored_asset(repo, tmp_path, "original")
    original = candidate(original_raw, "original-2609")
    unchanged, edited, removed = [airport(original_raw, name) for name in ["KEEP", "EDIT", "DROP"]]
    repo.stage(original, [unchanged, edited, removed], report(3))
    repo.promote(original.id, product(), at=NOW)
    assert repo.report(original.id)["diff"] == {
        "previous_release_id": None, "added": 3, "removed": 0, "changed": 0,
    }

    corrected_raw = stored_asset(repo, tmp_path, "correction")
    correction = candidate(corrected_raw, "correction-2609")
    corrected_records = [
        with_provenance(unchanged, corrected_raw, 201),
        with_provenance(edited.model_copy(update={
            "name": "Synthetic revised airport EDIT",
            "geometry": {"type": "Point", "coordinates": [-100.5, 40.25]},
        }), corrected_raw, 202),
        with_provenance(airport(corrected_raw, "NEW"), corrected_raw, 203),
    ]
    repo.stage(correction, corrected_records, report(3))
    repo.promote(correction.id, product(), at=NOW)
    assert correction.airac == original.airac
    assert repo.report(correction.id)["diff"] == {
        "previous_release_id": original.id, "added": 1, "removed": 1, "changed": 1,
    }
    assert repo.report(correction.id)["report"]["success_count"] == 3

    next_raw = stored_asset(repo, tmp_path, "next-cycle")
    next_cycle = candidate(next_raw, "next-2610", airac="2610",
                           valid_from=END, valid_to=END + timedelta(days=28))
    next_records = [
        with_provenance(record, next_raw, 301 + index)
        for index, record in enumerate(corrected_records)
    ]
    repo.stage(next_cycle, next_records, report(3))
    assert repo.resolve(next_cycle.id, product(), source_id="faa-aeronav",
                        mode="preview", at=NOW).id == next_cycle.id
    assert all(before.provenance != after.provenance
               for before, after in zip(corrected_records, next_records, strict=True))
    assert repo.report(next_cycle.id)["diff"] == {
        "previous_release_id": correction.id, "added": 0, "removed": 0, "changed": 0,
    }


def test_quiescent_directory_copy_recovers_assets_versions_and_revocation(tmp_path):
    source_dir = tmp_path / "original-data"
    source = Repository(source_dir)
    withdrawn_raw = stored_asset(source, tmp_path, "withdrawn")
    current_raw = stored_asset(source, tmp_path, "current")
    preview_raw = stored_asset(source, tmp_path, "preview")
    withdrawn = candidate(withdrawn_raw, "withdrawn-2609")
    current = candidate(current_raw, "current-2609")
    preview = candidate(preview_raw, "preview-2610", airac="2610",
                        valid_from=END, valid_to=END + timedelta(days=28))
    releases = [withdrawn, current, preview]
    records = {
        withdrawn.id: [airport(withdrawn_raw, "WITHDRAWN")],
        current.id: [airport(current_raw, "CURRENT")],
        preview.id: [airport(preview_raw, "PREVIEW")],
    }
    for release in releases:
        source.stage(release, records[release.id], report())
    source.promote(withdrawn.id, product(), at=NOW)
    source.revoke(withdrawn.id, "Synthetic source withdrawal before backup")
    source.promote(current.id, product(), at=NOW)
    expected_pointers = source.snapshot()["pointers"]
    expected_reports = {release.id: source.report(release.id) for release in releases}
    assert expected_pointers == {"faa-aeronav:nasr": current.id}

    # Repository methods close their connections before returning. Discard the source
    # instance before copying every file, including any remaining SQLite sidecars.
    del source
    restored_dir = tmp_path / "restored-data"
    shutil.copytree(source_dir, restored_dir)
    offline_source = tmp_path / "offline-original-data"
    # All move targets are resolved and confined to this test's private temporary root.
    for path in [source_dir, restored_dir, offline_source]:
        assert path.resolve().is_relative_to(tmp_path.resolve())
    source_dir.rename(offline_source)
    assert not source_dir.exists()

    recovered = Repository(restored_dir)
    assert recovered.snapshot()["pointers"] == expected_pointers
    assert recovered.resolve(current.id, product(), source_id="faa-aeronav", at=NOW) == current
    for release in releases:
        assert recovered.get_release(release.id) == release
        assert recovered.list_records(release.id) == records[release.id]
        assert recovered.report(release.id) == expected_reports[release.id]
        for digest in release.input_sha256:
            restored_asset = recovered.assets_dir / digest
            assert restored_asset.resolve().is_relative_to(restored_dir.resolve())
            assert hashlib.sha256(restored_asset.read_bytes()).hexdigest() == digest
    assert recovered.report(withdrawn.id)["release"]["revoked_reason"] == (
        "Synthetic source withdrawal before backup"
    )
    with pytest.raises(StoreError) as revoked_read:
        recovered.resolve(withdrawn.id, product(), source_id="faa-aeronav", mode="history", at=END)
    assert revoked_read.value.status_code == 410
    with pytest.raises(StoreError):
        recovered.promote(withdrawn.id, product(), at=NOW)

    assert recovered.resolve(preview.id, product(), source_id="faa-aeronav",
                             mode="preview", at=NOW) == preview
    # This promotion must validate originals inside the new directory; original
    # absolute paths are deliberately unavailable after the source rename.
    recovered.promote(preview.id, product(), at=END)
    assert recovered.resolve(preview.id, product(), source_id="faa-aeronav", at=END) == preview
    with pytest.raises(StoreError) as old_expired:
        recovered.resolve(current.id, product(), source_id="faa-aeronav", at=END)
    assert old_expired.value.status_code == 410
    assert recovered.resolve(current.id, product(), source_id="faa-aeronav",
                             mode="history", at=END) == current
    expiry = END + timedelta(days=28)
    with pytest.raises(StoreError) as new_expired:
        recovered.resolve(preview.id, product(), source_id="faa-aeronav", at=expiry)
    assert new_expired.value.status_code == 410
    assert recovered.resolve(preview.id, product(), source_id="faa-aeronav",
                             mode="history", at=expiry) == preview

    recovered.revoke(preview.id, "Synthetic withdrawal after recovery")
    del recovered
    restarted = Repository(restored_dir)
    assert not restarted.snapshot()["pointers"]
    assert restarted.report(preview.id)["release"]["revoked_reason"] == (
        "Synthetic withdrawal after recovery"
    )
    with pytest.raises(StoreError) as persisted_revocation:
        restarted.resolve(preview.id, product(), source_id="faa-aeronav", mode="history", at=expiry)
    assert persisted_revocation.value.status_code == 410
