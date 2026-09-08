"""Read-only snapshot endpoints. Every response retains the requested research version."""

import math
from typing import Annotated, Literal

from fastapi import Query
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
        layer: Literal["airports"] = "airports",
        bbox: str | None = None,
        limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
    ):
        item = resolve(snapshot_id, mode)
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
        for record in repo.list_snapshot_records(item.id):
            lon, lat = record.geometry["coordinates"]
            longitude_matches = west <= lon <= east if west <= east else lon >= west or lon <= east
            if not longitude_matches or not south <= lat <= north:
                continue
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
                        "kind": "airport",
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

    return resolve
