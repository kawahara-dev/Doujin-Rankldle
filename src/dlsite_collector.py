"""Persist DLsite current/history snapshots without affecting FANZA state."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.collector import atomic_write, read_json
from src.providers.dlsite_ranking import DLsiteRankingError, DLsiteRankingProvider

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "dlsite"
DOCS_DIR = ROOT / "docs" / "data" / "dlsite"
JST = ZoneInfo("Asia/Tokyo")


def identity(items: list[dict]) -> list[tuple[str | None, int]]:
    return [(item.get("product_id"), item["rank"]) for item in items]


def seen_product_ids(history_dir: Path) -> set[str]:
    seen: set[str] = set()
    for path in history_dir.glob("*/*.json"):
        payload = read_json(path, {})
        seen.update(item["product_id"] for item in payload.get("items", []) if item.get("product_id"))
    return seen


def compare(items: list[dict], previous: list[dict], seen: set[str]) -> list[dict]:
    old = {item.get("product_id"): item["rank"] for item in previous if item.get("product_id")}
    result = []
    for raw in items:
        item = dict(raw)
        product_id = item.get("product_id")
        prior = old.get(product_id) if product_id else None
        if prior is None:
            status = "reentry" if product_id and product_id in seen else "new"
            change = None
        else:
            change = prior - item["rank"]
            status = "up" if change > 0 else "down" if change < 0 else "stay"
        # Without a stable product ID there is no safe long-term identity and no
        # NEW/REENTRY assertion should be made from a title or URL.
        if not product_id:
            status = None
        item.update(previous_rank=prior, rank_change=change, status=status)
        result.append(item)
    return result


def sync_docs(data_dir: Path = DATA_DIR, docs_dir: Path = DOCS_DIR) -> None:
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    shutil.copytree(data_dir, docs_dir)


def collect(provider=None, now: datetime | None = None, data_dir: Path = DATA_DIR,
            docs_dir: Path = DOCS_DIR) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST).replace(microsecond=0)
    stamp = now.isoformat()
    status_path = data_dir / "status.json"
    current_path = data_dir / "current.json"
    status = read_json(status_path, {})
    provider = provider or DLsiteRankingProvider()
    try:
        raw = provider.fetch()
        ranks = [item["rank"] for item in raw]
        if len(ranks) != len(set(ranks)):
            raise DLsiteRankingError("parser failure: duplicate ranks", provider.http_status)
        previous_payload = read_json(current_path, {})
        previous = previous_payload.get("items", [])
        duplicate = bool(previous) and identity(raw) == identity(previous)
        if not duplicate:
            items = compare(raw, previous, seen_product_ids(data_dir / "history"))
            payload = {"source": "dlsite", "ranking_type": "public_ranking", "category": "maniax",
                       "fetched_at": stamp, "items": items}
            atomic_write(current_path, payload)
            history = data_dir / "history" / now.date().isoformat() / f'{now.strftime("%Y-%m-%dT%H%M%S%z")}.json'
            atomic_write(history, payload)
        successful = int(status.get("total_successful_snapshots", 0)) + (0 if duplicate else 1)
        status = {"last_run": stamp, "last_success": stamp, "last_error": None,
                  "items": len(raw), "http_status": provider.http_status,
                  "total_successful_snapshots": successful, "duplicate": duplicate,
                  "warning": "partial ranking (expected 20)" if len(raw) < 20 else None}
        atomic_write(status_path, status)
        sync_docs(data_dir, docs_dir)
        print(f"DLsite: {len(raw)} items (duplicate={str(duplicate).lower()})")
        return status
    except Exception as exc:
        http_status = getattr(exc, "http_status", getattr(provider, "http_status", None))
        failed = {**status, "last_run": stamp, "last_error": str(exc), "http_status": http_status,
                  "duplicate": False}
        atomic_write(status_path, failed)
        sync_docs(data_dir, docs_dir)
        print(f"DLsite collection failed: {exc}")
        return failed


def main() -> int:
    status = collect()
    return 1 if status.get("last_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
