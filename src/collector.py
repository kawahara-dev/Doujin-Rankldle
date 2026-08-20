"""FANZA API または開発用モックからランキング商品を収集する。"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LATEST_PATH = DATA_DIR / "latest.json"
STATUS_PATH = DATA_DIR / "status.json"
API_URL = "https://api.dmm.com/affiliate/v3/ItemList"
JST = ZoneInfo("Asia/Tokyo")


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """同じディレクトリで置換し、書き込み途中の JSON を公開しない。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def read_status() -> dict[str, Any]:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_run": None, "total_runs": 0, "items_collected": 0}


def fetch_items() -> list[dict[str, Any]]:
    api_id = os.environ.get("DMM_API_ID", "").strip()
    affiliate_id = os.environ.get("DMM_AFFILIATE_ID", "").strip()

    params = {
        "api_id": api_id,
        "affiliate_id": affiliate_id,
        "site": "FANZA",
        "service": os.environ.get("FANZA_SERVICE", "digital"),
        "floor": os.environ.get("FANZA_FLOOR", "videoa"),
        "hits": min(int(os.environ.get("FANZA_HITS", "100")), 100),
        "sort": "rank",
        "output": "json",
    }
    with urlopen(f"{API_URL}?{urlencode(params)}", timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result", {})
    raw_items = result.get("items")
    if not isinstance(raw_items, list):
        raise RuntimeError(f"FANZA API の応答が不正です: {result.get('message', 'items がありません')}")

    items = []
    for rank, item in enumerate(raw_items, start=1):
        prices = item.get("prices") or {}
        raw_price = prices.get("price") or prices.get("price_min") or 0
        try:
            price = int(str(raw_price).replace(",", ""))
        except (TypeError, ValueError):
            price = 0
        items.append(
            {
                "id": str(item.get("content_id", "")),
                "title": str(item.get("title", "")),
                "price": price,
                "url": str(item.get("affiliateURL") or item.get("URL") or ""),
                "rank": rank,
            }
        )
    return items


def mock_items() -> list[dict[str, Any]]:
    """API 認証情報がない環境向けの安定したサンプルを返す。"""
    products = [
        ("モック作品：真夏のランキング", 1980),
        ("モック作品：放課後コレクション", 2480),
        ("モック作品：秘密のスタジオ", 2980),
        ("モック作品：週末スペシャル", 1480),
        ("モック作品：プライベートタイム", 3280),
    ]
    return [
        {"id": f"mock-{rank:03d}", "title": title, "price": price,
         "url": f"https://example.com/mock-products/{rank}", "rank": rank}
        for rank, (title, price) in enumerate(products, start=1)
    ]


def main() -> None:
    # API の取得・整形がすべて成功してから、既存ファイルを原子的に置換する。
    has_credentials = bool(
        os.environ.get("DMM_API_ID", "").strip()
        and os.environ.get("DMM_AFFILIATE_ID", "").strip()
    )
    mode = "live" if has_credentials else "mock"
    items = fetch_items() if has_credentials else mock_items()
    now = datetime.now(JST).replace(microsecond=0).isoformat()
    old_status = read_status()
    run_date = now[:10]
    runs_today = (
        int(old_status.get("runs_today", 0)) + 1
        if old_status.get("run_date") == run_date
        else 1
    )
    latest = {"updated_at": now, "items": items}
    status = {
        "last_run": now,
        "total_runs": int(old_status.get("total_runs", 0)) + 1,
        "items_collected": len(items),
        "run_date": run_date,
        "runs_today": runs_today,
        "mode": mode,
    }
    atomic_write(LATEST_PATH, latest)
    atomic_write(STATUS_PATH, status)
    print(f"{len(items)} 件を収集しました ({now}, mode={mode})")


if __name__ == "__main__":
    main()
