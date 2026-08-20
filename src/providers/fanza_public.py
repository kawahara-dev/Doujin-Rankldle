"""Conservative reader for FANZA's public ranking page only."""
from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from .base import RankingProvider

# The old ``ranking`` endpoint now serves a page whose markup is not the all-item
# ranking.  ``ranking-all`` is FANZA Doujin's public, non-authenticated ranking.
DEFAULT_URL = "https://www.dmm.co.jp/dc/doujin/-/ranking-all/"
USER_AGENT = "Doujin-RankIdle/0.3 (+public-ranking-watch; low-frequency)"
PRODUCT_PATH = re.compile(r"/dc/doujin/-/detail/", re.I)
CARD_CLASS = re.compile(r"(?:ranking|rank)[-_\w]*(?:item|list__item)", re.I)


class FanzaAgeGateError(RuntimeError):
    """Raised when FANZA redirects the public request to age verification."""


def _classes(attrs: dict[str, str | None]) -> str:
    return attrs.get("class") or ""


class RankingParser(HTMLParser):
    """Parse the current rank-list cards and their public product links."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self.candidate_count = 0
        self._card: dict[str, Any] | None = None
        self._card_tag = ""
        self._card_depth = 0
        self._capture: str | None = None
        self._anchor_depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        classes = _classes(attrs)
        is_card = tag in ("article", "li", "div") and (
            "data-rank" in attrs or CARD_CLASS.search(classes)
        )
        if self._card is None and is_card:
            rank_match = re.search(r"\d+", attrs.get("data-rank") or "")
            self._card = {
                "rank": int(rank_match.group()) if rank_match else 0,
                "title": "",
                "price": 0,
                "url": "",
            }
            self._card_tag = tag
            self._card_depth = 1
        elif self._card is not None and tag == self._card_tag:
            self._card_depth += 1

        if self._card is None:
            return
        href = attrs.get("href") or ""
        absolute_url = urljoin(self.base_url, href)
        if tag == "a" and href and PRODUCT_PATH.search(urlparse(absolute_url).path):
            if not self._card["url"]:
                self.candidate_count += 1
                self._card["url"] = absolute_url
                self._capture = "title"
                self._anchor_depth = 1
                if attrs.get("title"):
                    self._card["title"] = attrs["title"].strip()
        elif self._anchor_depth and tag == "a":
            self._anchor_depth += 1
        elif self._capture != "title" and re.search(r"price", classes, re.I):
            self._capture = "price"
        elif self._capture != "title" and re.search(r"(?:^|[-_])rank(?:$|[-_])", classes, re.I):
            self._capture = "rank"

        if self._capture == "title" and tag == "img" and not self._card["title"]:
            self._card["title"] = (attrs.get("alt") or "").strip()

    def handle_data(self, data: str) -> None:
        if self._card is None or not self._capture:
            return
        text = data.strip()
        if self._capture == "title" and text:
            self._card["title"] += text
        elif self._capture == "price" and (match := re.search(r"[\d,]+", text)):
            self._card["price"] = int(match.group().replace(",", ""))
        elif self._capture == "rank" and (match := re.search(r"\d+", text)):
            self._card["rank"] = int(match.group())

    def handle_endtag(self, tag: str) -> None:
        if self._card is None:
            return
        if tag == "a" and self._anchor_depth:
            self._anchor_depth -= 1
            if not self._anchor_depth:
                self._capture = None
        if tag == self._card_tag:
            self._card_depth -= 1
            if self._card_depth == 0:
                self._finish_card()

    def _finish_card(self) -> None:
        assert self._card is not None
        item = self._card
        if item["rank"] and item["title"] and item["url"]:
            query = parse_qs(urlparse(item["url"]).query)
            cid_match = re.search(r"/cid=([^/]+)/?", urlparse(item["url"]).path)
            cid = cid_match.group(1) if cid_match else query.get("cid", [""])[0]
            item["id"] = cid or item["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            self.items.append(item)
        self._card = None
        self._capture = None
        self._anchor_depth = 0


def parse_ranking_html(html: str, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
    parser = RankingParser(base_url)
    parser.feed(html)
    return sorted(parser.items, key=lambda item: item["rank"])


class FanzaPublicProvider(RankingProvider):
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("FANZA_PUBLIC_RANKING_URL", DEFAULT_URL)

    def fetch(self) -> list[dict[str, Any]]:
        parsed = urlparse(self.url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        robots = RobotFileParser()
        robots.set_url(robots_url)
        try:
            robots.read()
        except Exception as exc:
            raise RuntimeError(f"robots.txt could not be verified: {exc}") from exc
        if not robots.can_fetch(USER_AGENT, self.url):
            raise RuntimeError("robots.txt disallows public ranking fetch")

        request = Request(self.url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            html = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            status = response.status
            final_url = response.geturl()
        parser = RankingParser(final_url)
        parser.feed(html)
        items = sorted(parser.items, key=lambda item: item["rank"])
        print(
            "PUBLIC WATCH RESPONSE: "
            f"HTTP status={status}; final URL={final_url}; Content-Type={content_type}; "
            f"HTML characters={len(html)}; ranking candidates={parser.candidate_count}; "
            f"parsed items={len(items)}"
        )
        if "/age_check/" in urlparse(final_url).path:
            raise FanzaAgeGateError("FANZA age verification page reached")
        if "captcha" in html.lower():
            raise RuntimeError("CAPTCHA detected; stopped safely")
        if not content_type.lower().startswith("text/html"):
            raise RuntimeError(f"unexpected Content-Type: {content_type or 'missing'}")
        if not items:
            raise RuntimeError("no public ranking items parsed")
        return items
