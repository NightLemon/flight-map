"""机器可读来源注册表加载。"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import Source


def load_sources(path: str | Path) -> list[Source]:
    registry_path = Path(path)
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("来源注册表必须包含 sources 数组")
    return [Source.model_validate(item) for item in payload["sources"]]
