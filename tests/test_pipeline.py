from datetime import UTC, datetime

import pytest
from flightmap_ingestion.pipeline import (
    IngestionContext,
    IngestionPipeline,
    PipelineError,
    PipelineStage,
)
from flightmap_schema import DatasetRelease, LicenseStatus, QualityStatus, SourceProduct

SHA = "b" * 64


def product(license_status: LicenseStatus) -> SourceProduct:
    return SourceProduct.model_validate(
        {
            "id": "cifp",
            "name": "CIFP",
            "landing_page": "https://www.faa.gov/example",
            "kind": "structured-data",
            "categories": ["airways"],
            "license_status": license_status,
            "redistribution": "test policy",
        }
    )


def release(license_status: LicenseStatus) -> DatasetRelease:
    return DatasetRelease(
        id="candidate",
        source_id="faa-aeronav",
        product_id="cifp",
        airac="2609",
        valid_from=datetime(2026, 9, 3, tzinfo=UTC),
        valid_to=datetime(2026, 10, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        sha256=SHA,
        parser_version="0.1.0",
        license_status=license_status,
        quality_status=QualityStatus.VERIFIED,
    )


def test_pipeline_enforces_stage_order() -> None:
    pipeline = IngestionPipeline(
        IngestionContext(source_id="faa-aeronav", product_id="cifp"),
        product(LicenseStatus.REVIEW_REQUIRED),
    )

    with pytest.raises(PipelineError, match="非法状态转换"):
        pipeline.advance(PipelineStage.ACQUIRE)


def test_unconfirmed_license_blocks_promotion_and_quarantines() -> None:
    status = LicenseStatus.REVIEW_REQUIRED
    context = IngestionContext(
        source_id="faa-aeronav",
        product_id="cifp",
        stage=PipelineStage.STAGE,
        release=release(status),
    )
    pipeline = IngestionPipeline(context, product(status))

    with pytest.raises(PipelineError, match="不允许发布"):
        pipeline.advance(PipelineStage.PROMOTE)

    assert context.stage is PipelineStage.QUARANTINE
    assert context.issues[-1].severity == "fatal"


def test_verified_permissive_release_can_be_promoted() -> None:
    status = LicenseStatus.PERMISSIVE
    context = IngestionContext(
        source_id="test-authority",
        product_id="test-product",
        stage=PipelineStage.STAGE,
        release=release(status),
    )
    pipeline = IngestionPipeline(context, product(status))

    pipeline.advance(PipelineStage.PROMOTE)

    assert context.stage is PipelineStage.PROMOTE
