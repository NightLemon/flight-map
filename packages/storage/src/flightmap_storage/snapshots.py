"""Immutable date-level research snapshots, never promoted into strict Current."""

from __future__ import annotations

import hashlib
import json
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
