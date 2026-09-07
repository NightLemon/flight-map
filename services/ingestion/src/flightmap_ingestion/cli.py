"""Read-only discovery and explicit local build/promotion commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from flightmap_schema import SourceProduct, load_sources
from flightmap_storage import Repository

from .acquisition import EvidenceRequired, build_local, load_manifest, update_product
from .faa import FaaDiscovery

app = typer.Typer(help="Flight Map official FAA local research tools")
RegistryOption = Annotated[Path, typer.Option(exists=True, readable=True)]
DataOption = Annotated[Path, typer.Option(envvar="FLIGHTMAP_DATA_DIR")]


def _product(registry: Path, identifier: str) -> SourceProduct:
    for source in load_sources(registry):
        if source.id == "faa-aeronav":
            for product in source.products:
                if product.id == identifier:
                    return product
    raise typer.BadParameter(f"Unknown FAA product: {identifier}")


def _echo(value) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """Acquisition builds candidates; only promote changes Current."""


@app.command("discover-faa")
def discover_faa(
    registry: RegistryOption = Path("sources/us/faa.yml"),
    product: Annotated[str | None, typer.Option()] = None,
    dry_run: Annotated[bool, typer.Option(help="Discover links without downloading assets")] = True,
    allow_network_failure: Annotated[bool, typer.Option()] = False,
    output: Annotated[
        Path | None, typer.Option(help="Save the report including network failures")
    ] = None,
) -> None:
    if not dry_run:
        raise typer.BadParameter("discover-faa only supports dry-run; use update for acquisition")
    results = []
    failed = False
    products = (
        [_product(registry, product)]
        if product
        else [p for s in load_sources(registry) for p in s.products]
    )
    for selected in products:
        entry = {
            "source": "faa-aeronav",
            "product": selected.id,
            "landing_page": str(selected.landing_page),
            "promotion": "disabled",
        }
        try:
            candidates = FaaDiscovery().fetch(selected)
            entry.update(
                candidate_count=len(candidates),
                candidates=[candidate.__dict__ for candidate in candidates],
                status="needs-user-action"
                if any(c.kind == "agreement" for c in candidates)
                else "discovered",
            )
        except Exception as exc:
            failed = True
            entry.update(error=str(exc), status="failed")
        results.append(entry)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _echo(results)
    if failed and not allow_network_failure:
        raise typer.Exit(code=1)


def _operation(repository: Repository, product_id: str, operation):
    try:
        result = operation()
        _echo(result)
        if result.get("status") == "quarantined":
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except EvidenceRequired as exc:
        repository.record_attempt(product_id, "needs-user-action", str(exc))
        _echo(
            {
                "product": product_id,
                "status": "needs-user-action",
                "reason": str(exc),
                "promotion": "not-requested",
            }
        )
        raise typer.Exit(2) from exc
    except Exception as exc:
        repository.record_attempt(product_id, "failed", str(exc))
        _echo(
            {
                "product": product_id,
                "status": "failed",
                "error": str(exc),
                "promotion": "not-requested",
            }
        )
        raise typer.Exit(1) from exc


@app.command("update")
def update(
    product: Annotated[str, typer.Option()],
    registry: RegistryOption = Path("sources/us/faa.yml"),
    data_dir: DataOption = Path("data"),
    manifest: Annotated[Path | None, typer.Option(exists=True, readable=True)] = None,
    preview: Annotated[bool, typer.Option()] = False,
) -> None:
    """Discover, acquire, verify, and build an immutable candidate; never promote."""
    selected = _product(registry, product)
    repository = Repository(data_dir)
    _operation(
        repository,
        product,
        lambda: update_product(
            repository,
            selected,
            manifest=load_manifest(manifest) if manifest else None,
            preview=preview,
        ),
    )


@app.command("import-local")
def import_local(
    product: Annotated[str, typer.Option()],
    file: Annotated[Path, typer.Option(exists=True, readable=True)],
    manifest: Annotated[Path, typer.Option(exists=True, readable=True)],
    registry: RegistryOption = Path("sources/us/faa.yml"),
    data_dir: DataOption = Path("data"),
) -> None:
    """Import a manually acquired official file with a source/validity manifest."""
    selected = _product(registry, product)
    repository = Repository(data_dir)
    _operation(
        repository,
        product,
        lambda: build_local(
            repository,
            selected,
            file,
            load_manifest(manifest),
        ),
    )


@app.command("report")
def report(
    release_id: Annotated[str, typer.Option()],
    data_dir: DataOption = Path("data"),
) -> None:
    """Read validation results and the difference from Current."""
    try:
        _echo(Repository(data_dir).report(release_id))
    except ValueError as exc:
        _echo({"status": "failed", "error": str(exc)})
        raise typer.Exit(1) from exc


@app.command("promote")
def promote(
    release_id: Annotated[str, typer.Option()],
    registry: RegistryOption = Path("sources/us/faa.yml"),
    data_dir: DataOption = Path("data"),
) -> None:
    """Recheck validity, evidence, quality, and permissions; transactionally switch Current."""
    repository = Repository(data_dir)
    try:
        release = repository.get_release(release_id)
        repository.promote(release_id, _product(registry, release.product_id))
        _echo({"release_id": release_id, "status": "current"})
    except ValueError as exc:
        _echo({"release_id": release_id, "status": "failed", "error": str(exc)})
        raise typer.Exit(1) from exc


@app.command("revoke")
def revoke(
    release_id: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option()],
    data_dir: DataOption = Path("data"),
) -> None:
    """Revoke a release and remove its Current pointer."""
    try:
        Repository(data_dir).revoke(release_id, reason)
        _echo({"release_id": release_id, "status": "revoked", "reason": reason})
    except ValueError as exc:
        _echo({"release_id": release_id, "status": "failed", "error": str(exc)})
        raise typer.Exit(1) from exc
