"""Read-only snapshot endpoints. Every response retains the requested research version."""

from typing import Literal

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

    return resolve
