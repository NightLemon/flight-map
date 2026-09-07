"""机器可读来源注册表加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from .models import Source


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    sources: list[Source]

    @model_validator(mode="after")
    def unique_sources(self) -> SourceRegistry:
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("Duplicate source id")
        return self


def load_sources(path: str | Path) -> list[Source]:
    registry_path = Path(path)
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    return SourceRegistry.model_validate(payload).sources
