from datetime import UTC, datetime

from flightmap_schema import DatasetRelease, LicenseStatus, QualityStatus

SHA = "a" * 64


def make_release(**changes: object) -> DatasetRelease:
    values: dict[str, object] = {
        "id": "faa-cifp-2609",
        "source_id": "faa-aeronav",
        "product_id": "cifp",
        "airac": "2609",
        "valid_from": datetime(2026, 9, 3, tzinfo=UTC),
        "valid_to": datetime(2026, 10, 1, tzinfo=UTC),
        "retrieved_at": datetime(2026, 8, 20, tzinfo=UTC),
        "sha256": SHA,
        "parser_version": "0.1.0",
        "license_status": LicenseStatus.REVIEW_REQUIRED,
        "quality_status": QualityStatus.VERIFIED,
    }
    values.update(changes)
    return DatasetRelease.model_validate(values)


def test_release_is_current_only_inside_valid_interval() -> None:
    release = make_release()

    assert release.is_current(datetime(2026, 9, 7, tzinfo=UTC))
    assert not release.is_current(datetime(2026, 10, 1, tzinfo=UTC))


def test_quarantined_release_is_never_current() -> None:
    release = make_release(quality_status=QualityStatus.QUARANTINED)

    assert not release.is_current(datetime(2026, 9, 7, tzinfo=UTC))
