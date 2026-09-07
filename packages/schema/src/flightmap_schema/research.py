"""Local research contracts; raw evidence remains separate from interpreted records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LocalAccessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acquisition: Literal["unknown", "allowed", "needs-user-action", "prohibited"] = "unknown"
    processing: Literal["unknown", "allowed", "needs-user-action", "prohibited"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    reviewed_at: datetime | None = None
    agreement_required: bool = False

    @model_validator(mode="after")
    def check_evidence(self) -> LocalAccessPolicy:
        if self.reviewed_at is not None and self.reviewed_at.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        if "allowed" in {self.acquisition, self.processing} and (
            not self.evidence or self.reviewed_at is None
        ):
            raise ValueError("Allowed local use requires evidence and review time")
        return self

    @property
    def allows_processing(self) -> bool:
        return self.processing == "allowed" and bool(self.evidence) and self.reviewed_at is not None


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    member: str | None = None
    line: int | None = Field(default=None, gt=0)
    locator: str = Field(min_length=1)


RecordKind = Literal[
    "airport", "runway", "navaid", "waypoint", "airway", "procedure", "leg", "chart"
]


class ResearchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    kind: RecordKind
    name: str
    identifier: str = ""
    airport_id: str | None = None
    airport_ident: str | None = None
    parent_id: str | None = None
    branch_id: str | None = None
    sequence: int | None = None
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    # ValidationIssue is resolved in models.py to avoid a circular import.
    issues: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def balanced(self) -> ValidationReport:
        if self.input_count != self.success_count + self.unsupported_count + self.error_count:
            raise ValueError("Report counts must account for every input record")
        for issue in self.issues:
            if issue.get("severity") not in {"info", "warning", "error", "fatal"}:
                raise ValueError("Every issue requires a valid severity")
        return self

    @property
    def blocking(self) -> bool:
        return self.error_count > 0 or any(
            issue["severity"] in {"error", "fatal"} for issue in self.issues
        )


class ParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[ResearchRecord]
    report: ValidationReport


class ImportManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = "faa-aeronav"
    product_id: str
    source_url: str
    airac: str = Field(pattern=r"^\d{4}$")
    valid_from: datetime
    valid_to: datetime
    validity_evidence: list[str] = Field(min_length=1)
    parser_version: str = "0.2.0"
    member: str | None = None

    @model_validator(mode="after")
    def interval(self) -> ImportManifest:
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None:
            raise ValueError("Product validity must include timezone")
        if self.valid_from >= self.valid_to:
            raise ValueError("Product validity must be a nonempty interval")
        return self
