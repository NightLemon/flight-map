"""SQLite repository. Immutable candidates and transactional current pointers."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from flightmap_schema import (
    DatasetRelease,
    RawAsset,
    ResearchRecord,
    SourceProduct,
    ValidationReport,
)
from flightmap_schema.publication import check_publication


class StoreError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Repository:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir = self.data_dir / "assets"
        self.assets_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "flightmap.sqlite3"
        self._migrate()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise StoreError(f"Unsupported database schema version: {version}")
            if version == 0:
                script = (Path(__file__).parent / "migrations/001_initial.sql").read_text("utf-8")
                try:
                    connection.executescript(
                        f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version=1;\nCOMMIT;"
                    )
                except Exception:
                    connection.rollback()
                    raise

    def store_asset(
        self,
        path: Path,
        *,
        source_id: str,
        product_id: str,
        source_url: str,
        retrieved_at: datetime,
        content_type: str,
        final_url: str | None = None,
    ) -> RawAsset:
        if retrieved_at.tzinfo is None:
            raise StoreError("retrieved_at must include timezone")
        digest = hashlib.sha256()
        size = 0
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.assets_dir, delete=False) as target:
                temporary = Path(target.name)
                with Path(path).open("rb") as source:
                    while block := source.read(1024 * 1024):
                        digest.update(block)
                        size += len(block)
                        target.write(block)
            if not size:
                raise StoreError("Empty asset")
            sha = digest.hexdigest()
            destination = self.assets_dir / sha
            if destination.exists():
                with destination.open("rb") as existing:
                    if hashlib.file_digest(existing, "sha256").hexdigest() != sha:
                        raise StoreError("Stored immutable asset is corrupt")
                temporary.unlink()
            else:
                os.replace(temporary, destination)
            temporary = None
            asset = RawAsset(
                source_id=source_id,
                product_id=product_id,
                source_url=source_url,
                retrieved_at=retrieved_at,
                sha256=sha,
                content_type=content_type,
                size_bytes=size,
                storage_uri=str(destination),
                final_url=final_url,
            )
            with self._connect() as connection, connection:
                connection.execute(
                    "INSERT OR IGNORE INTO assets VALUES(?,?,?)", (sha, size, str(destination))
                )
                connection.execute(
                    "INSERT INTO acquisitions(sha256,source_id,product_id,metadata) "
                    "VALUES(?,?,?,?)",
                    (sha, source_id, product_id, asset.model_dump_json()),
                )
            return asset
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def stage(
        self,
        release: DatasetRelease,
        records: list[ResearchRecord],
        report: ValidationReport,
    ) -> str:
        # Round-trip at this boundary: caller-owned mutable models cannot bypass validation.
        release = DatasetRelease.model_validate_json(release.model_dump_json())
        report = ValidationReport.model_validate_json(report.model_dump_json())
        records = [
            ResearchRecord.model_validate_json(record.model_dump_json()) for record in records
        ]
        if not release.validity_evidence:
            raise StoreError("Missing product validity evidence")
        if len({record.id for record in records}) != len(records):
            raise StoreError("Duplicate normalized record identity")
        if release.quality_status.value == "verified":
            if report.blocking or not records or not report.success_count:
                raise StoreError("A verified release requires nonempty, nonblocking parsed results")
            if any(issue.severity in {"error", "fatal"} for issue in release.issues):
                raise StoreError("A verified release cannot contain blocking issues")
        inputs = set(release.input_sha256)
        if any(record.provenance.asset_sha256 not in inputs for record in records):
            raise StoreError("Record provenance does not belong to release inputs")
        if set(release.capabilities) != set(report.capabilities):
            raise StoreError("Release capabilities must match validation report")
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for sha in inputs:
                acquired = connection.execute(
                    "SELECT 1 FROM acquisitions WHERE sha256=? AND source_id=? AND product_id=?",
                    (sha, release.source_id, release.product_id),
                ).fetchone()
                if acquired is None:
                    raise StoreError("Release input is missing or belongs to another product")
            existing = connection.execute(
                "SELECT * FROM releases WHERE id=?", (release.id,)
            ).fetchone()
            if existing:
                old = DatasetRelease.model_validate_json(existing["metadata"])
                old_records = connection.execute(
                    "SELECT metadata FROM records WHERE release_id=? ORDER BY id", (release.id,)
                ).fetchall()
                if (
                    old.model_dump(exclude={"retrieved_at"})
                    != release.model_dump(exclude={"retrieved_at"})
                    or json.loads(existing["report"]) != report.model_dump(mode="json")
                    or [json.loads(row[0]) for row in old_records]
                    != [
                        r.model_dump(mode="json") for r in sorted(records, key=lambda item: item.id)
                    ]
                ):
                    raise StoreError(
                        "Release id already exists with different immutable content", 409
                    )
                return release.id
            connection.execute(
                "INSERT INTO releases(id,source_id,product_id,metadata,report,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    release.id,
                    release.source_id,
                    release.product_id,
                    release.model_dump_json(),
                    report.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO release_assets VALUES(?,?)",
                [(release.id, sha) for sha in sorted(inputs)],
            )
            connection.executemany(
                "INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        release.id,
                        record.id,
                        record.kind,
                        record.identifier,
                        record.name,
                        record.airport_id,
                        record.airport_ident,
                        record.parent_id,
                        record.branch_id,
                        record.sequence,
                        record.model_dump_json(),
                    )
                    for record in records
                ],
            )
        return release.id

    def _release_row(self, connection: sqlite3.Connection, release_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
        if row is None:
            raise StoreError("Release not found", 404)
        return row

    def get_release(self, release_id: str) -> DatasetRelease:
        with self._connect() as connection:
            try:
                return DatasetRelease.model_validate_json(
                    self._release_row(connection, release_id)["metadata"]
                )
            except ValueError as exc:
                if isinstance(exc, StoreError):
                    raise
                raise StoreError("Stored release metadata is invalid", 403) from exc

    def _check_stored(self, connection, row):
        try:
            release = DatasetRelease.model_validate_json(row["metadata"])
            report = ValidationReport.model_validate_json(row["report"])
        except ValueError as exc:
            raise StoreError("Stored release or validation report is invalid", 403) from exc
        if (release.id, release.source_id, release.product_id) != (
            row["id"],
            row["source_id"],
            row["product_id"],
        ):
            raise StoreError("Stored release identity is inconsistent", 403)
        if report.blocking or not report.success_count:
            raise StoreError("Stored validation report blocks this release", 403)
        if set(release.capabilities) != set(report.capabilities):
            raise StoreError("Stored capabilities do not match the validation report", 403)
        if (
            connection.execute(
                "SELECT 1 FROM records WHERE release_id=? LIMIT 1", (release.id,)
            ).fetchone()
            is None
        ):
            raise StoreError("Stored release contains no records", 403)
        return release, report

    def promote(
        self,
        release_id: str,
        product: SourceProduct,
        *,
        source_id: str = "faa-aeronav",
        at: datetime | None = None,
    ) -> None:
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._release_row(connection, release_id)
            if row["revoked_reason"] is not None:
                raise StoreError("Revoked release cannot be promoted", 410)
            release, report = self._check_stored(connection, row)
            try:
                check_publication(release, product, source_id=source_id, at=at)
            except ValueError as exc:
                raise StoreError(str(exc)) from exc
            if report.blocking or not report.success_count:
                raise StoreError("Validation report does not permit promotion")
            for sha in release.input_sha256:
                asset_path = self.assets_dir / sha
                if not asset_path.is_file():
                    raise StoreError("Release input asset is missing")
                with asset_path.open("rb") as asset_file:
                    if hashlib.file_digest(asset_file, "sha256").hexdigest() != sha:
                        raise StoreError("Release input asset integrity failed")
            connection.execute(
                "INSERT INTO current_releases VALUES(?,?,?) "
                "ON CONFLICT(source_id,product_id) DO UPDATE SET release_id=excluded.release_id",
                (release.source_id, release.product_id, release.id),
            )
            connection.execute(
                "UPDATE releases SET promoted_at=? WHERE id=?",
                ((at or datetime.now(UTC)).isoformat(), release_id),
            )

    def revoke(self, release_id: str, reason: str) -> None:
        if not reason.strip():
            raise StoreError("Revocation requires a reason")
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._release_row(connection, release_id)
            connection.execute(
                "UPDATE releases SET revoked_reason=? WHERE id=?", (reason, release_id)
            )
            connection.execute("DELETE FROM current_releases WHERE release_id=?", (release_id,))

    def resolve(
        self,
        release_id: str,
        product: SourceProduct,
        *,
        source_id: str,
        mode: Literal["current", "preview", "history"] = "current",
        at: datetime | None = None,
    ) -> DatasetRelease:
        if mode not in {"current", "preview", "history"}:
            raise StoreError("Unknown release view mode")
        now = at or datetime.now(UTC)
        with self._connect() as connection:
            row = self._release_row(connection, release_id)
            release = DatasetRelease.model_validate_json(row["metadata"])
            if row["revoked_reason"] is not None:
                raise StoreError("Release has been revoked", 410)
            if now.tzinfo is None:
                raise StoreError("Query time must include timezone")
            if mode == "current" and not release.valid_from <= now < release.valid_to:
                raise StoreError("Release is outside its exact validity interval", 410)
            pointer = connection.execute(
                "SELECT release_id FROM current_releases WHERE source_id=? AND product_id=?",
                (source_id, product.id),
            ).fetchone()
            if mode == "current" and (pointer is None or pointer[0] != release_id):
                raise StoreError("Current release changed; refresh the complete view", 409)
            if mode == "preview" and release.valid_from <= now:
                raise StoreError("This release is not a future preview", 409)
            if mode == "history" and (
                release.valid_from > now
                or (pointer is not None and pointer[0] == release_id and now < release.valid_to)
                or (now < release.valid_to and row["promoted_at"] is None)
            ):
                raise StoreError("This release is not historical", 409)
            try:
                check_publication(
                    release, product, source_id=source_id, at=now, require_current=mode == "current"
                )
            except ValueError as exc:
                raise StoreError(str(exc), 403) from exc
            self._check_stored(connection, row)
            return release

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN")
            releases, storage_errors = [], []
            for row in connection.execute("SELECT * FROM releases ORDER BY created_at DESC,id"):
                try:
                    metadata = DatasetRelease.model_validate_json(row["metadata"])
                except ValueError:
                    storage_errors.append({"release_id": row["id"], "reason": "Invalid metadata"})
                    continue
                stored_error = None
                try:
                    self._check_stored(connection, row)
                except StoreError as exc:
                    stored_error = str(exc)
                try:
                    parsed_report = ValidationReport.model_validate_json(row["report"]).model_dump(
                        mode="json"
                    )
                except ValueError:
                    parsed_report = {}
                releases.append(
                    {
                        **metadata.model_dump(mode="json"),
                        "revoked_reason": row["revoked_reason"],
                        "promoted_at": row["promoted_at"],
                        "report": parsed_report,
                        "storage_error": stored_error,
                    }
                )
            pointers = {
                f"{row['source_id']}:{row['product_id']}": row["release_id"]
                for row in connection.execute("SELECT * FROM current_releases")
            }
            attempts = [
                dict(row)
                for row in connection.execute(
                    "SELECT a.* FROM attempts a JOIN (SELECT product_id,MAX(id) id FROM attempts "
                    "GROUP BY product_id) b ON a.id=b.id ORDER BY a.id DESC"
                )
            ]
            return {
                "releases": releases,
                "pointers": pointers,
                "attempts": attempts,
                "storage_errors": storage_errors,
            }

    def list_releases(self) -> list[dict[str, Any]]:
        return self.snapshot()["releases"]

    def list_records(
        self,
        release_id: str,
        *,
        kind: str | None = None,
        airport_ident: str | None = None,
        parent_id: str | None = None,
        branch_id: str | None = None,
        q: str | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[ResearchRecord]:
        clauses, params = ["release_id=?"], [release_id]
        for column, value in [
            ("kind", kind),
            ("airport_ident", airport_ident),
            ("parent_id", parent_id),
            ("branch_id", branch_id),
        ]:
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        if q is not None:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append(
                "(identifier LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' "
                "OR json_extract(metadata, '$.properties.icao_id') LIKE ? ESCAPE '\\')"
            )
            params.extend([f"%{escaped}%"] * 3)
        sql = "SELECT metadata FROM records WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sequence,id LIMIT ? OFFSET ?"
        with self._connect() as connection:
            return [
                ResearchRecord.model_validate_json(row[0])
                for row in connection.execute(
                    sql, [*params, min(max(limit, 1), 100000), max(offset, 0)]
                )
            ]

    def get_record(self, release_id: str, record_id: str) -> ResearchRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT metadata FROM records WHERE release_id=? AND id=?", (release_id, record_id)
            ).fetchone()
            if row is None:
                raise StoreError("Record not found", 404)
            return ResearchRecord.model_validate_json(row[0])

    def report(self, release_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._release_row(connection, release_id)
            previous = connection.execute(
                "SELECT id FROM releases WHERE source_id=? AND product_id=? AND id!=? "
                "AND created_at<=? ORDER BY created_at DESC,id LIMIT 1",
                (row["source_id"], row["product_id"], release_id, row["created_at"]),
            ).fetchone()
            current_records = {
                r["id"]: json.loads(r["metadata"])
                for r in connection.execute(
                    "SELECT id,metadata FROM records WHERE release_id=?", (release_id,)
                )
            }
            old_records = (
                {}
                if previous is None
                else {
                    r["id"]: json.loads(r["metadata"])
                    for r in connection.execute(
                        "SELECT id,metadata FROM records WHERE release_id=?", (previous[0],)
                    )
                }
            )

            def interpreted(record: dict[str, Any]) -> dict[str, Any]:
                return {key: value for key, value in record.items() if key != "provenance"}

            changed = sum(
                interpreted(current_records[key]) != interpreted(old_records[key])
                for key in current_records.keys() & old_records.keys()
            )
            return {
                "release": {**json.loads(row["metadata"]), "revoked_reason": row["revoked_reason"]},
                "report": json.loads(row["report"]),
                "diff": {
                    "previous_release_id": previous[0] if previous else None,
                    "added": len(current_records.keys() - old_records.keys()),
                    "removed": len(old_records.keys() - current_records.keys()),
                    "changed": changed,
                },
            }

    def record_attempt(
        self,
        product_id: str,
        status: str,
        message: str,
        release_id: str | None = None,
    ) -> None:
        with self._connect() as connection, connection:
            connection.execute(
                "INSERT INTO attempts(product_id,status,message,release_id,occurred_at) "
                "VALUES(?,?,?,?,?)",
                (product_id, status, message, release_id, datetime.now(UTC).isoformat()),
            )

    def backup(self, destination: Path) -> None:
        """Metadata snapshot; immutable originals must be copied alongside for a full backup."""
        with self._connect() as connection, sqlite3.connect(destination) as target:
            connection.backup(target)
