"""Immutable date-level research snapshots, never promoted into strict Current."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime

from flightmap_schema import RawAsset, ResearchRecord, ResearchSnapshot, ValidationReport

from .errors import StoreError


def _digest_records(records):
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda r: r.id):
        digest.update(json.dumps(record.model_dump(mode="json"), sort_keys=True).encode())
        digest.update(b"\n")
    return digest.hexdigest()


class SnapshotRepositoryMixin:
    def _check_snapshot(self, connection, row, product, source_id):
        try:
            item = ResearchSnapshot.model_validate_json(row["metadata"])
            report = ValidationReport.model_validate_json(row["report"])
        except ValueError as exc:
            raise StoreError("Stored snapshot metadata/report failed validation", 403) from exc
        if row["revoked_reason"] is not None:
            raise StoreError("Research snapshot has been revoked", 410)
        if (item.id, item.source_id, item.product_id) != (
            row["id"],
            row["source_id"],
            row["product_id"],
        ) or (source_id, product.id) != (item.source_id, item.product_id):
            raise StoreError("Research snapshot source/product identity mismatch", 403)
        if (source_id, product.id) != ("faa-aeronav", "nasr"):
            raise StoreError("Unsupported snapshot source/product", 403)
        if not item.local_access.allows_processing or not product.local_access.allows_processing:
            raise StoreError("Research snapshot processing permission is not allowed", 403)
        if report.blocking or not report.success_count:
            raise StoreError("Research validation report blocks reading", 403)
        if item.capabilities != ["airports"] or set(report.capabilities) != {"airports"}:
            raise StoreError("Research capabilities disagree with report", 403)
        inputs = connection.execute(
            "SELECT i.sha256,a.metadata FROM snapshot_inputs i JOIN acquisitions a "
            "ON i.acquisition_id=a.id WHERE i.snapshot_id=? ORDER BY i.sha256",
            (item.id,),
        ).fetchall()
        if [r[0] for r in inputs] != item.input_sha256:
            raise StoreError("Snapshot input set is inconsistent", 403)
        for sha, metadata in inputs:
            try:
                raw = RawAsset.model_validate_json(metadata)
                if (raw.sha256, raw.source_id, raw.product_id) != (sha, source_id, product.id):
                    raise ValueError("Acquisition identity mismatch")
                path = self.assets_dir / sha
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                        raise ValueError("Input hash mismatch")
                if path.stat().st_size != raw.size_bytes:
                    raise ValueError("Input size mismatch")
            except (ValueError, OSError) as exc:
                raise StoreError("Snapshot original input integrity failed", 403) from exc

        # Revalidate immutable records once per database/WAL revision. Raw assets above are
        # hashed on every gate, including reads, so modifying an original never hits this cache.
        def signature():
            result = []
            for path in [self.db_path, self.db_path.with_name(self.db_path.name + "-wal")]:
                try:
                    stat = path.stat()
                    result.append((stat.st_mtime_ns, stat.st_size))
                except FileNotFoundError:
                    result.append(None)
            return tuple(result)

        marker = signature()
        cache = getattr(self, "_checked_snapshot_records", {})
        key = (item.id, row["records_sha256"], report.success_count)
        if cache.get(key) != marker:
            records = []
            try:
                for stored in connection.execute(
                    "SELECT id,identifier,name,metadata FROM snapshot_records "
                    "WHERE snapshot_id=? ORDER BY id",
                    (item.id,),
                ):
                    r = ResearchRecord.model_validate_json(stored["metadata"])
                    if (r.id, r.identifier, r.name) != tuple(stored)[:3]:
                        raise ValueError("Stored record identity differs")
                    if r.kind != "airport" or r.provenance.asset_sha256 not in item.input_sha256:
                        raise ValueError("Record provenance/kind differs")
                    geometry = r.geometry or {}
                    coords = geometry.get("coordinates", [])
                    if (
                        geometry.get("type") != "Point"
                        or len(coords) != 2
                        or not all(isinstance(v, int | float) and math.isfinite(v) for v in coords)
                        or not -180 <= coords[0] <= 180
                        or not -90 <= coords[1] <= 90
                    ):
                        raise ValueError("Invalid airport coordinates")
                    records.append(r)
                if len(records) != report.success_count:
                    raise ValueError("Stored record count differs")
                if _digest_records(records) != row["records_sha256"]:
                    raise ValueError("Stored record checksum differs")
            except ValueError as exc:
                raise StoreError(f"Snapshot records failed validation: {exc}", 403) from exc
            if signature() == marker:
                self._checked_snapshot_records = {key: marker}
        return item, report

    def resolve_snapshot(
        self, snapshot_id, product, *, source_id, mode="active", at=None
    ) -> ResearchSnapshot:
        now = at or datetime.now(UTC)
        if now.tzinfo is None or mode not in {"active", "history", "preview"}:
            raise StoreError("Aware query time and valid research mode are required")
        with self._connect() as connection:
            connection.execute("BEGIN")
            row = self._snapshot_row(connection, snapshot_id)
            item, _ = self._check_snapshot(connection, row, product, source_id)
            pointer = connection.execute(
                "SELECT snapshot_id FROM active_snapshots WHERE source_id=? AND product_id=?",
                (source_id, product.id),
            ).fetchone()
            future = item.official_effective_date > now.astimezone(UTC).date()
            if mode == "active" and (pointer is None or pointer[0] != snapshot_id):
                raise StoreError("Active research snapshot changed; refresh the complete view", 409)
            if mode == "active" and future:
                raise StoreError("Future snapshot requires explicit preview", 409)
            if mode == "preview" and not future:
                raise StoreError("Snapshot is not a future preview", 409)
            if mode == "history" and (future or (pointer and pointer[0] == snapshot_id)):
                raise StoreError("Select a non-active, non-future research snapshot", 409)
            return item

    def get_acquired_asset(self, sha, *, source_id, product_id) -> RawAsset:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT metadata FROM acquisitions WHERE sha256=? AND source_id=? "
                "AND product_id=? ORDER BY id LIMIT 1",
                (sha, source_id, product_id),
            ).fetchone()
            if row is None:
                raise StoreError("Registered input not found for this source/product", 404)
            raw = RawAsset.model_validate_json(row[0])
            if (raw.source_id, raw.product_id, raw.sha256) != (source_id, product_id, sha):
                raise StoreError("Acquisition identity is inconsistent", 403)
            return raw

    def _snapshot_row(self, connection, snapshot_id):
        row = connection.execute(
            "SELECT * FROM research_snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise StoreError("Research snapshot not found", 404)
        return row

    def get_snapshot(self, snapshot_id) -> ResearchSnapshot:
        with self._connect() as connection:
            row = self._snapshot_row(connection, snapshot_id)
            try:
                return ResearchSnapshot.model_validate_json(row["metadata"])
            except ValueError as exc:
                raise StoreError("Invalid snapshot metadata", 403) from exc

    def stage_snapshot(self, snapshot, records, report) -> str:
        snapshot = ResearchSnapshot.model_validate_json(snapshot.model_dump_json())
        report = ValidationReport.model_validate_json(report.model_dump_json())
        records = [ResearchRecord.model_validate_json(r.model_dump_json()) for r in records]
        if len(records) != report.success_count or len({r.id for r in records}) != len(records):
            raise StoreError("Snapshot record identities/counts disagree with report")
        if snapshot.source_id != "faa-aeronav" or snapshot.product_id != "nasr":
            raise StoreError("Only FAA NASR airport research snapshots are supported")
        if snapshot.capabilities != ["airports"] or set(report.capabilities) != {"airports"}:
            raise StoreError("Snapshot/report capabilities must be NASR airports")
        for record in records:
            if (
                record.kind != "airport"
                or record.provenance.asset_sha256 not in snapshot.input_sha256
            ):
                raise StoreError("Snapshot record kind or input provenance is inconsistent")
        digest = _digest_records(records)
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            inputs = []
            for sha in snapshot.input_sha256:
                row = connection.execute(
                    "SELECT id FROM acquisitions WHERE sha256=? AND source_id=? AND product_id=? "
                    "ORDER BY id LIMIT 1",
                    (sha, snapshot.source_id, snapshot.product_id),
                ).fetchone()
                if row is None:
                    raise StoreError("Snapshot input missing or belongs to another source/product")
                inputs.append((snapshot.id, sha, row[0]))
            old = connection.execute(
                "SELECT * FROM research_snapshots WHERE id=?",
                (snapshot.id,),
            ).fetchone()
            if old:
                if (
                    json.loads(old["metadata"]) != snapshot.model_dump(mode="json")
                    or json.loads(old["report"]) != report.model_dump(mode="json")
                    or old["records_sha256"] != digest
                ):
                    raise StoreError("Snapshot ID already has different immutable content", 409)
                return snapshot.id
            connection.execute(
                "INSERT INTO research_snapshots "
                "(id,source_id,product_id,metadata,report,created_at,records_sha256) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    snapshot.id,
                    snapshot.source_id,
                    snapshot.product_id,
                    snapshot.model_dump_json(),
                    report.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                    digest,
                ),
            )
            connection.executemany("INSERT INTO snapshot_inputs VALUES(?,?,?)", inputs)
            connection.executemany(
                "INSERT INTO snapshot_records VALUES(?,?,?,?,?)",
                [(snapshot.id, r.id, r.identifier, r.name, r.model_dump_json()) for r in records],
            )
        return snapshot.id

    def list_snapshot_records(self, snapshot_id, *, q=None, limit=100000, offset=0):
        params = [snapshot_id]
        sql = "SELECT metadata FROM snapshot_records WHERE snapshot_id=?"
        if q is not None:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += (
                " AND (identifier LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR "
                "json_extract(metadata, '$.properties.icao_id') LIKE ? ESCAPE '\\')"
            )
            params.extend([f"%{escaped}%"] * 3)
        sql += " ORDER BY id LIMIT ? OFFSET ?"
        with self._connect() as connection:
            try:
                return [
                    ResearchRecord.model_validate_json(row[0])
                    for row in connection.execute(
                        sql,
                        [*params, min(max(limit, 1), 100000), max(0, offset)],
                    )
                ]
            except ValueError as exc:
                raise StoreError("Invalid stored research record", 403) from exc

    def snapshot_report(self, snapshot_id):
        with self._connect() as connection:
            row = self._snapshot_row(connection, snapshot_id)
            inputs = [
                json.loads(raw[0])
                for raw in connection.execute(
                    "SELECT a.metadata FROM snapshot_inputs i JOIN acquisitions a "
                    "ON a.id=i.acquisition_id WHERE i.snapshot_id=? ORDER BY i.sha256",
                    (snapshot_id,),
                )
            ]
            return {
                "snapshot": {
                    **json.loads(row["metadata"]),
                    "revoked_reason": row["revoked_reason"],
                },
                "report": json.loads(row["report"]),
                "inputs": inputs,
            }

    def record_research_attempt(self, product_id, status, message, snapshot_id=None):
        with self._connect() as connection, connection:
            connection.execute(
                "INSERT INTO research_attempts(product_id,status,message,snapshot_id,occurred_at) "
                "VALUES(?,?,?,?,?)",
                (product_id, status, message, snapshot_id, datetime.now(UTC).isoformat()),
            )
