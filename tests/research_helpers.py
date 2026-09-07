"""Synthetic test-only records, isolated from the normal data directory."""

from datetime import UTC, datetime
from pathlib import Path

from flightmap_schema import (
    DatasetRelease,
    LocalAccessPolicy,
    Provenance,
    RawAsset,
    ResearchRecord,
    SourceProduct,
    ValidationReport,
)
from flightmap_storage import Repository

START = datetime(2026, 9, 3, 9, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, 9, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 7, tzinfo=UTC)


def product(product_id="nasr") -> SourceProduct:
    return SourceProduct(
        id=product_id,
        name="Synthetic test product",
        landing_page="https://www.faa.gov/test-fixture/",
        kind="structured-data",
        categories=["airports"],
        license_status="review-required",
        redistribution="Not reviewed for redistribution",
        local_access=LocalAccessPolicy(
            acquisition="allowed",
            processing="allowed",
            evidence=["https://www.faa.gov/test-fixture/"],
            reviewed_at=NOW,
        ),
    )


def asset(repo: Repository, tmp_path: Path, product_id="nasr") -> RawAsset:
    path = tmp_path / "synthetic.txt"
    path.write_text("SYNTHETIC TEST ONLY", encoding="utf-8")
    return repo.store_asset(
        path,
        source_id="faa-aeronav",
        product_id=product_id,
        source_url="https://www.faa.gov/test-fixture/asset.txt",
        retrieved_at=NOW,
        content_type="text/plain",
    )


def candidate(asset: RawAsset, release_id="test-r1", **changes) -> DatasetRelease:
    values = dict(
        id=release_id,
        source_id="faa-aeronav",
        product_id=asset.product_id,
        airac="2609",
        valid_from=START,
        valid_to=END,
        retrieved_at=NOW,
        sha256=asset.sha256,
        parser_version="test-only",
        license_status="review-required",
        quality_status="verified",
        local_access=product().local_access,
        validity_evidence=["https://www.faa.gov/test-fixture/validity"],
        capabilities=["airports"],
    )
    values.update(changes)
    return DatasetRelease(**values)


def airport(asset: RawAsset, identifier="TEST") -> ResearchRecord:
    return ResearchRecord(
        id=f"test:airport:{identifier}",
        kind="airport",
        name=f"Synthetic airport {identifier}",
        identifier=identifier,
        airport_ident=identifier,
        geometry={"type": "Point", "coordinates": [-100.0, 40.0]},
        properties={"icao_id": "", "fixture": True},
        provenance=Provenance(asset_sha256=asset.sha256, line=1, locator="synthetic:line:1"),
    )


def report(count=1, **changes) -> ValidationReport:
    return ValidationReport(
        **{
            "input_count": count,
            "success_count": count,
            "unsupported_count": 0,
            "error_count": 0,
            "capabilities": ["airports"],
            **changes,
        }
    )
