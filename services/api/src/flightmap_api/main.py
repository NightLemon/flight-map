"""Flight Map 只读 API。"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from flightmap_schema import airac_period_at, load_sources

DISCLAIMER = "仅供研究与学习，不得用于航空器导航、签派放行或替代官方飞行前简报。"


def _registry_path() -> Path:
    configured = Path(os.getenv("FLIGHTMAP_SOURCE_REGISTRY", "sources/us/faa.yml"))
    if configured.is_absolute():
        return configured
    current = Path.cwd()
    for base in [current, *current.parents]:
        candidate = base / configured
        if candidate.exists():
            return candidate
    return configured


def create_app() -> FastAPI:
    application = FastAPI(
        title="Flight Map API",
        version="0.1.0",
        description=DISCLAIMER,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/v1/status")
    def status() -> dict[str, object]:
        now = datetime.now(UTC)
        period = airac_period_at(now)
        return {
            "current_time": now,
            "airac": period.model_dump(mode="json"),
            "verified_release_available": False,
            "publication_state": "empty",
            "disclaimer": DISCLAIMER,
        }

    @application.get("/api/v1/sources")
    def sources() -> list[dict[str, object]]:
        return [source.model_dump(mode="json") for source in load_sources(_registry_path())]

    @application.get("/api/v1/coverage")
    def coverage() -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for source in load_sources(_registry_path()):
            for product in source.products:
                rows.append(
                    {
                        "region": source.country,
                        "source_id": source.id,
                        "product_id": product.id,
                        "name": product.name,
                        "categories": product.categories,
                        "status": "not-imported",
                        "license_status": product.license_status,
                        "note": "尚无通过验证且处于有效期的发布集",
                    }
                )
        return rows

    return application


app = create_app()


def run() -> None:
    uvicorn.run(
        "flightmap_api.main:app",
        host=os.getenv("FLIGHTMAP_API_HOST", "127.0.0.1"),
        port=int(os.getenv("FLIGHTMAP_API_PORT", "8000")),
        reload=os.getenv("FLIGHTMAP_ENV", "development") == "development",
    )
