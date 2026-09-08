"""Read-only snapshot endpoints. Every response retains the requested research version."""

import math
from typing import Annotated, Literal

from fastapi import Query
from flightmap_schema.research_layers import LAYER_KINDS
from flightmap_storage import StoreError

ResearchMode = Literal["active", "history", "preview"]


def install_research_routes(application, repo, policies, clock, disclaimer):
    def resolve(snapshot_id, mode):
        if not snapshot_id:
            raise StoreError("snapshot_id is required; select a research snapshot")
        snapshot = repo.get_snapshot(snapshot_id)
        product = policies().get((snapshot.source_id, snapshot.product_id))
        if product is None:
            raise StoreError("Snapshot source is no longer registered", 403)
        return repo.resolve_snapshot(
            snapshot_id, product, source_id=snapshot.source_id, mode=mode, at=clock()
        )

    @application.get("/api/v1/research/snapshots")
    def snapshots():
        return {**repo.research_status(policies(), at=clock()), "disclaimer": disclaimer}

    @application.get("/api/v1/research/snapshots/{id}/report")
    def snapshot_report(id: str):
        return {**repo.snapshot_report(id), "disclaimer": disclaimer}

    @application.get("/api/v1/research/search")
    def search(
        q: Annotated[str, Query(min_length=1, max_length=100)],
        snapshot_id: str | None = None,
        mode: ResearchMode = "active",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        item = resolve(snapshot_id, mode)
        query = q.strip()
        if not query:
            raise StoreError("Search query cannot be blank")
        records = repo.list_snapshot_records(item.id, q=query)
        records.sort(
            key=lambda r: (
                query.upper()
                not in {r.identifier.upper(), str(r.properties.get("icao_id") or "").upper()},
                r.identifier,
                r.id,
            )
        )
        resolve(item.id, mode)
        return {
            "snapshot_id": item.id,
            "mode": mode,
            "disclaimer": disclaimer,
            "items": [r.model_dump(mode="json") for r in records[:limit]],
            "truncated": len(records) > limit,
        }

    @application.get("/api/v1/research/features")
    def features(
        snapshot_id: str | None = None,
        mode: ResearchMode = "active",
        layer: Literal["airports", "runways", "navaids", "waypoints", "airways"] = "airports",
        bbox: str | None = None,
        limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
    ):
        item = resolve(snapshot_id, mode)
        if layer not in item.capabilities:
            raise StoreError("This research snapshot does not support the requested layer", 422)
        try:
            west, south, east, north = (float(v) for v in (bbox or "-180,-90,180,90").split(","))
            if not (
                all(math.isfinite(v) for v in (west, south, east, north))
                and -180 <= west <= 180
                and -180 <= east <= 180
                and -90 <= south <= north <= 90
            ):
                raise ValueError("Invalid geographic bounds")
        except ValueError as exc:
            raise StoreError("bbox must be west,south,east,north in geographic degrees") from exc
        selected = []
        for record in repo.list_snapshot_records(
            item.id,
            bounds=(west, south, east, north),
            limit=limit + 1,
            kind=LAYER_KINDS[layer],
        ):
            selected.append(
                {
                    "type": "Feature",
                    "id": record.id,
                    "geometry": record.geometry,
                    "properties": {
                        **{k: v for k, v in record.properties.items() if k != "raw_fields"},
                        "id": record.id,
                        "name": record.name,
                        "identifier": record.identifier,
                        "kind": record.kind,
                        "airport_id": record.airport_id,
                        "airport_ident": record.airport_ident,
                        "provenance": record.provenance.model_dump(mode="json"),
                        "snapshot_id": item.id,
                    },
                }
            )
            if len(selected) > limit:
                break
        resolve(item.id, mode)
        return {
            "snapshot_id": item.id,
            "mode": mode,
            "disclaimer": disclaimer,
            "type": "FeatureCollection",
            "features": selected[:limit],
            "truncated": len(selected) > limit,
        }

    @application.get("/api/v1/research/records/{record_id}")
    def record_detail(
        record_id: str, snapshot_id: str | None = None, mode: ResearchMode = "active"
    ):
        item = resolve(snapshot_id, mode)
        records = repo.list_snapshot_records(item.id, record_id=record_id, limit=1)
        if not records:
            raise StoreError("Research record not found in the selected snapshot", 404)
        resolve(item.id, mode)
        return {
            "snapshot_id": item.id,
            "mode": mode,
            "disclaimer": disclaimer,
            "record": records[0].model_dump(mode="json"),
        }

    @application.get("/api/v1/research/airports/{airport_id}/communications")
    def communications(
        airport_id: str,
        snapshot_id: str | None = None,
        mode: ResearchMode = "active",
    ):
        item = resolve(snapshot_id, mode)
        airports = repo.list_snapshot_records(
            item.id, record_id=airport_id, kind="airport", limit=1
        )
        if not airports:
            raise StoreError("Airport not found in the selected snapshot", 404)
        if "communications" not in item.capabilities:
            raise StoreError("This research snapshot does not contain airport communications", 409)
        records = repo.list_snapshot_records(item.id, kind="communication", airport_id=airport_id)
        records.sort(
            key=lambda r: (r.properties.get("service", ""), r.properties["frequency"], r.id)
        )
        resolve(item.id, mode)
        return {
            "snapshot_id": item.id,
            "mode": mode,
            "disclaimer": disclaimer,
            "items": [record.model_dump(mode="json") for record in records],
        }

    return resolve
