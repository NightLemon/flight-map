from datetime import UTC, datetime

import pytest
from flightmap_ingestion.pipeline import (
    IngestionContext,
    IngestionPipeline,
    PipelineError,
    PipelineStage,
    PromotionGate,
)
from flightmap_schema import (
    DatasetRelease,
    LicenseStatus,
    LocalAccessPolicy,
    QualityStatus,
    SourceProduct,
    ValidationIssue,
)

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
            "local_access": {
                "acquisition": "allowed",
                "processing": "allowed",
                "evidence": ["https://www.faa.gov/test-policy"],
                "reviewed_at": "2026-09-01T00:00:00Z",
            },
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
        validity_evidence=["https://www.faa.gov/test-validity"],
        local_access=product(license_status).local_access,
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
    restricted = product(status).model_copy(update={"local_access": LocalAccessPolicy()})
    pipeline = IngestionPipeline(context, restricted)

    with pytest.raises(PipelineError, match="permission"):
        pipeline.advance(PipelineStage.PROMOTE)

    assert context.stage is PipelineStage.QUARANTINE
    assert context.issues[-1].severity == "fatal"


def test_verified_permissive_release_can_be_promoted() -> None:
    status = LicenseStatus.PERMISSIVE
    context = IngestionContext(
        source_id="faa-aeronav",
        product_id="cifp",
        stage=PipelineStage.STAGE,
        release=release(status),
    )
    pipeline = IngestionPipeline(
        context, product(status), clock=lambda: datetime(2026, 9, 7, tzinfo=UTC)
    )

    pipeline.advance(PipelineStage.PROMOTE, lambda _: {"release_id": "candidate"})

    assert context.stage is PipelineStage.PROMOTE


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 9, 2, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    ],
)
def test_gate_rejects_future_and_expired(at):
    status = LicenseStatus.PERMISSIVE
    context = IngestionContext(source_id="faa-aeronav", product_id="cifp", release=release(status))
    with pytest.raises(PipelineError, match="interval"):
        PromotionGate.check(context, product(status), at=at)


@pytest.mark.parametrize("location", ["release", "context"])
def test_gate_checks_both_issue_lists(location):
    status = LicenseStatus.PERMISSIVE
    context = IngestionContext(source_id="faa-aeronav", product_id="cifp", release=release(status))
    issue = ValidationIssue(code="test", severity="fatal", message="Synthetic failure")
    (context.release.issues if location == "release" else context.issues).append(issue)
    with pytest.raises(PipelineError):
        PromotionGate.check(context, product(status), at=datetime(2026, 9, 7, tzinfo=UTC))


def test_gate_rejects_wrong_source_and_product():
    status = LicenseStatus.PERMISSIVE
    context = IngestionContext(source_id="wrong", product_id="cifp", release=release(status))
    with pytest.raises(PipelineError, match="identity"):
        PromotionGate.check(context, product(status))
    context.source_id, context.product_id = "faa-aeronav", "wrong"
    with pytest.raises(PipelineError, match="identity"):
        PromotionGate.check(context, product(status))


@pytest.mark.parametrize("handler", [None, lambda _: {}])
def test_stage_requires_real_output(handler):
    pipeline = IngestionPipeline(
        IngestionContext(source_id="faa-aeronav", product_id="cifp"),
        product(LicenseStatus.PERMISSIVE),
    )
    with pytest.raises(PipelineError):
        pipeline.advance(PipelineStage.DISCOVER, handler)
    assert pipeline.context.stage == PipelineStage.QUARANTINE


def test_terminal_stage_is_controlled_error():
    pipeline = IngestionPipeline(
        IngestionContext(source_id="faa-aeronav", product_id="cifp", stage=PipelineStage.PROMOTE),
        product(LicenseStatus.PERMISSIVE),
    )
    with pytest.raises(PipelineError, match="终态"):
        pipeline.advance(PipelineStage.PROMOTE)
