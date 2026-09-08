CREATE TABLE research_snapshots (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL, product_id TEXT NOT NULL,
  metadata TEXT NOT NULL, report TEXT NOT NULL, created_at TEXT NOT NULL,
  records_sha256 TEXT NOT NULL, activated_at TEXT, revoked_reason TEXT
);
CREATE TABLE snapshot_inputs (
  snapshot_id TEXT NOT NULL REFERENCES research_snapshots(id),
  sha256 TEXT NOT NULL REFERENCES assets(sha256),
  acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
  PRIMARY KEY(snapshot_id, sha256)
);
CREATE TABLE snapshot_records (
  snapshot_id TEXT NOT NULL REFERENCES research_snapshots(id), id TEXT NOT NULL,
  identifier TEXT NOT NULL, name TEXT NOT NULL, metadata TEXT NOT NULL,
  PRIMARY KEY(snapshot_id, id)
);
CREATE INDEX snapshot_records_ident ON snapshot_records(snapshot_id, identifier);
CREATE TABLE active_snapshots (
  source_id TEXT NOT NULL, product_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL REFERENCES research_snapshots(id),
  PRIMARY KEY(source_id, product_id)
);
CREATE TABLE research_attempts (
  id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, status TEXT NOT NULL,
  message TEXT NOT NULL, snapshot_id TEXT, occurred_at TEXT NOT NULL
);
