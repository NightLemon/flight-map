"""R17: official, bounded PDF reads without a mutable or arbitrary URL proxy."""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from flightmap_api import chart_pdf
from flightmap_schema import Provenance, ResearchRecord
from flightmap_storage import Repository, StoreError
from research_helpers import END, NOW, START, candidate, product, report

PDF = (Path(__file__).parent / "fixtures" / "synthetic-two-page.pdf").read_bytes()
URL = "https://aeronav.faa.gov/d-tpp/2609/SYNTHETIC.PDF"


def environment(tmp_path, *, props=None, kind="chart", product_id="dtpp", source_id="faa-aeronav"):
    repo = Repository(tmp_path / "data")
    original = tmp_path / "synthetic.txt"
    original.write_text("SYNTHETIC TEST ONLY", encoding="utf-8")
    raw = repo.store_asset(
        original,
        source_id=source_id,
        product_id=product_id,
        source_url="https://www.faa.gov/test-fixture/",
        retrieved_at=NOW,
        content_type="text/plain",
    )
    record = ResearchRecord(
        id="synthetic:chart:TEST",
        kind=kind,
        name="SYNTHETIC TEST ONLY",
        identifier="TEST",
        properties={
            "cycle": "2609",
            "pdf_url": URL,
            "deleted": False,
            "raw_fields": {"pdf_name": "SYNTHETIC.PDF"},
            **(props or {}),
        },
        provenance=Provenance(asset_sha256=raw.sha256, line=1, locator="synthetic:1"),
    )
    release = candidate(raw, source_id=source_id, capabilities=["charts"])
    repo.stage(release, [record], report(capabilities=["charts"]))
    policy = product(product_id)
    repo.promote(release.id, policy, source_id=source_id, at=NOW)
    clock = [NOW]
    app = FastAPI()

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StoreError)
    async def store_error(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    def resolve(release_id, mode):
        if not release_id:
            raise StoreError("release_id is required")
        return repo.resolve(release_id, policy, source_id=source_id, at=clock[0], mode=mode)

    chart_pdf.install_chart_pdf_route(app, repo, resolve)
    return SimpleNamespace(
        repo=repo,
        raw=raw,
        release=release,
        record=record,
        clock=clock,
        policy=policy,
        client=TestClient(app),
    )


def fetch(env, **kwargs):
    params = {"release_id": env.release.id, **kwargs.pop("params", {})}
    chart_id = kwargs.pop("chart_id", env.record.id)
    return env.client.get(f"/api/v1/charts/{chart_id}/pdf", params=params, **kwargs)


def upstream(monkeypatch, handler=None):
    requests, options = [], []
    original = httpx.AsyncClient

    async def serve(request):
        requests.append(request)
        if handler:
            return handler(request)
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})

    def client(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(serve), **kwargs)

    monkeypatch.setattr(chart_pdf.httpx, "AsyncClient", client)
    return requests, options


class Stream(httpx.AsyncByteStream):
    def __init__(self, parts, *, delay=0, after_first=None):
        self.parts, self.delay, self.after_first = parts, delay, after_first
        self.closed = False

    async def __aiter__(self):
        for index, part in enumerate(self.parts):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield part
            if index == 0 and self.after_first:
                self.after_first()

    async def aclose(self):
        self.closed = True


def test_pdf_is_memory_only_and_pinned_without_forwarding_browser_credentials(
    tmp_path, monkeypatch
):
    env = environment(tmp_path)
    requests, options = upstream(monkeypatch)
    before = sorted(p.relative_to(env.repo.data_dir) for p in env.repo.data_dir.rglob("*"))
    response = fetch(
        env,
        headers={"Authorization": "Bearer browser-secret", "Cookie": "session=secret"},
        params={"url": "https://example.invalid/never-follow.pdf"},
    )
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-flightmap-release-id"] == env.release.id
    assert response.headers["x-flightmap-chart-id"] == env.record.id
    assert response.headers["x-flightmap-pdf-sha256"] == hashlib.sha256(PDF).hexdigest()
    assert len(requests) == 1 and str(requests[0].url) == URL
    assert "authorization" not in requests[0].headers and "cookie" not in requests[0].headers
    assert requests[0].headers["accept-encoding"] == "identity"
    assert options[0]["follow_redirects"] is False and options[0]["trust_env"] is False
    assert options[0]["auth"] is None
    assert chart_pdf.PDF_MAX_BYTES == 20 * 1024 * 1024
    assert chart_pdf.PDF_TIMEOUT_SECONDS == 20
    assert sorted(p.relative_to(env.repo.data_dir) for p in env.repo.data_dir.rglob("*")) == before


@pytest.mark.parametrize(
    "props",
    [
        {"pdf_url": "http://aeronav.faa.gov/d-tpp/2609/SYNTHETIC.PDF"},
        {"pdf_url": "https://aeronav.faa.gov.evil.invalid/d-tpp/2609/SYNTHETIC.PDF"},
        {"pdf_url": "https://user:password@aeronav.faa.gov/d-tpp/2609/SYNTHETIC.PDF"},
        {"pdf_url": "https://aeronav.faa.gov:443/d-tpp/2609/SYNTHETIC.PDF"},
        {"pdf_url": URL + "?url=other"},
        {"pdf_url": URL + "#fragment"},
        {"pdf_url": "https://aeronav.faa.gov/d-tpp/2608/SYNTHETIC.PDF"},
        {"pdf_url": "https://aeronav.faa.gov/d-tpp/2609/OTHER.PDF"},
        {"cycle": "2608"},
        {"raw_fields": {}},
        {"raw_fields": "not-an-object"},
        {"raw_fields": {"pdf_name": "../SYNTHETIC.PDF"}},
        {"raw_fields": {"pdf_name": "%2e%2e/SYNTHETIC.PDF"}},
        {"raw_fields": {"pdf_name": "SYNTHETIC.PDF?query"}},
    ],
)
def test_invalid_stored_url_or_cycle_never_reaches_network(tmp_path, monkeypatch, props):
    env = environment(tmp_path, props=props)
    requests, _ = upstream(monkeypatch)
    response = fetch(env)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert not requests


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"kind": "airport"}, 404),
        ({"product_id": "nasr"}, 403),
        ({"source_id": "other-source"}, 403),
        ({"props": {"deleted": True}}, 404),
        ({"props": {"pdf_url": None}}, 404),
    ],
)
def test_wrong_record_product_or_missing_pdf_fails_before_network(
    tmp_path,
    monkeypatch,
    changes,
    status,
):
    env = environment(tmp_path, **changes)
    requests, _ = upstream(monkeypatch)
    assert fetch(env).status_code == status
    assert not requests


def test_unknown_chart_and_missing_or_invalid_version_selection(tmp_path, monkeypatch):
    env = environment(tmp_path)
    requests, _ = upstream(monkeypatch)
    assert fetch(env, chart_id="does-not-exist").status_code == 404
    assert env.client.get(f"/api/v1/charts/{env.record.id}/pdf").status_code == 400
    assert fetch(env, params={"mode": "typo"}).status_code == 422
    assert not requests


@pytest.mark.parametrize("status", [206, 301, 302, 307, 308, 401, 403, 404, 429, 500, 503])
def test_upstream_status_and_redirects_are_panel_errors(tmp_path, monkeypatch, status):
    env = environment(tmp_path)
    requests, _ = upstream(
        monkeypatch,
        lambda _: httpx.Response(
            status,
            content=PDF,
            headers={"content-type": "application/pdf", "location": "https://example.invalid/"},
        ),
    )
    response = fetch(env)
    assert response.status_code == 502
    assert response.headers["cache-control"] == "no-store"
    assert len(requests) == 1
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize(
    "headers,body",
    [
        ({}, PDF),
        ({"content-type": "text/html"}, PDF),
        ({"content-type": "application/octet-stream"}, PDF),
        ({"content-type": "application/pdf"}, b"<html>not a PDF</html>"),
        ({"content-type": "application/pdf"}, b"%PDF-"),
        ({"content-type": "application/pdf"}, b"%PDF-9.9\ninvalid"),
        ({"content-type": "application/pdf", "content-encoding": "gzip"}, PDF),
        ({"content-type": "application/pdf", "content-length": "-1"}, PDF),
        ({"content-type": "application/pdf", "content-length": "invalid"}, PDF),
        ({"content-type": "application/pdf", "content-length": "9" * 5000}, PDF),
        ({"content-type": "application/pdf", "content-length": str(len(PDF) + 1)}, PDF),
        ({"content-type": "application/pdf", "content-length": str(len(PDF) - 1)}, PDF),
    ],
)
def test_upstream_type_header_and_length_are_validated(tmp_path, monkeypatch, headers, body):
    env = environment(tmp_path)
    stream = Stream([body])
    upstream(monkeypatch, lambda _: httpx.Response(200, headers=headers, stream=stream))
    response = fetch(env)
    assert response.status_code == 502
    assert stream.closed
    assert "x-flightmap-pdf-sha256" not in response.headers


def test_pdf_content_type_parameters_and_streaming_without_length_are_accepted(
    tmp_path, monkeypatch
):
    env = environment(tmp_path)
    stream = Stream([PDF[:10], PDF[10:]])
    upstream(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            headers={"content-type": "Application/PDF; charset=binary"},
            stream=stream,
        ),
    )
    assert fetch(env).content == PDF
    assert stream.closed


@pytest.mark.parametrize("with_length", [True, False])
def test_body_cap_applies_to_declared_and_streamed_size(tmp_path, monkeypatch, with_length):
    env = environment(tmp_path)
    monkeypatch.setattr(chart_pdf, "PDF_MAX_BYTES", 1024)
    stream = Stream([b"%PDF-1.7\n", b"x" * 1024])
    headers = {"content-type": "application/pdf"}
    if with_length:
        headers["content-length"] = "1025"
    upstream(monkeypatch, lambda _: httpx.Response(200, headers=headers, stream=stream))
    assert fetch(env).status_code == 502
    assert stream.closed


@pytest.mark.parametrize(
    "failure,status",
    [
        (httpx.ConnectError, 502),
        (httpx.RemoteProtocolError, 502),
        (httpx.ReadTimeout, 504),
        (httpx.ConnectTimeout, 504),
    ],
)
def test_upstream_exceptions_are_explicit_panel_errors(tmp_path, monkeypatch, failure, status):
    env = environment(tmp_path)

    def fail(request):
        raise failure("Synthetic upstream failure", request=request)

    upstream(monkeypatch, fail)
    assert fetch(env).status_code == status


def test_total_deadline_stops_slow_drip_and_closes_stream(tmp_path, monkeypatch):
    env = environment(tmp_path)
    monkeypatch.setattr(chart_pdf, "PDF_TIMEOUT_SECONDS", 0.04)
    stream = Stream([PDF[:10], *[b"x" * 64 for _ in range(100)]], delay=0.01)
    upstream(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            stream=stream,
        ),
    )
    response = fetch(env)
    assert response.status_code == 504
    assert response.headers["cache-control"] == "no-store"
    assert stream.closed


@pytest.mark.parametrize(
    "change,status",
    [
        ("correction", 409),
        ("revoke", 410),
        ("expiry", 410),
        ("policy", 403),
    ],
)
def test_release_is_rechecked_after_upstream_read(tmp_path, monkeypatch, change, status):
    env = environment(tmp_path)

    def mutate():
        if change == "correction":
            correction = candidate(env.raw, "corrected", capabilities=["charts"])
            env.repo.stage(correction, [env.record], report(capabilities=["charts"]))
            env.repo.promote(correction.id, env.policy, at=NOW)
        elif change == "revoke":
            env.repo.revoke(env.release.id, "Synthetic withdrawal during PDF read")
        elif change == "expiry":
            env.clock[0] = END
        else:
            env.policy.local_access.processing = "unknown"

    stream = Stream([PDF[:10], PDF[10:]], after_first=mutate)
    upstream(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            stream=stream,
        ),
    )
    response = fetch(env)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "x-flightmap-pdf-sha256" not in response.headers
    assert PDF not in response.content
    assert stream.closed


@pytest.mark.parametrize("mode,at", [("preview", START - timedelta(days=1)), ("history", END)])
def test_explicit_preview_and_history_preserve_selected_cycle(tmp_path, monkeypatch, mode, at):
    env = environment(tmp_path)
    env.clock[0] = at
    requests, _ = upstream(monkeypatch)
    assert fetch(env).status_code in {409, 410}
    assert not requests
    response = fetch(env, params={"mode": mode})
    assert response.status_code == 200
    assert response.headers["x-flightmap-release-id"] == env.release.id
    assert str(requests[0].url) == URL
