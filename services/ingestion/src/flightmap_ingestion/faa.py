"""Product-specific FAA discovery; classify links before acquisition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from flightmap_schema import SourceProduct

from .download import USER_AGENT

_DATE_TOKEN = re.compile(r"(?<!\d)(20\d{2}[-_/]?\d{2}[-_/]?\d{2}|\d{6})(?!\d)")
_NASR_PAGE = re.compile(r"/NASR_Subscription/20\d{2}-\d{2}-\d{2}/?$", re.I)
_APT_ZIP = re.compile(r"/\d{2}_[A-Za-z]{3}_20\d{2}_APT_CSV\.zip$", re.I)
_NASR_LAYER_ZIP = re.compile(r"/\d{2}_[A-Za-z]{3}_20\d{2}_(NAV|FIX|AWY|FRQ)_CSV\.zip$", re.I)


@dataclass(frozen=True)
class DiscoveryCandidate:
    url: str
    label: str
    observed_date_token: str | None
    kind: str = "asset"
    role: str = "data"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._label = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._label).strip()))
            self._href = None
            self._label = []


def _classify(product_id: str, url: str, label: str) -> tuple[str, str] | None:
    path = urlparse(url).path
    lower = path.lower()
    if "test" in lower or "test" in label.lower():
        return None
    if product_id == "nasr":
        if _NASR_PAGE.search(path):
            return "product-page", "edition"
        if _APT_ZIP.search(path):
            return "asset", "airport-csv"
        layer = _NASR_LAYER_ZIP.search(path)
        if layer:
            return "asset", f"{layer[1].lower()}-csv"
        if re.search(r"/20\d{2}-\d{2}-\d{2}/AWY\.zip$", path, re.I):
            return "asset", "airway-points"
        if lower.endswith("/layout_data.zip"):
            return "documentation", "nasr-layout"
        if lower.endswith("/readme.txt"):
            return "documentation", "readme"
        if lower.endswith(".pdf") and "nasr" in lower:
            return "documentation", "notice"
    elif product_id == "dtpp":
        if lower.endswith("/dtpp/search/"):
            return "product-page", "catalog-search"
        if lower.endswith("/d-tpp_metafile.xml"):
            return "asset", "chart-catalog"
        if lower.endswith("metafile_xml_definitions.pdf"):
            return "documentation", "definitions"
        if re.search(r"/ddtpp[a-e]_\d{6}\.zip$", lower):
            return "asset", "chart-package"
    elif product_id == "cifp":
        if "i agree" in label.lower() or lower.endswith("/cifp/download/"):
            return "agreement", "needs-user-action"
        if lower.endswith(".pdf") and "cifp" in lower.rsplit("/", 1)[-1]:
            return "documentation", "readme"
        if lower.endswith(".zip") and "cifp" in lower:
            return "asset", "cifp"
    elif product_id == "ifr-charts":
        if lower.endswith((".zip", ".tif", ".tiff", ".pdf")):
            return "asset", "chart"
    elif product_id == "safety-alerts":
        if lower.endswith(".pdf") and "/safety_alerts/" in lower:
            return "documentation", "notice"
    return None


class FaaDiscovery:
    def discover_html(
        self, product: SourceProduct, html: str, *, page_url: str | None = None
    ) -> list[DiscoveryCandidate]:
        parser = _LinkParser()
        parser.feed(html)
        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, label in parser.links:
            absolute_url = urljoin(page_url or str(product.landing_page), href)
            parsed = urlparse(absolute_url)
            if parsed.scheme != "https" or not (
                parsed.hostname == "faa.gov" or (parsed.hostname or "").endswith(".faa.gov")
            ):
                continue
            classification = _classify(product.id, absolute_url, label)
            if classification is None or absolute_url in seen:
                continue
            seen.add(absolute_url)
            date_match = _DATE_TOKEN.search(f"{absolute_url} {label}")
            candidates.append(
                DiscoveryCandidate(
                    url=absolute_url,
                    label=label,
                    observed_date_token=date_match.group(1) if date_match else None,
                    kind=classification[0],
                    role=classification[1],
                )
            )
        return candidates

    def fetch(
        self, product: SourceProduct, timeout_seconds: float = 30
    ) -> list[DiscoveryCandidate]:
        """Read listed edition/search pages, never follow an agreement link."""
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.get(str(product.landing_page))
            response.raise_for_status()
            candidates = self.discover_html(product, response.text, page_url=str(response.url))
            pages = [c for c in candidates if c.kind == "product-page"]
            for page in pages[:6]:
                response = client.get(page.url)
                response.raise_for_status()
                candidates.extend(
                    self.discover_html(product, response.text, page_url=str(response.url))
                )
        return list({candidate.url: candidate for candidate in candidates}.values())
