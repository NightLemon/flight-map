"""Read-only, release-pinned local research API."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from flightmap_schema import DatasetRelease, airac_period_at, load_sources
from flightmap_schema.publication import check_publication
from flightmap_storage import Repository, StoreError

DISCLAIMER = "仅供研究与学习，不得用于航空器导航、签派放行或替代官方飞行前简报。"
ViewMode = Literal["current", "preview", "history"]
LAYERS = {
    "airports": "airport",
    "runways": "runway",
    "navaids": "navaid",
    "waypoints": "waypoint",
    "airways": "airway",
}


def _registry_path() -> Path:
    path = Path(os.getenv("FLIGHTMAP_SOURCE_REGISTRY", "sources/us/faa.yml"))
    if path.is_absolute():
        return path
    return next(
        (base / path for base in [Path.cwd(), *Path.cwd().parents] if (base / path).is_file()), path
    )


def _intersects(geometry: dict, bounds: tuple) -> bool:
    if geometry.get("type") == "MultiLineString":
        return any(_intersects({"coordinates": line}, bounds) for line in geometry["coordinates"])
    points = []

    def visit(value):
        if not isinstance(value, list):
            return
        if len(value) >= 2 and all(isinstance(v, int | float) for v in value[:2]):
            if all(math.isfinite(v) for v in value[:2]):
                points.append(value[:2])
        else:
            for item in value:
                visit(item)

    visit(geometry.get("coordinates"))
    if not points:
        return False
    west, south, east, north = bounds
    if max(p[1] for p in points) < south or min(p[1] for p in points) > north:
        return False
    left, right = min(p[0] for p in points), max(p[0] for p in points)
    return (right >= west and left <= east) if west <= east else (right >= west or left <= east)


def create_app(
    *,
    data_dir: str | Path | None = None,
    registry_path: str | Path | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    repo = Repository(data_dir or os.getenv("FLIGHTMAP_DATA_DIR", "data"))
    registry = Path(registry_path) if registry_path else _registry_path()
    application = FastAPI(title="Flight Map API", version="0.2.0", description=DISCLAIMER)
    application.state.repository = repo
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-FlightMap-Usage"] = "research-only; non-operational"
        return response

    @application.exception_handler(StoreError)
    async def store_error(_request: Request, error: StoreError):
        return JSONResponse(
            status_code=error.status_code, content={"detail": str(error), "disclaimer": DISCLAIMER}
        )

    def policies():
        return {(s.id, p.id): p for s in load_sources(registry) for p in s.products}

    def resolve(release_id, mode):
        if not release_id:
            raise StoreError("release_id is required; select a version from /api/v1/status")
        release = repo.get_release(release_id)
        product = policies().get((release.source_id, release.product_id))
        if product is None:
            raise StoreError("Release source is no longer registered", 403)
        return repo.resolve(release_id, product, source_id=release.source_id, mode=mode, at=clock())

    def envelope(release, mode, **data):
        resolve(release.id, mode)
        return {"release_id": release.id, "mode": mode, "disclaimer": DISCLAIMER, **data}

    def snapshot():
        now, stored, policy = clock(), repo.snapshot(), policies()
        current, releases = {}, []
        for item in stored["releases"]:
            release = DatasetRelease.model_validate(
                {
                    k: v
                    for k, v in item.items()
                    if k not in {"revoked_reason", "promoted_at", "report", "storage_error"}
                }
            )
            product = policy.get((release.source_id, release.product_id))
            pointer = stored["pointers"].get(f"{release.source_id}:{release.product_id}")
            state, reason = "staged", ""
            if item["revoked_reason"] is not None:
                state, reason = "revoked", item["revoked_reason"]
            elif release.quality_status.value != "verified":
                state, reason = "quarantined", "验证未通过；查看验证报告"
            elif item["storage_error"]:
                state, reason = "blocked", item["storage_error"]
            elif product is None:
                state, reason = "blocked", "来源未登记"
            else:
                try:
                    check_publication(
                        release, product, source_id=release.source_id, at=now, require_current=False
                    )
                except ValueError as exc:
                    state, reason = "blocked", str(exc)
                else:
                    if release.valid_from > now:
                        state = "preview"
                    elif release.valid_to <= now or (item["promoted_at"] and pointer != release.id):
                        state = "history"
                    elif pointer == release.id:
                        state = "current"
            public = {
                **release.model_dump(mode="json"),
                "state": state,
                "reason": reason,
                "revoked_reason": item["revoked_reason"],
                "counts": {
                    key: item["report"].get(key, 0)
                    for key in ["input_count", "success_count", "unsupported_count", "error_count"]
                },
            }
            releases.append(public)
            if state == "current":
                current[release.product_id] = public
        return {
            "current_time": now,
            "airac": airac_period_at(now).model_dump(mode="json"),
            "verified_release_available": bool(current),
            "current_releases": current,
            "publication_state": "current" if current else "empty",
            "releases": releases,
            "attempts": stored["attempts"],
            "storage_errors": stored["storage_errors"],
            "disclaimer": DISCLAIMER,
        }

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/api/v1/status")
    def status():
        return snapshot()

    @application.get("/api/v1/sources")
    def sources():
        return [source.model_dump(mode="json") for source in load_sources(registry)]

    @application.get("/api/v1/coverage")
    def coverage():
        state, rows = snapshot(), []
        for source in load_sources(registry):
            for product in source.products:
                candidate = state["current_releases"].get(product.id) or next(
                    (
                        r
                        for r in state["releases"]
                        if r["source_id"] == source.id and r["product_id"] == product.id
                    ),
                    None,
                )
                attempt = next(
                    (a for a in state["attempts"] if a["product_id"] == product.id), None
                )
                row = {
                    "region": source.country,
                    "source_id": source.id,
                    "product_id": product.id,
                    "name": product.name,
                    "categories": product.categories,
                    "license_status": product.license_status,
                    "local_access": product.local_access.model_dump(mode="json"),
                    "status": candidate["state"] if candidate else "not-imported",
                    "note": candidate["reason"] if candidate else "尚无通过验证的发布集",
                    "latest_attempt": attempt,
                    "official_url": str(product.landing_page),
                }
                if candidate:
                    row.update(
                        {
                            "release_id": candidate["id"],
                            **{
                                k: candidate[k]
                                for k in ["airac", "valid_from", "valid_to", "counts"]
                            },
                        }
                    )
                if attempt and attempt["status"] in {"failed", "needs-user-action", "blocked"}:
                    row["note"] = attempt["message"]
                rows.append(row)
        return rows

    @application.get("/api/v1/search")
    def search(
        q: Annotated[str, Query(min_length=1, max_length=100)],
        release_id: str | None = None,
        mode: ViewMode = "current",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        release = resolve(release_id, mode)
        matches = [
            r
            for r in repo.list_records(release.id, q=q.strip(), limit=100000)
            if r.kind not in {"leg", "chart"}
        ]
        matches.sort(
            key=lambda r: (r.identifier.upper() != q.strip().upper(), r.kind, r.identifier)
        )
        return envelope(
            release,
            mode,
            items=[r.model_dump(mode="json") for r in matches[:limit]],
            truncated=len(matches) > limit,
        )

    @application.get("/api/v1/features")
    def features(
        layer: Literal["airports", "runways", "navaids", "waypoints", "airways"],
        release_id: str | None = None,
        mode: ViewMode = "current",
        bbox: str | None = None,
        limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
    ):
        release = resolve(release_id, mode)
        bounds = (-180.0, -90.0, 180.0, 90.0)
        if bbox is not None:
            try:
                west, south, east, north = (float(v) for v in bbox.split(","))
                if not (
                    all(math.isfinite(v) for v in (west, south, east, north))
                    and -180 <= west <= 180
                    and -180 <= east <= 180
                    and -90 <= south <= north <= 90
                ):
                    raise ValueError("Invalid bounds")
                bounds = west, south, east, north
            except ValueError as exc:
                raise StoreError(
                    "bbox must be west,south,east,north in geographic degrees"
                ) from exc
        selected, offset = [], 0
        while True:
            batch = repo.list_records(release.id, kind=LAYERS[layer], limit=2000, offset=offset)
            for record in batch:
                if record.geometry and _intersects(record.geometry, bounds):
                    selected.append(
                        {
                            "type": "Feature",
                            "id": record.id,
                            "geometry": record.geometry,
                            "properties": {
                                **record.properties,
                                "id": record.id,
                                "name": record.name,
                                "identifier": record.identifier,
                                "kind": record.kind,
                                "airport_id": record.airport_id,
                                "airport_ident": record.airport_ident,
                                "provenance": record.provenance.model_dump(mode="json"),
                                "release_id": release.id,
                            },
                        }
                    )
                if len(selected) > limit:
                    break
            if len(selected) > limit or len(batch) < 2000:
                break
            offset += len(batch)
        return envelope(
            release,
            mode,
            type="FeatureCollection",
            features=selected[:limit],
            truncated=len(selected) > limit,
        )

    def airport_records(airport_ident, release_id, mode, kind):
        release = resolve(release_id, mode)
        records = repo.list_records(release.id, kind=kind, airport_ident=airport_ident)
        return envelope(release, mode, items=[r.model_dump(mode="json") for r in records])

    @application.get("/api/v1/airports/{id}/charts")
    def charts(id: str, release_id: str | None = None, mode: ViewMode = "current"):
        return airport_records(id, release_id, mode, "chart")

    @application.get("/api/v1/airports/{id}/procedures")
    def procedures(id: str, release_id: str | None = None, mode: ViewMode = "current"):
        return airport_records(id, release_id, mode, "procedure")

    @application.get("/api/v1/procedures/{id}")
    def procedure(id: str, release_id: str | None = None, mode: ViewMode = "current"):
        release = resolve(release_id, mode)
        record = repo.get_record(release.id, id)
        if record.kind != "procedure":
            raise StoreError("Procedure not found", 404)
        legs = repo.list_records(release.id, kind="leg", parent_id=id, limit=100000)
        return envelope(
            release,
            mode,
            record=record.model_dump(mode="json"),
            legs=[leg.model_dump(mode="json") for leg in legs],
            branches=sorted({leg.branch_id for leg in legs if leg.branch_id is not None}),
        )

    @application.get("/api/v1/procedures/{id}/geometry")
    def geometry(
        id: str,
        release_id: str | None = None,
        mode: ViewMode = "current",
        branch_id: str | None = None,
    ):
        from flightmap_ingestion.geometry import geometry_for_legs

        release = resolve(release_id, mode)
        if repo.get_record(release.id, id).kind != "procedure":
            raise StoreError("Procedure not found", 404)
        if not branch_id:
            raise StoreError("Select one explicit branch_id")
        legs = repo.list_records(
            release.id, kind="leg", parent_id=id, branch_id=branch_id, limit=100000
        )
        if not legs:
            raise StoreError("Procedure branch not found", 404)
        return envelope(release, mode, **geometry_for_legs(legs, branch_id=branch_id))

    @application.get("/api/v1/releases/{id}/report")
    def report(id: str):
        return {**repo.report(id), "disclaimer": DISCLAIMER}

    return application


app = create_app()


def run() -> None:
    uvicorn.run(
        "flightmap_api.main:app",
        host=os.getenv("FLIGHTMAP_API_HOST", "127.0.0.1"),
        port=int(os.getenv("FLIGHTMAP_API_PORT", "8000")),
        reload=os.getenv("FLIGHTMAP_ENV", "development") == "development",
    )
