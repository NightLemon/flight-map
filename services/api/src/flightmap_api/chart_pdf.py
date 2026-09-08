"""Bounded, release-pinned PDF reads for stored FAA d-TPP chart records."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from flightmap_schema import DatasetRelease, ResearchRecord
from flightmap_storage import Repository, StoreError

PDF_MAX_BYTES = 20 * 1024 * 1024
PDF_TIMEOUT_SECONDS = 20.0
PDF_CHUNK_BYTES = 64 * 1024
ViewMode = Literal["current", "preview", "history"]
_PDF_HEADER = re.compile(rb"%PDF-(?:1\.[0-7]|2\.0)(?:\r\n|\n|\r)")
_PDF_FILENAME = re.compile(r"[A-Za-z0-9_-]+\.PDF", re.IGNORECASE)


def _upstream_error(message: str, status_code: int = 502) -> HTTPException:
    return HTTPException(status_code, message, headers={"Cache-Control": "no-store"})


def _chart_url(release: DatasetRelease, chart: ResearchRecord) -> str:
    if release.source_id != "faa-aeronav" or release.product_id != "dtpp":
        raise StoreError("PDF reading requires an FAA d-TPP release", 403)
    if chart.kind != "chart":
        raise StoreError("Chart not found", 404)
    props = chart.properties
    if props.get("deleted") or not props.get("pdf_url"):
        raise StoreError("This chart has no PDF in the selected release", 404)
    raw = props.get("raw_fields")
    filename = raw.get("pdf_name") if isinstance(raw, dict) else None
    if (
        not isinstance(filename, str)
        or not _PDF_FILENAME.fullmatch(filename)
        or not re.fullmatch(r"[0-9]{4}", release.airac)
        or props.get("cycle") != release.airac
    ):
        raise StoreError("Chart PDF lacks a verified filename and matching product cycle", 403)
    expected = f"https://aeronav.faa.gov/d-tpp/{release.airac}/{filename}"
    if props.get("pdf_url") != expected:
        raise StoreError("Chart PDF URL does not match its official stored cycle and filename", 403)
    return expected


async def _read_pdf(url: str) -> tuple[bytearray, str]:
    """The deadline covers connection, headers, the whole body, and cleanup."""
    try:
        async with asyncio.timeout(PDF_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                auth=None,
                timeout=PDF_TIMEOUT_SECONDS,
                headers={"Accept": "application/pdf", "Accept-Encoding": "identity"},
            ) as client:
                async with client.stream("GET", url) as upstream:
                    if upstream.status_code != 200:
                        raise _upstream_error("The official chart server did not return a PDF")
                    content_type = upstream.headers.get("content-type", "").split(";", 1)[0]
                    if content_type.strip().lower() != "application/pdf":
                        raise _upstream_error("The official chart response is not application/pdf")
                    encoding = upstream.headers.get("content-encoding", "identity").strip().lower()
                    if encoding != "identity":
                        raise _upstream_error("Compressed upstream PDF responses are not supported")
                    length = upstream.headers.get("content-length")
                    expected_size = None
                    if length is not None:
                        if not re.fullmatch(r"[0-9]+", length.strip()):
                            raise _upstream_error("The official chart response has an invalid size")
                        normalized_length = length.strip().lstrip("0") or "0"
                        if len(normalized_length) > len(str(PDF_MAX_BYTES)):
                            raise _upstream_error("The official chart PDF exceeds the 20 MiB limit")
                        expected_size = int(normalized_length)
                        if expected_size > PDF_MAX_BYTES:
                            raise _upstream_error("The official chart PDF exceeds the 20 MiB limit")
                    body, digest = bytearray(), hashlib.sha256()
                    async for chunk in upstream.aiter_bytes(chunk_size=PDF_CHUNK_BYTES):
                        if len(body) + len(chunk) > PDF_MAX_BYTES:
                            raise _upstream_error("The official chart PDF exceeds the 20 MiB limit")
                        body.extend(chunk)
                        digest.update(chunk)
                        if len(body) >= 9 and not _PDF_HEADER.match(body):
                            raise _upstream_error(
                                "The official chart response has no valid PDF header"
                            )
                    if expected_size is not None and len(body) != expected_size:
                        raise _upstream_error("The official chart PDF is incomplete")
                    if not _PDF_HEADER.match(body):
                        raise _upstream_error("The official chart response has no valid PDF header")
                    return body, digest.hexdigest()
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise _upstream_error(
            "The official chart PDF exceeded the 20 second deadline", 504
        ) from exc
    except httpx.HTTPError as exc:
        raise _upstream_error("The official chart PDF could not be read") from exc


def install_chart_pdf_route(
    application: FastAPI,
    repo: Repository,
    resolve: Callable[[str | None, ViewMode], DatasetRelease],
) -> None:
    @application.get("/api/v1/charts/{chart_id}/pdf")
    async def chart_pdf(
        chart_id: str,
        release_id: str | None = None,
        mode: ViewMode = "current",
    ) -> Response:
        release = resolve(release_id, mode)
        chart = repo.get_record(release.id, chart_id)
        url = _chart_url(release, chart)
        body, digest = await _read_pdf(url)
        # A Current switch, expiry, policy change, or revocation during I/O must win.
        resolve(release.id, mode)
        return Response(
            content=memoryview(body),
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-FlightMap-Release-Id": release.id,
                "X-FlightMap-Chart-Id": chart.id,
                "X-FlightMap-Pdf-Sha256": digest,
            },
        )
