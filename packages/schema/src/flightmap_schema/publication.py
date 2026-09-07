"""Shared publication checks used at both write and read boundaries."""

from datetime import UTC, datetime
from typing import Literal

from .models import DatasetRelease, SourceProduct


def check_publication(
    release: DatasetRelease,
    product: SourceProduct,
    *,
    source_id: str,
    at: datetime | None = None,
    audience: Literal["local", "redistribution"] = "local",
    require_current: bool = True,
) -> None:
    if audience not in {"local", "redistribution"}:
        raise ValueError("Unknown publication audience")
    now = at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Query time must include timezone")
    if release.product_id != product.id or release.source_id != source_id:
        raise ValueError("Release source/product identity mismatch")
    if release.license_status != product.license_status:
        raise ValueError("Release license no longer matches source policy")
    if audience == "local":
        if not product.local_access.allows_processing or not release.local_access.allows_processing:
            raise ValueError("Local processing permission is not established")
    elif not product.license_status.allows_redistribution:
        raise ValueError("许可不允许发布数据用于再分发")
    if release.quality_status.value != "verified":
        raise ValueError("Only verified releases can be read or promoted")
    if not release.validity_evidence:
        raise ValueError("Product validity evidence is required")
    if any(issue.severity in {"error", "fatal"} for issue in release.issues):
        raise ValueError("Release has blocking validation issues")
    if require_current and not release.valid_from <= now < release.valid_to:
        raise ValueError("Release is outside its exact validity interval")
