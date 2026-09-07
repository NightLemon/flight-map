"""Local build orchestration. Acquisition never promotes a release."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flightmap_schema import (
    DatasetRelease,
    ImportManifest,
    ParseResult,
    QualityStatus,
    RawAsset,
    SourceProduct,
    ValidationReport,
    airac_period_at,
)
from flightmap_storage import Repository, StoreError

from .download import AssetDownloader, verify_download
from .dtpp import dtpp_validity, parse_dtpp
from .faa import FaaDiscovery
from .nasr import nasr_effective_date, parse_nasr
from .pipeline import IngestionContext, IngestionPipeline, PipelineStage

PARSER_VERSION = "0.2.0"


class EvidenceRequired(ValueError):
    """The product was found, but an explicit human-supplied input is missing."""


def check_local_policy(product: SourceProduct) -> None:
    if not product.local_access.allows_processing:
        raise EvidenceRequired(
            f"{product.id}: local processing is {product.local_access.processing}"
        )


def load_manifest(path: Path) -> ImportManifest:
    return ImportManifest.model_validate_json(path.read_text(encoding="utf-8-sig"))


def _validate_manifest(manifest: ImportManifest, product: SourceProduct, path: Path) -> None:
    if manifest.source_id != "faa-aeronav" or manifest.product_id != product.id:
        raise ValueError("Manifest source/product identity mismatch")
    parsed_url = urlparse(manifest.source_url)
    if parsed_url.scheme != "https" or not (parsed_url.hostname or "").endswith(".faa.gov"):
        raise ValueError("FAA imports require an official HTTPS source URL")
    if manifest.parser_version != PARSER_VERSION:
        raise ValueError(f"Installed parser version is {PARSER_VERSION}")
    if product.id == "nasr":
        effective = nasr_effective_date(path)
        if manifest.valid_from.astimezone(UTC).date() != effective:
            raise ValueError("Manifest valid_from conflicts with NASR EFF_DATE")
        # Calendar is used only to check the cycle label; it never supplies product validity.
        label = airac_period_at(manifest.valid_from).identifier
        if label != manifest.airac:
            raise ValueError("Manifest AIRAC label conflicts with the effective date")
    if product.id == "dtpp":
        actual = dtpp_validity(path)
        for key in ("airac", "valid_from", "valid_to"):
            if getattr(manifest, key) != actual[key]:
                raise ValueError(f"Manifest {key} conflicts with d-TPP XML")


def _parse(path: Path, asset: RawAsset, manifest: ImportManifest) -> ParseResult:
    if manifest.product_id == "nasr":
        return parse_nasr(path, asset.sha256, manifest.valid_from.astimezone(UTC).date())
    if manifest.product_id == "dtpp":
        return parse_dtpp(path, asset.sha256)
    if manifest.product_id == "cifp":
        from .cifp import parse_cifp

        return parse_cifp(path, asset.sha256, manifest.member)
    raise ValueError(f"No parser for product: {manifest.product_id}")


def build_local(
    repository: Repository,
    product: SourceProduct,
    path: Path,
    manifest: ImportManifest,
    *,
    final_url: str | None = None,
    content_type: str = "application/octet-stream",
) -> dict:
    check_local_policy(product)
    _validate_manifest(manifest, product, path)
    context = IngestionContext(source_id=manifest.source_id, product_id=product.id)
    pipeline = IngestionPipeline(context, product)
    asset: RawAsset | None = None
    parsed: ParseResult | None = None
    status = "staged"
    runs = repository.data_dir / "runs"
    runs.mkdir(exist_ok=True)
    run_path = runs / f"{product.id}-{uuid4().hex}.json"
    try:
        pipeline.advance(PipelineStage.DISCOVER, lambda _: {"source_url": manifest.source_url})

        def acquire(_):
            nonlocal asset
            asset = repository.store_asset(
                path,
                source_id=manifest.source_id,
                product_id=product.id,
                source_url=manifest.source_url,
                retrieved_at=datetime.now(UTC),
                content_type=content_type,
                final_url=final_url,
            )
            return {"sha256": asset.sha256}

        pipeline.advance(PipelineStage.ACQUIRE, acquire)
        assert asset is not None
        stored = Path(asset.storage_uri)

        def verify(_):
            sha, _size = verify_download(stored, content_type, require_zip=product.id == "cifp")
            if sha != asset.sha256:
                raise ValueError("Stored asset hash mismatch")
            return {"sha256": sha}

        pipeline.advance(PipelineStage.VERIFY, verify)

        def parse(_):
            nonlocal parsed
            parsed = _parse(stored, asset, manifest)
            return {"parser_version": PARSER_VERSION}

        pipeline.advance(PipelineStage.PARSE, parse)
        assert parsed is not None

        def normalize(_):
            nonlocal parsed
            parsed = ParseResult.model_validate_json(parsed.model_dump_json())
            return {"record_count": str(len(parsed.records))}

        pipeline.advance(PipelineStage.NORMALIZE, normalize)

        def validate(_):
            report = ValidationReport.model_validate_json(parsed.report.model_dump_json())
            digest = hashlib.sha256(report.model_dump_json().encode()).hexdigest()
            return {"report_sha256": digest}

        pipeline.advance(PipelineStage.VALIDATE, validate)
        identity = {
            "manifest": manifest.model_dump(mode="json"),
            "sha256": asset.sha256,
            "local_access": product.local_access.model_dump(mode="json"),
        }
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        release_id = f"{product.id}-{manifest.airac}-{digest}"
        release = DatasetRelease(
            id=release_id,
            source_id=manifest.source_id,
            product_id=product.id,
            airac=manifest.airac,
            valid_from=manifest.valid_from,
            valid_to=manifest.valid_to,
            retrieved_at=asset.retrieved_at,
            sha256=asset.sha256,
            parser_version=PARSER_VERSION,
            license_status=product.license_status,
            quality_status=QualityStatus.QUARANTINED
            if parsed.report.blocking
            else QualityStatus.VERIFIED,
            issues=parsed.report.issues,
            input_sha256=[asset.sha256],
            validity_evidence=manifest.validity_evidence,
            local_access=product.local_access,
            capabilities=parsed.report.capabilities,
        )
        context.release = release
        try:
            repository.get_release(release_id)
            status = "unchanged"
        except StoreError as exc:
            if exc.status_code != 404:
                raise
        pipeline.advance(
            PipelineStage.STAGE,
            lambda _: {
                "release_id": repository.stage(release, parsed.records, parsed.report),
            },
        )
        if parsed.report.blocking:
            status = "quarantined"
        repository.record_attempt(
            product.id, status, "Candidate built; promotion is explicit", release_id
        )
        return {
            "product": product.id,
            "status": status,
            "release_id": release_id,
            "report": parsed.report.model_dump(mode="json"),
            "promotion": "not-requested",
            "run_file": str(run_path),
        }
    finally:
        run_path.write_text(context.model_dump_json(indent=2), encoding="utf-8")


def _nasr_candidate_date(url: str) -> date:
    name = urlparse(url).path.rsplit("/", 1)[-1]
    token = name.removesuffix("_APT_CSV.zip")
    return datetime.strptime(token, "%d_%b_%Y").date()


def update_product(
    repository: Repository,
    product: SourceProduct,
    *,
    manifest: ImportManifest | None = None,
    preview: bool = False,
    at: datetime | None = None,
) -> dict:
    at = at or datetime.now(UTC)
    if at.tzinfo is None:
        raise ValueError("Update clock must include timezone")
    check_local_policy(product)
    if product.local_access.acquisition != "allowed" or product.local_access.agreement_required:
        raise EvidenceRequired(f"{product.id}: official acquisition requires user action")
    candidates = FaaDiscovery().fetch(product)
    role = {"nasr": "airport-csv", "dtpp": "chart-catalog"}.get(product.id)
    assets = [c for c in candidates if c.kind == "asset" and c.role == role]
    if product.id == "nasr":
        assets = [c for c in assets if (_nasr_candidate_date(c.url) > at.date()) == preview]
        assets.sort(key=lambda c: _nasr_candidate_date(c.url), reverse=not preview)
    elif product.id == "dtpp":
        assets.sort(key=lambda c: re.search(r"/d-tpp/(\d{4})/", c.url).group(1), reverse=True)
    if not assets:
        raise ValueError("No supported official asset discovered for the requested edition")
    chosen = assets[0]
    download = AssetDownloader(repository.data_dir / "downloads").acquire(
        chosen.url,
        require_zip=product.id == "nasr",
    )
    if manifest is None and product.id == "dtpp":
        validity = dtpp_validity(download.path)
        if (validity["valid_from"] > at) != preview:
            raise ValueError(
                "Discovered d-TPP edition does not match the requested current/preview mode"
            )
        if validity["valid_to"] <= at and not preview:
            raise ValueError("Discovered d-TPP catalog has expired")
        validity["validity_evidence"].insert(0, chosen.url)
        manifest = ImportManifest(product_id="dtpp", source_url=chosen.url, **validity)
    if manifest is None:
        # Dates without a timezone/time are retained as evidence, never promoted into UTC validity.
        asset = repository.store_asset(
            download.path,
            source_id="faa-aeronav",
            product_id=product.id,
            source_url=chosen.url,
            retrieved_at=at,
            content_type=download.content_type,
            final_url=download.final_url,
        )
        parsed = parse_nasr(Path(asset.storage_uri), asset.sha256)
        report_path = repository.data_dir / f"nasr-{asset.sha256}.report.json"
        report_path.write_text(parsed.report.model_dump_json(indent=2), encoding="utf-8")
        raise EvidenceRequired(
            "NASR validity-evidence-missing: EFF_DATE establishes a date, "
            "not an exact UTC interval. "
            f"Raw asset retained at {asset.storage_uri}; parse report {report_path}. "
            "Supply a manifest backed by NASR-specific official time evidence."
        )
    if manifest.source_url != chosen.url:
        raise ValueError("Manifest source URL differs from the discovered asset")
    return build_local(
        repository,
        product,
        download.path,
        manifest,
        final_url=download.final_url,
        content_type=download.content_type,
    )
