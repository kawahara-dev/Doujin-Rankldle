from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .base import RankingProvider

API_URL = "https://api.dmm.com/affiliate/v3/ItemList"


class FanzaApiProvider(RankingProvider):
    def fetch(self) -> list[dict[str, Any]]:
        params = {"api_id": os.environ["DMM_API_ID"], "affiliate_id": os.environ["DMM_AFFILIATE_ID"],
                  "site": "FANZA", "service": os.getenv("FANZA_SERVICE", "digital"),
                  "floor": os.getenv("FANZA_FLOOR", "videoa"), "hits": min(int(os.getenv("FANZA_HITS", "100")), 100),
                  "sort": "rank", "output": "json"}
        with urlopen(f"{API_URL}?{urlencode(params)}", timeout=30) as response:
            raw = json.loads(response.read().decode())["result"].get("items")
        if not isinstance(raw, list):
            raise RuntimeError("FANZA API response has no items")
        result = []
        for rank, item in enumerate(raw, 1):
            price = (item.get("prices") or {}).get("price", 0)
            try: price = int(str(price).replace(",", ""))
            except (ValueError, TypeError): price = 0
            result.append({"id": str(item.get("content_id", "")), "title": str(item.get("title", "")),
                           "price": price, "url": str(item.get("affiliateURL") or item.get("URL") or ""), "rank": rank})
        return result
