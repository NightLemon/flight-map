"""R21 offline audit against a temporary copy of the frozen real NASR/d-TPP corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import sleep
from unittest.mock import patch

from flightmap_ingestion import research_acquisition
from flightmap_schema import load_sources
from flightmap_storage import Repository, StoreError

NASR_SHA = "d5e4c999d4c96ab4d66d8ce9a387de8ea59b5226a6144ea1ba58758ff29bbbd9"
STRICT_TABLES = ("releases", "release_assets", "current_releases", "records", "attempts")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def read_database(directory: Path):
    connection = sqlite3.connect((directory / "flightmap.sqlite3").as_uri() + "?mode=ro", uri=True)
    try:
        yield connection
    finally:
        connection.close()


def database_fingerprint(directory: Path, tables: tuple[str, ...] | None = None) -> str:
    digest = hashlib.sha256()
    with read_database(directory) as connection:
        connection.execute("BEGIN")
        names = tables or tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        )
        for table in names:
            require(bool(re.fullmatch(r"[a-z_]+", table)), "Unexpected database table name")
            digest.update(table.encode())
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode())
                digest.update(b"\n")
    return digest.hexdigest()


def acquisition_count(directory: Path) -> int:
    with read_database(directory) as connection:
        return connection.execute("SELECT COUNT(*) FROM acquisitions").fetchone()[0]


def remove_temporary_data_copy(target: Path, source: Path, work_root: Path) -> None:
    # Only remove this verified, unique audit child; never a source or user-supplied directory.
    target_path = target
    source = source.resolve()
    work_root = work_root.resolve()
    for attempt in range(4):
        resolved_target = target_path.resolve()
        require(
            resolved_target.parent == work_root and resolved_target.name.startswith("audit-"),
            "Unsafe cleanup",
        )
        require(
            resolved_target != source and not source.is_relative_to(resolved_target),
            "Cannot remove live data",
        )
        try:
            shutil.rmtree(resolved_target)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (32, 33) or attempt == 3:
                raise
            sleep((0.1, 0.2, 0.4)[attempt])


@contextmanager
def temporary_data_copy(source: Path, work_root: Path):
    require(not work_root.is_relative_to(source), "Audit workspace cannot be inside live data")
    work_root.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="audit-", dir=work_root)).resolve()
    require(target.parent == work_root and target.name.startswith("audit-"), "Unsafe audit path")
    try:
        # SQLite backup produces a consistent copy even while the read-only API remains running.
        with (
            read_database(source) as original,
            closing(sqlite3.connect(target / "flightmap.sqlite3")) as copy,
        ):
            original.backup(copy)
        assets = target / "assets"
        assets.mkdir()
        with read_database(target) as connection:
            hashes = [row[0] for row in connection.execute("SELECT sha256 FROM assets")]
        for digest in hashes:
            require(bool(re.fullmatch(r"[a-f0-9]{64}", digest)), "Invalid registered asset SHA")
            shutil.copy2(source / "assets" / digest, assets / digest)
            require(sha256(assets / digest) == digest, "Copied original failed its registered hash")
        yield target
    finally:
        remove_temporary_data_copy(target, source, work_root)


def expect_store_error(status: int, operation) -> None:
    try:
        operation()
    except StoreError as exc:
        require(exc.status_code == status, f"Expected {status}, received {exc.status_code}: {exc}")
    else:
        raise AssertionError(f"Expected repository error {status}")


def audit_copy(directory: Path, registry: Path, record) -> None:
    policies = {
        (source.id, product.id): product
        for source in load_sources(registry)
        for product in source.products
    }
    nasr = policies[("faa-aeronav", "nasr")]
    dtpp = policies[("faa-aeronav", "dtpp")]
    repository = Repository(directory)
    raw = repository.get_acquired_asset(NASR_SHA, source_id="faa-aeronav", product_id="nasr")
    copied_original = directory / "assets" / NASR_SHA
    require(
        Path(raw.storage_uri).resolve() == copied_original, "Restored asset points outside copy"
    )
    before_acquisitions = acquisition_count(directory)
    strict_before = database_fingerprint(directory, STRICT_TABLES)
    pointers = repository.snapshot()["pointers"]
    strict_id = pointers.get("faa-aeronav:dtpp")
    require(strict_id is not None, "The frozen d-TPP Current release is required for this audit")
    strict_release = repository.get_release(strict_id)
    now = datetime(2026, 9, 8, 12, tzinfo=UTC)

    def resolve(identifier, *, mode="active", at=now):
        return repository.resolve_snapshot(
            identifier, nasr, source_id="faa-aeronav", mode=mode, at=at
        )

    first = research_acquisition.build_research_from_asset(repository, nasr, NASR_SHA, at=now)
    second = research_acquisition.build_research_from_asset(repository, nasr, NASR_SHA, at=now)
    snapshot_id = first["snapshot_id"]
    require(second["status"] == "unchanged", "Repeated cached build was not unchanged")
    require(second["snapshot_id"] == snapshot_id, "Repeated cached build changed snapshot identity")
    require(
        acquisition_count(directory) == before_acquisitions, "Cached build recorded acquisition"
    )
    require(first["report"]["input_count"] == 19411, "Frozen NASR input count changed")
    require(first["report"]["success_count"] == 19411, "Frozen NASR success count changed")
    require(
        first["report"]["unsupported_count"] == first["report"]["error_count"] == 0,
        "Frozen NASR report no longer passes",
    )
    record(
        "cached-repeat",
        snapshot_id=snapshot_id,
        initial_status=first["status"],
        repeated_status=second["status"],
        inputs=19411,
        acquisitions=before_acquisitions,
    )

    repository = Repository(directory)
    snapshot = repository.get_snapshot(snapshot_id)
    require(snapshot.official_effective_date == date(2026, 9, 3), "Frozen official date changed")
    require(snapshot.exact_validity_status == "unknown", "Research invented exact validity")
    repository.activate_snapshot(snapshot_id, nasr, at=now)
    require(resolve(snapshot_id).id == snapshot_id, "Reopened snapshot cannot be selected")
    record("reopen", snapshot_id=snapshot_id)

    # These are UTC calendar classification boundaries, never product validity timestamps.
    date_boundary = datetime.combine(snapshot.official_effective_date, time.min, tzinfo=UTC)
    before_date = date_boundary - timedelta(seconds=1)
    preview = research_acquisition.build_research_from_asset(
        repository, nasr, NASR_SHA, preview=True, at=before_date
    )
    require(preview["snapshot_id"] == snapshot_id, "Preview classification changed identity")
    require(
        resolve(snapshot_id, mode="preview", at=before_date).id == snapshot_id,
        "Explicit future preview was rejected",
    )
    expect_store_error(409, lambda: repository.activate_snapshot(snapshot_id, nasr, at=before_date))
    expect_store_error(409, lambda: resolve(snapshot_id, at=before_date))
    status = repository.research_status(policies, at=before_date)
    item = next(s for s in status["snapshots"] if s["id"] == snapshot_id)
    require(item["state"] == "preview" and item["date_status"] == "future", "Preview mislabeled")
    record("future-preview", at=before_date.isoformat(), activation_error=409)

    repository.activate_snapshot(snapshot_id, nasr, at=date_boundary)
    require(resolve(snapshot_id, at=date_boundary).id == snapshot_id, "Date transition failed")
    expect_store_error(409, lambda: resolve(snapshot_id, mode="preview", at=date_boundary))
    expect_store_error(
        410, lambda: repository.resolve(strict_id, dtpp, source_id="faa-aeronav", at=date_boundary)
    )
    record(
        "date-transition",
        classification_at=date_boundary.isoformat(),
        exact_validity_status="unknown",
        strict_dtpp_before_0901_error=410,
    )

    update_due = date_boundary + timedelta(days=28)
    status = repository.research_status(policies, at=update_due)
    require(status["active_snapshots"]["nasr"]["date_status"] == "update-due", "Missing reminder")
    require(
        resolve(snapshot_id, at=update_due).id == snapshot_id, "Research reminder blocked viewing"
    )
    record("scheduled-update-reminder", at=update_due.isoformat(), remains_researchable=True)

    # Simulate a corrected parser build, retaining every official byte and normalized record.
    # This tests version switching, not an assertion that FAA issued a corrected source ZIP.
    with patch.object(
        research_acquisition, "PARSER_VERSION", snapshot.parser_version + "+r21-audit"
    ):
        correction = research_acquisition.build_research_from_asset(
            repository, nasr, NASR_SHA, at=now
        )
    correction_id = correction["snapshot_id"]
    require(
        correction_id != snapshot_id, "Parser version change did not create independent identity"
    )
    require(resolve(snapshot_id).id == snapshot_id, "Candidate build silently switched selection")
    repository.activate_snapshot(correction_id, nasr, at=now)
    expect_store_error(409, lambda: resolve(snapshot_id))
    require(
        resolve(snapshot_id, mode="history").id == snapshot_id, "Old version cannot be selected"
    )
    repository = Repository(directory)
    require(resolve(correction_id).id == correction_id, "Switched pointer did not survive reopen")
    record(
        "correction-switch",
        replacement_snapshot_id=correction_id,
        old_active_error=409,
        simulation="parser-version rebuild; official original unchanged",
    )

    repository.revoke_snapshot(correction_id, "R21 temporary-copy lifecycle audit")
    repository = Repository(directory)
    expect_store_error(410, lambda: resolve(correction_id))
    expect_store_error(410, lambda: resolve(correction_id, mode="history"))
    expect_store_error(409, lambda: resolve(snapshot_id))
    require(
        repository.research_status(policies, at=now)["active_snapshots"] == {},
        "Revocation selected a replacement automatically",
    )
    record("revoke-restart", revoked_error=410, fallback_error=409)

    repository.activate_snapshot(snapshot_id, nasr, at=now)
    require(
        copied_original.resolve().is_relative_to(directory), "Refusing to corrupt live original"
    )
    with copied_original.open("r+b") as stream:
        stream.write(b"X")
    expect_store_error(403, lambda: resolve(snapshot_id))
    expect_store_error(403, lambda: repository.activate_snapshot(snapshot_id, nasr, at=now))
    try:
        research_acquisition.build_research_from_asset(repository, nasr, NASR_SHA, at=now)
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError("Corrupt copied original was rebuilt")
    record("corrupt-original", reading_error=403, activation_error=403, rebuild_rejected=True)

    require(
        database_fingerprint(directory, STRICT_TABLES) == strict_before,
        "Research lifecycle modified strict release tables",
    )
    require(acquisition_count(directory) == before_acquisitions, "Audit added acquisition events")
    require(repository.snapshot()["pointers"] == pointers, "Research lifecycle changed Current")
    repository.resolve(
        strict_id,
        dtpp,
        source_id="faa-aeronav",
        at=strict_release.valid_from + timedelta(seconds=1),
    )
    record(
        "strict-current-preserved", dtpp_release_id=strict_id, acquisition_count=before_acquisitions
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-data-dir", type=Path, default=Path("data"))
    parser.add_argument("--registry", type=Path, default=Path("sources/us/faa.yml"))
    parser.add_argument("--work-root", type=Path, default=Path(".cache/research-lifecycle"))
    parser.add_argument(
        "--output", type=Path, default=Path(".cache/research-lifecycle-report.json")
    )
    options = parser.parse_args()
    source = options.source_data_dir.resolve()
    work_root = options.work_root.resolve()
    output = options.output.resolve()
    require(not output.is_relative_to(source), "Audit report cannot be written inside live data")
    result = {
        "status": "running",
        "source_data_dir": str(source),
        "source_sha256": NASR_SHA,
        "started_at": datetime.now(UTC).isoformat(),
        "checks": [],
    }

    def record(name, **details):
        item = {"check": name, "status": "passed", **details}
        result["checks"].append(item)
        print(json.dumps(item), flush=True)

    try:
        original_fingerprint = database_fingerprint(source)
        require(sha256(source / "assets" / NASR_SHA) == NASR_SHA, "Source NASR hash mismatch")
        try:
            with (
                temporary_data_copy(source, work_root) as directory,
                patch.object(
                    research_acquisition.FaaDiscovery,
                    "fetch",
                    side_effect=AssertionError("Offline audit attempted discovery"),
                ),
                patch.object(
                    research_acquisition.AssetDownloader,
                    "acquire",
                    side_effect=AssertionError("Offline audit attempted download"),
                ),
            ):
                audit_copy(directory, options.registry.resolve(), record)
            result["temporary_copy_removed"] = True
        finally:
            require(database_fingerprint(source) == original_fingerprint, "Live database changed")
            require(sha256(source / "assets" / NASR_SHA) == NASR_SHA, "Live original changed")
            record("source-unchanged", live_database_equal=True, original_hash_equal=True)
        result["status"] = "passed"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["completed_at"] = datetime.now(UTC).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"status": result["status"], "report": str(output), "error": result.get("error")},
        ),
        flush=True,
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
