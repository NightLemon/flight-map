"""来源、资产、发布与覆盖模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class LicenseStatus(StrEnum):
    REVIEW_REQUIRED = "review-required"
    LINK_ONLY = "link-only"
    PUBLIC_DOMAIN = "public-domain"
    PERMISSIVE = "permissive"
    AGREEMENT_APPROVED = "agreement-approved"

    @property
    def allows_redistribution(self) -> bool:
        return self in {
            LicenseStatus.PUBLIC_DOMAIN,
            LicenseStatus.PERMISSIVE,
            LicenseStatus.AGREEMENT_APPROVED,
        }


class QualityStatus(StrEnum):
    DISCOVERED = "discovered"
    QUARANTINED = "quarantined"
    VERIFIED = "verified"
    EXPIRED = "expired"


class ProductKind(StrEnum):
    STRUCTURED_DATA = "structured-data"
    CHART = "chart"
    SAFETY_NOTICE = "safety-notice"
    CATALOG = "catalog"


class DiscoveryRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_contains: list[str] = Field(default_factory=list)
    require_zip: bool = False


class SourceProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    landing_page: HttpUrl
    kind: ProductKind
    categories: list[str]
    update_cycle_days: int | None = Field(default=None, gt=0)
    formats: list[str] = Field(default_factory=list)
    license_status: LicenseStatus
    redistribution: str
    notes: str | None = None
    discovery: DiscoveryRule = Field(default_factory=DiscoveryRule)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    authority: str
    country: str
    trust_level: str = Field(pattern="^[A-D]$")
    official: bool
    products: list[SourceProduct]


class RawAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    product_id: str
    source_url: HttpUrl
    retrieved_at: datetime
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    content_type: str
    size_bytes: int = Field(gt=0)
    storage_uri: str


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str = Field(pattern="^(info|warning|error|fatal)$")
    message: str
    record_key: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class DatasetRelease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    product_id: str
    airac: str = Field(pattern="^\\d{4}$")
    valid_from: datetime
    valid_to: datetime
    retrieved_at: datetime
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    parser_version: str
    license_status: LicenseStatus
    quality_status: QualityStatus
    issues: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interval(self) -> DatasetRelease:
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None:
            raise ValueError("有效期必须包含时区")
        if self.valid_from >= self.valid_to:
            raise ValueError("valid_from 必须早于 valid_to")
        return self

    def is_current(self, at: datetime | None = None) -> bool:
        at = at or datetime.now(UTC)
        if at.tzinfo is None:
            raise ValueError("查询时间必须包含时区")
        return (
            self.quality_status is QualityStatus.VERIFIED
            and self.valid_from <= at < self.valid_to
        )


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str
    category: str
    source_id: str
    status: str
    airac: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    note: str | None = None
