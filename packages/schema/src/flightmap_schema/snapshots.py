"""Date precision research data, deliberately separate from exact-validity releases."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .research import LocalAccessPolicy


class ResearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = ""
    source_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    official_effective_date: date
    date_precision: Literal["day"] = "day"
    exact_validity_status: Literal["unknown"] = "unknown"
    date_evidence: list[str] = Field(min_length=1)
    input_sha256: list[str] = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    schema_version: Literal["research-1", "research-2"] = "research-1"
    local_access: LocalAccessPolicy
    capabilities: list[str] = Field(default_factory=lambda: ["airports"])
    update_interval_days: Literal[28] = 28
    update_interval_evidence: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def identity(self) -> ResearchSnapshot:
        import re

        if any(not re.fullmatch(r"[a-f0-9]{64}", sha) for sha in self.input_sha256):
            raise ValueError("Invalid snapshot input SHA-256")
        if len(set(self.input_sha256)) != len(self.input_sha256):
            raise ValueError("Duplicate snapshot inputs")
        if self.schema_version == "research-2":
            allowed = {"airports", "runways", "navaids", "waypoints", "airways", "communications"}
            if (
                "airports" not in self.capabilities
                or not set(self.capabilities) <= allowed
                or len(set(self.capabilities)) != len(self.capabilities)
            ):
                raise ValueError("Invalid NASR research layer capabilities")
            self.capabilities = sorted(self.capabilities)
        self.input_sha256 = sorted(self.input_sha256)
        encoded = json.dumps(
            self.model_dump(mode="json", exclude={"id"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        expected = (
            f"{self.product_id}-research-{self.official_effective_date.isoformat()}-"
            f"{hashlib.sha256(encoded).hexdigest()[:24]}"
        )
        if self.id and self.id != expected:
            raise ValueError("Snapshot ID does not match immutable evidence")
        self.id = expected
        return self
