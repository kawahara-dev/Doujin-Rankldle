"""Conservative reader for FANZA's public ranking page only."""
from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from .base import RankingProvider

DEFAULT_URL = "https://www.dmm.co.jp/dc/doujin/-/ranking/"
USER_AGENT = "Doujin-RankIdle/0.3 (+public-ranking-watch; low-frequency)"


class RankingParser(HTMLParser):
    """Parse explicitly annotated cards; also supports common rank/item classes."""
    def __init__(self, base_url: str):
        super().__init__(); self.base_url = base_url; self.items = []; self.current = None; self.capture = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs); classes = a.get("class", "")
        if tag in ("article", "li", "div") and ("data-rank" in a or re.search(r"ranking[-_ ]?item", classes, re.I)):
            self.current = {"rank": int(a.get("data-rank", "0") or 0), "title": "", "price": 0, "url": ""}
        if not self.current: return
        if tag == "a" and a.get("href") and not self.current["url"]:
            self.current["url"] = urljoin(self.base_url, a["href"]); self.capture = "title"
        elif re.search(r"price", classes, re.I): self.capture = "price"
        elif re.search(r"rank", classes, re.I): self.capture = "rank"

    def handle_data(self, data):
        if not self.current or not self.capture: return
        text = data.strip()
        if self.capture == "title" and text: self.current["title"] += text
        elif self.capture == "price" and (m := re.search(r"[\d,]+", text)): self.current["price"] = int(m.group().replace(",", ""))
        elif self.capture == "rank" and (m := re.search(r"\d+", text)): self.current["rank"] = int(m.group())

    def handle_endtag(self, tag):
        if tag == "a": self.capture = None
        if self.current and tag in ("article", "li", "div") and self.current["rank"] and self.current["title"] and self.current["url"]:
            self.current["id"] = self.current["url"].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            self.items.append(self.current); self.current = None; self.capture = None


def parse_ranking_html(html: str, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
    parser = RankingParser(base_url); parser.feed(html)
    return sorted(parser.items, key=lambda x: x["rank"])


class FanzaPublicProvider(RankingProvider):
    def __init__(self, url: str | None = None): self.url = url or os.getenv("FANZA_PUBLIC_RANKING_URL", DEFAULT_URL)
    def fetch(self) -> list[dict[str, Any]]:
        parsed = urlparse(self.url); robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        robots = RobotFileParser(); robots.set_url(robots_url)
        try: robots.read()
        except Exception as exc: raise RuntimeError(f"robots.txt could not be verified: {exc}") from exc
        if not robots.can_fetch(USER_AGENT, self.url): raise RuntimeError("robots.txt disallows public ranking fetch")
        request = Request(self.url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with urlopen(request, timeout=30) as response:
            html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        if "captcha" in html.lower(): raise RuntimeError("CAPTCHA detected; stopped safely")
        items = parse_ranking_html(html, self.url)
        if not items: raise RuntimeError("no public ranking items parsed")
        return items
