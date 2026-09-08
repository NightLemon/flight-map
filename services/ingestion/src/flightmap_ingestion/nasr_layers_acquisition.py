"""Same-edition NASR bundle acquisition and immutable research-2 builds."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flightmap_schema import ParseResult, ResearchSnapshot
from flightmap_storage import StoreError

from .acquisition import EvidenceRequired
from .download import AssetDownloader, verify_download
from .faa import FaaDiscovery
from .nasr import nasr_effective_date
from .research_acquisition import NASR_INTERVAL_EVIDENCE, _check_product, _clock

PARSER_VERSION = "0.3.0"
BUNDLE_ROLES = {
    "APT": "airport-csv",
    "NAV": "nav-csv",
    "FIX": "fix-csv",
    "AWY": "awy-csv",
    "AWY_POINTS": "airway-points",
    "FRQ": "frq-csv",
    "LAYOUT": "nasr-layout",
}
MONTHS = {
    name: index
    for index, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}


def source_edition(key, url):
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".faa.gov"):
        raise ValueError("NASR bundle requires official FAA HTTPS sources")
    path = parsed.path
    if key == "LAYOUT":
        if not path.lower().endswith("/layout_data.zip"):
            raise ValueError("Unexpected NASR layout asset")
        edition = re.search(r"/(20\d{2}-\d{2}-\d{2})/layout_data\.zip$", path, re.I)
        if not edition:
            raise ValueError("NASR layout source must identify its edition date")
        return date.fromisoformat(edition[1])
    if key == "AWY_POINTS":
        match = re.search(r"/(20\d{2}-\d{2}-\d{2})/AWY\.zip$", path, re.I)
        if match:
            return date.fromisoformat(match[1])
    else:
        match = re.search(rf"/(\d{{2}})_([A-Za-z]{{3}})_(20\d{{2}})_{key}_CSV\.zip$", path)
        if match and match[2].title() in MONTHS:
            return date(int(match[3]), MONTHS[match[2].title()], int(match[1]))
    raise ValueError(f"Unexpected NASR {key} source or missing edition date")


def build_research_layers_from_assets(repository, product, asset_ids, *, preview=False, at=None):
    from .nasr_layers import parse_nasr_layers

    _check_product(product)
    now = _clock(at)
    if set(asset_ids) != set(BUNDLE_ROLES):
        raise ValueError(f"NASR bundle must specify exactly {', '.join(BUNDLE_ROLES)}")
    run_path = repository.data_dir / "runs" / f"nasr-layers-{uuid4().hex}.json"
    run_path.parent.mkdir(exist_ok=True)
    run = {"product": "nasr", "mode": "research-2", "inputs": asset_ids, "stage": "verify"}
    try:
        assets, dates = {}, set()
        for key, sha in asset_ids.items():
            raw = repository.get_acquired_asset(sha, source_id="faa-aeronav", product_id="nasr")
            edition = source_edition(key, raw.source_url)
            if raw.final_url and source_edition(key, raw.final_url) != edition:
                raise ValueError("NASR redirected source conflicts with original edition")
            if edition:
                dates.add(edition)
            path = Path(raw.storage_uri)
            actual, size = verify_download(path, raw.content_type, require_zip=True)
            if actual != sha or size != raw.size_bytes:
                raise ValueError("NASR bundle input integrity mismatch")
            assets[key] = (path, sha)
        if len(dates) != 1:
            raise ValueError("NASR bundle mixes edition dates")
        effective = dates.pop()
        if nasr_effective_date(assets["APT"][0]) != effective:
            raise ValueError("NASR APT EFF_DATE conflicts with bundle edition")
        if (effective > now.date()) != preview:
            raise ValueError("NASR edition does not match research/preview mode")
        run["stage"] = "parse"
        parsed = ParseResult.model_validate_json(
            parse_nasr_layers(assets, effective).model_dump_json()
        )
        snapshot = ResearchSnapshot(
            source_id="faa-aeronav",
            product_id="nasr",
            official_effective_date=effective,
            schema_version="research-2",
            parser_version=PARSER_VERSION,
            date_evidence=[
                f"https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/{effective}",
                f"CSV EFF_DATE={effective:%Y/%m/%d}; "
                "same-edition AWY point package; date precision only",
                *[f"{key}:sha256:{sha}" for key, sha in sorted(asset_ids.items())],
            ],
            input_sha256=list(asset_ids.values()),
            local_access=product.local_access,
            capabilities=parsed.report.capabilities,
            update_interval_evidence=NASR_INTERVAL_EVIDENCE,
        )
        run["stage"] = "stage"
        exists = False
        try:
            repository.get_snapshot(snapshot.id)
            exists = True
        except StoreError as exc:
            if exc.status_code != 404:
                raise
        repository.stage_snapshot(snapshot, parsed.records, parsed.report)
        state = "quarantined" if parsed.report.blocking else "unchanged" if exists else "staged"
        repository.record_research_attempt("nasr", state, "NASR layer candidate built", snapshot.id)
        result = {
            "product": "nasr",
            "mode": "research",
            "status": state,
            "snapshot_id": snapshot.id,
            "official_effective_date": str(effective),
            "report": parsed.report.model_dump(mode="json"),
            "assets": asset_ids,
            "activation": "not-requested",
            "promotion": "not-requested",
            "run_file": str(run_path),
        }
        run.update(result)
        return result
    except Exception as exc:
        run["error"] = str(exc)
        raise
    finally:
        run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def update_research_layers(repository, product, *, preview=False, at=None):
    _check_product(product)
    now = _clock(at)
    if product.local_access.acquisition != "allowed" or product.local_access.agreement_required:
        raise EvidenceRequired("NASR acquisition requires user action")
    candidates = FaaDiscovery().fetch(product)
    airport_editions = [source_edition("APT", c.url) for c in candidates if c.role == "airport-csv"]
    applicable = sorted(d for d in airport_editions if (d > now.date()) == preview)
    if not applicable:
        raise ValueError("No NASR bundle for the requested research/preview edition")
    effective = applicable[0] if preview else applicable[-1]
    chosen = {}
    for key, role in BUNDLE_ROLES.items():
        matches = {
            c.url
            for c in candidates
            if c.role == role and source_edition(key, c.url) in {None, effective}
        }
        if len(matches) != 1:
            raise ValueError(f"Expected one official {key} asset for NASR {effective}")
        chosen[key] = matches.pop()
    asset_ids = {}
    downloader = AssetDownloader(repository.data_dir / "downloads", max_bytes=100 * 1024 * 1024)
    for key, url in chosen.items():
        downloaded = downloader.acquire(url, require_zip=True)
        if source_edition(key, downloaded.final_url or url) not in {None, effective}:
            raise ValueError("Redirected NASR asset belongs to another edition")
        raw = repository.store_asset(
            downloaded.path,
            source_id="faa-aeronav",
            product_id="nasr",
            source_url=url,
            retrieved_at=datetime.now(UTC),
            content_type=downloaded.content_type,
            final_url=downloaded.final_url,
        )
        if raw.sha256 != downloaded.sha256 or raw.size_bytes != downloaded.size_bytes:
            raise ValueError("NASR bundle asset changed during storage")
        asset_ids[key] = raw.sha256
    return build_research_layers_from_assets(
        repository, product, asset_ids, preview=preview, at=now
    )
