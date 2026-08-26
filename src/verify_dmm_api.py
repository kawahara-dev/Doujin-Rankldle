from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .providers.fanza_api import DOUJIN_FLOOR, DOUJIN_SERVICE, FanzaApiProvider

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/verify/dmm_api_latest.json"
MANUAL = {"1h": ROOT / "data/fanza/1h/current.json", "24h": ROOT / "data/fanza/24h/current.json"}


def load_manual(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"manual ranking not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(f"manual ranking has no items: {path}")
    return items[:20]


def item_key(item: dict[str, Any]) -> str:
    return str(item.get("key") or item.get("content_id") or item.get("id") or "").strip()


def compare(api_items: list[dict[str, Any]], manual_items: list[dict[str, Any]]) -> dict[str, Any]:
    api = {item_key(x): int(x.get("rank", i)) for i, x in enumerate(api_items[:20], 1) if item_key(x)}
    manual = {item_key(x): int(x.get("rank", i)) for i, x in enumerate(manual_items[:20], 1) if item_key(x)}
    shared = api.keys() & manual.keys()
    exact = sum(api[key] == manual[key] for key in shared)
    differences = [abs(api[key] - manual[key]) for key in shared]
    denominator = len(api)
    return {
        "matched_products": len(shared),
        "overlap_rate": round(len(shared) / denominator * 100, 2) if denominator else 0.0,
        "exact_rank_matches": exact,
        "exact_rank_rate": round(exact / denominator * 100, 2) if denominator else 0.0,
        "average_rank_difference": round(sum(differences) / len(differences), 2) if differences else None,
    }


def classify(one_hour: dict[str, Any], day: dict[str, Any]) -> dict[str, str]:
    def score(value: dict[str, Any]) -> tuple[float, float]:
        average = value["average_rank_difference"]
        return value["overlap_rate"], -(average if average is not None else 999)

    best_name, best, other = ("1h", one_hour, day) if score(one_hour) > score(day) else ("24h", day, one_hour)
    if best["overlap_rate"] < 60:
        return {"likely_match": "neither", "confidence": "LOW"}
    best_avg = best["average_rank_difference"] or 0
    other_avg = other["average_rank_difference"] or 0
    if abs(best["overlap_rate"] - other["overlap_rate"]) < 10 and abs(best_avg - other_avg) <= 1:
        return {"likely_match": "uncertain", "confidence": "LOW"}
    confidence = "HIGH" if best["overlap_rate"] >= 80 and best_avg <= 2 else "MEDIUM"
    return {"likely_match": best_name, "confidence": confidence}


def run(*, provider: FanzaApiProvider | None = None, output: Path = OUTPUT) -> dict[str, Any]:
    provider = provider or FanzaApiProvider(hits=20)
    api_items = provider.fetch()[:20]
    if len(api_items) < 20:
        raise RuntimeError("verification requires at least 20 API items")
    comparisons = {name: compare(api_items, load_manual(path)) for name, path in MANUAL.items()}
    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "mode": "verify_dry_run",
        "request": {"site": "FANZA", "service": DOUJIN_SERVICE, "floor": DOUJIN_FLOOR, "sort": "rank", "hits": 20},
        "api_items": api_items,
        "api_vs_1h": comparisons["1h"],
        "api_vs_24h": comparisons["24h"],
        "summary": classify(comparisons["1h"], comparisons["24h"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return result


def main() -> None:
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(f"Verification artifact written to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
