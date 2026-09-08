"""NASR date precision builds. Research candidates never alter exact-validity releases."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flightmap_schema import ParseResult, ResearchSnapshot, SourceProduct
from flightmap_storage import Repository, StoreError

from .acquisition import PARSER_VERSION, EvidenceRequired, _nasr_candidate_date, check_local_policy
from .download import AssetDownloader, verify_download
from .faa import FaaDiscovery
from .nasr import nasr_effective_date, parse_nasr

# The archived FAA README and its exact quote are frozen in docs/source-evidence.md.
NASR_INTERVAL_EVIDENCE = [
    "https://nfdc.faa.gov/webContent/28DaySub/2026-09-03/README.txt",
    "SHA-256 b846654fd869ff98efaba45c30a5d39f2cb7c6237c843ab2f57c64500d062546; "
    "AIRAC CYCLE PERIOD: 28 DAY CLARIFICATION: "
    "We are now issuing these products on a 28 day cycle periodicity.",
]


def _check_product(product: SourceProduct) -> None:
    if product.id != "nasr":
        raise ValueError("Date precision research currently supports only NASR airports")
    check_local_policy(product)
    if product.update_cycle_days != 28:
        raise EvidenceRequired("NASR research requires the reviewed 28 day publication evidence")


def _clock(at: datetime | None) -> datetime:
    now = at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Research clock must include timezone")
    return now.astimezone(UTC)


def build_research_from_asset(
    repository: Repository,
    product: SourceProduct,
    sha256: str,
    *,
    preview: bool = False,
    at: datetime | None = None,
    expected_effective_date: date | None = None,
) -> dict:
    """Verify and parse a previously acquired NASR ZIP without downloading or reacquiring it."""
    _check_product(product)
    now = _clock(at)
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("--asset-sha256 requires the complete lowercase SHA-256")
    runs = repository.data_dir / "runs"
    runs.mkdir(exist_ok=True)
    run_path = runs / f"nasr-research-{uuid4().hex}.json"
    run = {"product": "nasr", "mode": "research", "stage": "initial", "completed": {}}
    try:
        asset = repository.get_acquired_asset(sha256, source_id="faa-aeronav", product_id="nasr")
        source = urlparse(str(asset.source_url))
        if source.scheme != "https" or not (
            source.hostname == "faa.gov" or (source.hostname or "").endswith(".faa.gov")
        ):
            raise ValueError("NASR research requires an acquired official HTTPS source")
        run["completed"]["reuse"] = {"sha256": sha256, "source_url": str(asset.source_url)}
        run["stage"] = "reuse"
        stored = Path(asset.storage_uri)
        actual_sha, size = verify_download(stored, asset.content_type, require_zip=True)
        if actual_sha != sha256 or size != asset.size_bytes:
            raise ValueError("Acquired NASR asset integrity mismatch")
        run["completed"]["verify"] = {"sha256": actual_sha, "size_bytes": size}
        run["stage"] = "verify"
        effective = nasr_effective_date(stored)
        if expected_effective_date is not None and effective != expected_effective_date:
            raise ValueError(
                f"NASR EFF_DATE conflicts with discovered edition date; asset retained: {sha256}"
            )
        if (effective > now.date()) != preview:
            raise ValueError(
                "NASR official date does not match the requested research/preview mode"
            )
        parsed = ParseResult.model_validate_json(
            parse_nasr(stored, sha256, effective).model_dump_json()
        )
        run["completed"]["parse"] = {"parser_version": PARSER_VERSION}
        run["stage"] = "parse"
        report = parsed.report
        run["completed"]["validate"] = {
            "report_sha256": hashlib.sha256(report.model_dump_json().encode()).hexdigest(),
            "input_count": report.input_count,
            "success_count": report.success_count,
            "unsupported_count": report.unsupported_count,
            "error_count": report.error_count,
        }
        run["stage"] = "validate"
        with zipfile.ZipFile(stored) as archive:
            member = next(n for n in archive.namelist() if n.rsplit("/", 1)[-1] == "APT_BASE.csv")
        snapshot = ResearchSnapshot(
            source_id="faa-aeronav",
            product_id="nasr",
            official_effective_date=effective,
            date_evidence=[
                f"sha256:{sha256}!{member}#column=EFF_DATE",
                f"EFF_DATE={effective:%Y/%m/%d}; official date only; exact UTC interval unknown",
            ],
            input_sha256=[sha256],
            parser_version=PARSER_VERSION,
            local_access=product.local_access,
            capabilities=report.capabilities,
            update_interval_days=28,
            update_interval_evidence=NASR_INTERVAL_EVIDENCE,
        )
        status = "staged"
        try:
            repository.get_snapshot(snapshot.id)
            status = "unchanged"
        except StoreError as exc:
            if exc.status_code != 404:
                raise
        snapshot_id = repository.stage_snapshot(snapshot, parsed.records, report)
        if report.blocking:
            status = "quarantined"
        run["completed"]["stage"] = {"snapshot_id": snapshot_id}
        run["stage"] = "stage"
        repository.record_research_attempt(
            product.id, status, "Research candidate built; activation is explicit", snapshot_id
        )
        return {
            "product": product.id,
            "mode": "research",
            "status": status,
            "snapshot_id": snapshot_id,
            "official_effective_date": effective.isoformat(),
            "exact_validity_status": "unknown",
            "report": report.model_dump(mode="json"),
            "activation": "not-requested",
            "promotion": "not-requested",
            "run_file": str(run_path),
        }
    except Exception as exc:
        run["error"] = str(exc)
        raise
    finally:
        run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def update_research_product(
    repository: Repository,
    product: SourceProduct,
    *,
    preview: bool = False,
    at: datetime | None = None,
) -> dict:
    """Acquire the requested NASR edition and build an inactive research candidate."""
    _check_product(product)
    now = _clock(at)
    if product.local_access.acquisition != "allowed" or product.local_access.agreement_required:
        raise EvidenceRequired("NASR official acquisition requires user action")
    candidates = [
        candidate
        for candidate in FaaDiscovery().fetch(product)
        if candidate.kind == "asset" and candidate.role == "airport-csv"
    ]
    candidates = [
        candidate
        for candidate in candidates
        if (_nasr_candidate_date(candidate.url) > now.date()) == preview
    ]
    candidates.sort(key=lambda candidate: _nasr_candidate_date(candidate.url), reverse=not preview)
    if not candidates:
        raise ValueError("No official NASR airport asset found for the requested research edition")
    chosen = candidates[0]
    # A URL may serve a same-cycle correction. Only explicit --asset-sha256 builds skip acquisition.
    download = AssetDownloader(repository.data_dir / "downloads").acquire(
        chosen.url, require_zip=True
    )
    asset = repository.store_asset(
        download.path,
        source_id="faa-aeronav",
        product_id="nasr",
        source_url=chosen.url,
        retrieved_at=now,
        content_type=download.content_type,
        final_url=download.final_url,
    )
    if asset.sha256 != download.sha256 or asset.size_bytes != download.size_bytes:
        raise ValueError("NASR download changed between verification and storage")
    return build_research_from_asset(
        repository,
        product,
        asset.sha256,
        preview=preview,
        at=now,
        expected_effective_date=_nasr_candidate_date(chosen.url),
    )
