from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .base import RankingProvider

API_URL = "https://api.dmm.com/affiliate/v3/ItemList"
SITE = "FANZA"
# DMM Web Service's doujin service uses digital_doujin (not digital/videoa).
DOUJIN_SERVICE = "doujin"
DOUJIN_FLOOR = "digital_doujin"


def _price(item: dict[str, Any]) -> int:
    value = (item.get("prices") or {}).get("price", 0)
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def normalize_items(raw: Any, *, service: str, floor: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("FANZA API response has no items")

    normalized = []
    for rank, item in enumerate(raw, 1):
        content_id = str(item.get("content_id") or "").strip()
        if not content_id:
            raise RuntimeError("FANZA API item has no content_id")
        images = item.get("imageURL") or {}
        normalized.append(
            {
                "rank": rank,
                "id": content_id,
                "key": content_id,
                "title": str(item.get("title") or ""),
                "price": _price(item),
                "url": str(item.get("URL") or ""),
                "affiliate_url": str(item.get("affiliateURL") or ""),
                "image_url": str(images.get("large") or images.get("list") or images.get("small") or ""),
                "service": service,
                "floor": floor,
            }
        )
    return normalized


class FanzaApiProvider(RankingProvider):
    def __init__(self, *, hits: int | None = None, service: str | None = None, floor: str | None = None):
        requested_hits = hits if hits is not None else int(os.getenv("FANZA_HITS", "100"))
        self.hits = max(20, min(requested_hits, 100))
        self.service = service or os.getenv("FANZA_SERVICE", DOUJIN_SERVICE)
        self.floor = floor or os.getenv("FANZA_FLOOR", DOUJIN_FLOOR)

    def fetch(self) -> list[dict[str, Any]]:
        api_id = os.getenv("DMM_API_ID")
        affiliate_id = os.getenv("DMM_AFFILIATE_ID")
        if not api_id or not affiliate_id:
            raise RuntimeError("DMM_API_ID and DMM_AFFILIATE_ID are required")
        params = {
            "api_id": api_id,
            "affiliate_id": affiliate_id,
            "site": SITE,
            "service": self.service,
            "floor": self.floor,
            "hits": self.hits,
            "sort": "rank",
            "output": "json",
        }
        with urlopen(f"{API_URL}?{urlencode(params)}", timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("result") or {}
        if result.get("errors") or payload.get("errors"):
            raise RuntimeError("FANZA API returned an error")
        items = normalize_items(result.get("items"), service=self.service, floor=self.floor)
        if len(items) < 20:
            raise RuntimeError(f"FANZA API returned only {len(items)} items; at least 20 are required")
        return items
