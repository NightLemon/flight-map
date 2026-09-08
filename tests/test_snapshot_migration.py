import sqlite3
from pathlib import Path

import flightmap_storage.repository as storage_module
from flightmap_storage import Repository
from research_helpers import NOW, airport, asset, candidate, product, report


def test_upgrade_preserves_existing_release_assets_records_and_current(tmp_path):
    class LegacyRepository(Repository):
        def _migrate(self):
            script = (
                Path(storage_module.__file__).parent / "migrations/001_initial.sql"
            ).read_text("utf-8")
            with self._connect() as connection:
                connection.executescript(script + "\nPRAGMA user_version=1;")

    old = LegacyRepository(tmp_path / "store")
    raw = asset(old, tmp_path, "dtpp")
    release = candidate(raw)
    old.stage(release, [airport(raw)], report())
    old.promote(release.id, product("dtpp"), at=NOW)
    tables = ["assets", "acquisitions", "releases", "release_assets", "records", "current_releases"]
    with sqlite3.connect(old.db_path) as connection:
        before = {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    migrated = Repository(old.data_dir)
    Repository(old.data_dir)
    with sqlite3.connect(migrated.db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert before == {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
        assert connection.execute("SELECT COUNT(*) FROM active_snapshots").fetchone()[0] == 0
    assert migrated.resolve(release.id, product("dtpp"), source_id="faa-aeronav", at=NOW) == release
    assert (migrated.assets_dir / raw.sha256).read_bytes() == b"SYNTHETIC TEST ONLY"
