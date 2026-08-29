"""Low-frequency collector for DLsite's public maniax ranking page."""

from __future__ import annotations

from urllib.error import URLError
from urllib.parse import urlsplit

from scripts.dlsite_ranking_probe import _blocked, fetch, parse_ranking


RANKING_URL = "https://www.dlsite.com/maniax/ranking"
ALLOWED_HOSTS = {"dlsite.com", "www.dlsite.com"}


class DLsiteRankingError(RuntimeError):
    """A safe, non-retriable failure while collecting the ranking."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


def _safe_product_url(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        return None
    if "/work/" not in parts.path:
        return None
    return parts._replace(scheme="https", fragment="").geturl()


class DLsiteRankingProvider:
    """Fetch and parse the ranking with exactly one HTTP GET per invocation."""

    def __init__(self, url: str = RANKING_URL, timeout: float = 20.0):
        self.url = url
        self.timeout = timeout
        self.http_status: int | None = None

    def fetch(self) -> list[dict]:
        try:
            access, html = fetch(self.url, self.timeout)
        except (URLError, TimeoutError, OSError) as exc:
            raise DLsiteRankingError(f"request failed: {exc}") from exc
        self.http_status = access["http_status"]
        reason = _blocked(self.http_status, access["final_url"], html)
        if reason:
            raise DLsiteRankingError(reason, self.http_status)
        if self.http_status != 200:
            raise DLsiteRankingError(f"HTTP {self.http_status}", self.http_status)
        try:
            parsed, _ = parse_ranking(html, access["final_url"], limit=20)
        except Exception as exc:
            raise DLsiteRankingError(f"parser failure: {exc}", self.http_status) from exc
        items = []
        for raw in parsed:
            url = _safe_product_url(str(raw.get("url") or ""))
            rank = raw.get("rank")
            if not url or not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
                continue
            items.append({key: raw.get(key) for key in ("rank", "product_id", "title", "url", "price")} | {"url": url})
        if len(items) < 10:
            raise DLsiteRankingError(f"insufficient ranking items: {len(items)} (minimum 10)", self.http_status)
        return items
