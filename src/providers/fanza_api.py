from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from .base import RankingProvider

API_URL = "https://api.dmm.com/affiliate/v3/ItemList"
SITE = "FANZA"
# DMM Web Service's doujin service uses digital_doujin (not digital/videoa).
DOUJIN_SERVICE = "doujin"
DOUJIN_FLOOR = "digital_doujin"


class DmmApiRequestError(RuntimeError):
    """An API failure whose text is safe to print in CI logs."""


def _redact(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def _error_details(body: bytes, secrets: tuple[str, ...]) -> str:
    """Return useful API error fields without echoing credentials or a URL."""
    text = body.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _redact(text.strip(), secrets) or "(empty response body)"

    def safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: safe(item)
                for key, item in value.items()
                if key.lower() not in {"api_id", "affiliate_id", "url", "request"}
            }
        if isinstance(value, list):
            return [safe(item) for item in value]
        if isinstance(value, str):
            return _redact(value, secrets)
        return value

    details: dict[str, Any] = {}
    for key in ("message", "errors"):
        if key in payload:
            details[key] = safe(payload[key])
    result = payload.get("result")
    if isinstance(result, dict):
        result_errors = {key: safe(result[key]) for key in ("message", "errors") if key in result}
        if result_errors:
            details["result"] = result_errors
    if not details:
        details = safe(payload)
    return json.dumps(details, ensure_ascii=False, separators=(",", ":"))


def request_json(api_url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call a DMM endpoint and raise a credential-safe error on HTTP failure."""
    secrets = (str(params.get("api_id") or ""), str(params.get("affiliate_id") or ""))
    try:
        with urlopen(f"{api_url}?{urlencode(params)}", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = _error_details(error.read(), secrets)
        raise DmmApiRequestError(
            f"DMM API request failed\nstatus: {error.code}\nresponse: {details}"
        ) from None


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
        payload = request_json(API_URL, params)
        result = payload.get("result") or {}
        if result.get("errors") or payload.get("errors"):
            raise RuntimeError("FANZA API returned an error")
        items = normalize_items(result.get("items"), service=self.service, floor=self.floor)
        if len(items) < 20:
            raise RuntimeError(f"FANZA API returned only {len(items)} items; at least 20 are required")
        return items
