"""来源、资产、发布与覆盖模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .research import LocalAccessPolicy


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

    id: str = Field(pattern="^[a-z0-9-]+$")
    name: str = Field(min_length=1)
    landing_page: HttpUrl
    kind: ProductKind
    categories: list[str]
    update_cycle_days: int | None = Field(default=None, gt=0)
    formats: list[str] = Field(default_factory=list)
    license_status: LicenseStatus
    redistribution: str
    notes: str | None = None
    discovery: DiscoveryRule = Field(default_factory=DiscoveryRule)
    local_access: LocalAccessPolicy = Field(default_factory=LocalAccessPolicy)

    @model_validator(mode="after")
    def valid_product(self) -> SourceProduct:
        if self.landing_page.scheme != "https":
            raise ValueError("Source landing pages must use HTTPS")
        if not self.id or not self.name or not self.categories:
            raise ValueError("Product id, name and categories cannot be empty")
        return self


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern="^[a-z0-9-]+$")
    name: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    country: str = Field(pattern="^[A-Z]{2}$")
    trust_level: str = Field(pattern="^[A-D]$")
    official: bool
    products: list[SourceProduct] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_products(self) -> Source:
        if len({p.id for p in self.products}) != len(self.products):
            raise ValueError("Duplicate product id")
        return self


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
    final_url: HttpUrl | None = None

    @model_validator(mode="after")
    def aware_retrieval(self) -> RawAsset:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must include timezone")
        return self


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
    input_sha256: list[str] = Field(default_factory=list)
    validity_evidence: list[str] = Field(default_factory=list)
    local_access: LocalAccessPolicy = Field(default_factory=LocalAccessPolicy)
    capabilities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interval(self) -> DatasetRelease:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must include timezone")
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None:
            raise ValueError("有效期必须包含时区")
        if self.valid_from >= self.valid_to:
            raise ValueError("valid_from 必须早于 valid_to")
        if not self.input_sha256:
            self.input_sha256 = [self.sha256]
        if self.sha256 not in self.input_sha256:
            raise ValueError("Primary asset must belong to release inputs")
        import re

        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in self.input_sha256):
            raise ValueError("Invalid input SHA-256")
        return self

    def is_current(self, at: datetime | None = None) -> bool:
        at = at or datetime.now(UTC)
        if at.tzinfo is None:
            raise ValueError("查询时间必须包含时区")
        return (
            self.quality_status is QualityStatus.VERIFIED and self.valid_from <= at < self.valid_to
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
