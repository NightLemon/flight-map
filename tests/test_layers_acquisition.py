import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from flightmap_ingestion.download import AssetVerificationError
from flightmap_ingestion.faa import FaaDiscovery
from flightmap_ingestion.nasr_layers_acquisition import (
    BUNDLE_ROLES,
    build_research_layers_from_assets,
    source_edition,
    update_research_layers,
)
from flightmap_schema import load_sources
from flightmap_storage import Repository
from test_nasr_layers import _bundle
from test_nasr_layers import source as source

NOW = datetime(2026, 9, 8, tzinfo=UTC)
BASE = "https://nfdc.faa.gov/webContent/28DaySub/"


def product():
    return next(p for s in load_sources("sources/us/faa.yml") for p in s.products if p.id == "nasr")


def urls(day="03_Sep_2026", iso="2026-09-03"):
    return {
        key: BASE
        + (
            f"{iso}/AWY.zip"
            if key == "AWY_POINTS"
            else f"{iso}/layout_data.zip"
            if key == "LAYOUT"
            else f"extra/{day}_{key}_CSV.zip"
        )
        for key in BUNDLE_ROLES
    }


def registered(tmp_path, source):
    repo = Repository(tmp_path / "data")
    bundle = _bundle(tmp_path, source)
    layout = tmp_path / "layout.zip"
    with zipfile.ZipFile(layout, "w") as archive:
        archive.writestr("synthetic-layout.txt", "SYNTHETIC ONLY")
    bundle["LAYOUT"] = layout, ""
    ids = {
        key: repo.store_asset(
            path,
            source_id="faa-aeronav",
            product_id="nasr",
            source_url=urls()[key],
            retrieved_at=NOW,
            content_type="application/zip",
        ).sha256
        for key, (path, _) in bundle.items()
    }
    return repo, ids


def test_bundle_build_preserves_old_current_and_is_immutable(tmp_path, source):
    repo, ids = registered(tmp_path, source)
    first = build_research_layers_from_assets(repo, product(), ids, at=NOW)
    second = build_research_layers_from_assets(repo, product(), ids, at=NOW)
    assert first["status"] == "staged"
    assert second["status"] == "unchanged"
    assert first["snapshot_id"] == second["snapshot_id"]
    snapshot = repo.get_snapshot(first["snapshot_id"])
    assert snapshot.schema_version == "research-2"
    assert set(snapshot.capabilities) == {
        "airports",
        "runways",
        "navaids",
        "waypoints",
        "airways",
        "communications",
    }
    assert len(snapshot.input_sha256) == 7
    assert repo.snapshot()["pointers"] == {}
    assert (
        repo.research_status({("faa-aeronav", "nasr"): product()}, at=NOW)["active_snapshots"] == {}
    )
    assert json.loads(Path(first["run_file"]).read_text(encoding="utf-8"))["stage"] == "stage"


def test_corrupt_bundle_and_missing_member_rejected(tmp_path, source):
    repo, ids = registered(tmp_path, source)
    with pytest.raises(ValueError, match="exactly"):
        build_research_layers_from_assets(repo, product(), {"APT": ids["APT"]}, at=NOW)
    (repo.assets_dir / ids["NAV"]).write_bytes(b"broken")
    with pytest.raises(AssetVerificationError):
        build_research_layers_from_assets(repo, product(), ids, at=NOW)
    assert repo.research_status({("faa-aeronav", "nasr"): product()}, at=NOW)["snapshots"] == []


def test_discovery_selects_layout_from_same_edition_before_downloading(tmp_path, monkeypatch):
    editions = [urls(), urls("01_Oct_2026", "2026-10-01")]
    html = "".join(
        f'<a href="{url}">FAA asset</a>' for edition in editions for url in edition.values()
    )
    candidates = FaaDiscovery().discover_html(product(), html)
    assert len(candidates) == 14
    monkeypatch.setattr(FaaDiscovery, "fetch", lambda *_: candidates)
    observed = []
    from flightmap_ingestion.download import AssetDownloader

    def acquire(_self, url, **_kwargs):
        observed.append(url)
        raise RuntimeError("stop before network")

    monkeypatch.setattr(AssetDownloader, "acquire", acquire)
    with pytest.raises(RuntimeError, match="stop before network"):
        update_research_layers(Repository(tmp_path), product(), at=NOW)
    assert observed == [urls()["APT"]]


@pytest.mark.parametrize("key", list(BUNDLE_ROLES))
def test_official_urls_pin_the_bundle_edition(key):
    assert source_edition(key, urls()[key]) == date(2026, 9, 3)
    with pytest.raises(ValueError, match="official"):
        source_edition(key, urls()[key].replace("nfdc.faa.gov", "faa.gov.evil.example"))
