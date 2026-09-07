CREATE TABLE assets (
  sha256 TEXT PRIMARY KEY, size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
  storage_uri TEXT NOT NULL
);
CREATE TABLE acquisitions (
  id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL REFERENCES assets(sha256),
  source_id TEXT NOT NULL, product_id TEXT NOT NULL, metadata TEXT NOT NULL
);
CREATE TABLE releases (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL, product_id TEXT NOT NULL,
  metadata TEXT NOT NULL, report TEXT NOT NULL, created_at TEXT NOT NULL,
  revoked_reason TEXT, promoted_at TEXT
);
CREATE TABLE release_assets (
  release_id TEXT NOT NULL REFERENCES releases(id), sha256 TEXT NOT NULL REFERENCES assets(sha256),
  PRIMARY KEY(release_id, sha256)
);
CREATE TABLE current_releases (
  source_id TEXT NOT NULL, product_id TEXT NOT NULL, release_id TEXT NOT NULL REFERENCES releases(id),
  PRIMARY KEY(source_id, product_id)
);
CREATE TABLE records (
  release_id TEXT NOT NULL REFERENCES releases(id), id TEXT NOT NULL, kind TEXT NOT NULL,
  identifier TEXT NOT NULL, name TEXT NOT NULL, airport_id TEXT, airport_ident TEXT,
  parent_id TEXT, branch_id TEXT, sequence INTEGER, metadata TEXT NOT NULL,
  PRIMARY KEY(release_id, id)
);
CREATE INDEX records_kind ON records(release_id, kind);
CREATE INDEX records_airport ON records(release_id, airport_ident, kind);
CREATE INDEX records_parent ON records(release_id, parent_id, branch_id);
CREATE TABLE attempts (
  id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, status TEXT NOT NULL,
  message TEXT NOT NULL, release_id TEXT, occurred_at TEXT NOT NULL
);
