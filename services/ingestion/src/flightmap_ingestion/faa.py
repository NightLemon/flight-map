"""FAA 官方产品页面发现器。

发现器只报告页面上真实存在的链接，不推断生效期，也不自动发布。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from flightmap_schema import SourceProduct

from .download import USER_AGENT

_DATE_TOKEN = re.compile(r"(?<!\d)(20\d{2}[-_/]?\d{2}[-_/]?\d{2}|\d{6})(?!\d)")


@dataclass(frozen=True)
class DiscoveryCandidate:
    url: str
    label: str
    observed_date_token: str | None


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


class FaaDiscovery:
    def discover_html(self, product: SourceProduct, html: str) -> list[DiscoveryCandidate]:
        parser = _LinkParser()
        parser.feed(html)
        contains = [value.lower() for value in product.discovery.link_contains]
        candidates: list[DiscoveryCandidate] = []
        seen: set[str] = set()
        for href, label in parser.links:
            absolute_url = urljoin(str(product.landing_page), href)
            haystack = f"{href} {label}".lower()
            if contains and not any(token in haystack for token in contains):
                continue
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            date_match = _DATE_TOKEN.search(f"{absolute_url} {label}")
            candidates.append(
                DiscoveryCandidate(
                    url=absolute_url,
                    label=label,
                    observed_date_token=date_match.group(1) if date_match else None,
                )
            )
        return candidates

    def fetch(
        self, product: SourceProduct, timeout_seconds: float = 30
    ) -> list[DiscoveryCandidate]:
        response = httpx.get(
            str(product.landing_page),
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return self.discover_html(product, response.text)
