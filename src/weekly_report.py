"""Build an observation-only weekly report from saved ranking snapshots."""
from __future__ import annotations

import json
import statistics
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
FANZA_DIR = ROOT / "data" / "fanza"
REPORT_DIR = ROOT / "data" / "reports" / "weekly"
PAGES_DIR = ROOT / "docs" / "data" / "reports" / "weekly"
PRICE_BUCKETS = (("〜499円", 0, 499), ("500〜999円", 500, 999),
                 ("1000〜1999円", 1000, 1999), ("2000〜2999円", 2000, 2999),
                 ("3000円〜", 3000, None))


def _read(path):
 try: return json.loads(path.read_text(encoding="utf-8"))
 except (OSError, json.JSONDecodeError): return []


def _write(path, payload):
 path.parent.mkdir(parents=True, exist_ok=True)
 with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
  json.dump(payload, f, ensure_ascii=False, indent=2); f.write("\n"); temporary = Path(f.name)
 temporary.replace(path)


def _key(item): return str(item.get("key") or item.get("id") or item.get("url", "")).split("?")[0]
def _rank(item): return int(item.get("current_rank", item.get("rank", 0)) or 0)
def _percent(part, whole): return round(part / whole * 100) if whole else 0


def week_bounds(now):
 local = now.astimezone(JST)
 start_date = local.date() - timedelta(days=local.weekday())
 return datetime.combine(start_date, time.min, JST), datetime.combine(start_date + timedelta(days=6), time.max, JST)


def _snapshots(kind, start, end, fanza_dir):
 found = []
 for path in sorted((fanza_dir / kind / "history").glob("*.json")):
  for snapshot in _read(path):
   try: captured = datetime.fromisoformat(snapshot["fetched_at"]).astimezone(JST)
   except (KeyError, TypeError, ValueError): continue
   if start <= captured <= end and isinstance(snapshot.get("items"), list): found.append((captured, snapshot["items"]))
 return sorted(found, key=lambda row: row[0])


def generate_weekly_report(now=None, fanza_dir=FANZA_DIR, report_dir=REPORT_DIR, pages_dir=PAGES_DIR):
 now = now or datetime.now(JST); start, end = week_bounds(now)
 series = {kind: _snapshots(kind, start, end, Path(fanza_dir)) for kind in ("1h", "24h")}
 observations = [(kind, captured, item) for kind, snapshots in series.items() for captured, items in snapshots for item in items if _key(item)]
 products = {}; top10 = set()
 for kind, captured, item in observations:
  key = _key(item); products[key] = item
  if 0 < _rank(item) <= 10: top10.add(key)
 # Prefer the latest 24H observation for price/sale statistics and count each work once.
 market = {}
 for captured, items in series["1h"] + series["24h"]:
  for item in items:
   if _key(item): market[_key(item)] = item
 prices = [int(x.get("price")) for x in market.values() if isinstance(x.get("price"), int) and not isinstance(x.get("price"), bool) and x["price"] >= 0]
 top_prices = [int(market[k]["price"]) for k in top10 if k in market and isinstance(market[k].get("price"), int)]
 sales = {k: x for k, x in market.items() if x.get("on_sale")}
 top_sales = top10 & sales.keys(); discounts = [int(x.get("discount_rate") or 0) for x in sales.values()]
 entries = [x for _, _, x in observations if x.get("status") == "new"]
 reentries = [x for _, _, x in observations if x.get("status") == "reentry"]
 rises = [int(x.get("rank_change") or 0) for _, _, x in observations]
 buckets = []
 for label, low, high in PRICE_BUCKETS:
  matches = {k for k, x in market.items() if isinstance(x.get("price"), int) and x["price"] >= low and (high is None or x["price"] <= high)}
  buckets.append({"label": label, "count": len(matches), "top10_count": len(matches & top10)})
 top_stays = []
 for key in top10:
  hits = sum(0 < _rank(item) <= 10 for _, _, item in observations if _key(item) == key)
  top_stays.append({"id": key, "title": products[key].get("title", ""), "top10_snapshots": hits,
                    "observation_rate": _percent(hits, sum(len(x) for x in series.values()))})
 top_stays.sort(key=lambda x: (-x["top10_snapshots"], x["id"]))
 # A propagation is a positive 1H move followed by a positive 24H move for the same work.
 propagation = set()
 hourly_rises = [(at, _key(x)) for at, items in series["1h"] for x in items if int(x.get("rank_change") or 0) > 0]
 for at, items in series["24h"]:
  daily = {_key(x) for x in items if int(x.get("rank_change") or 0) > 0}
  propagation.update(key for earlier, key in hourly_rises if earlier <= at and key in daily)
 days = {captured.date() for snapshots in series.values() for captured, _ in snapshots}
 expected_days = min(7, (min(now.astimezone(JST), end).date() - start.date()).days + 1)
 complete = expected_days == 7 and len(days) == 7 and all(series.values())
 payload = {
  "week_start": start.date().isoformat(), "week_end": end.date().isoformat(),
  "generated_at": now.astimezone(JST).replace(microsecond=0).isoformat(), "data_status": "COMPLETE" if complete else "PARTIAL",
  "observed_days": len(days), "expected_days": expected_days,
  "snapshot_counts": {kind: len(rows) for kind, rows in series.items()},
  "market_overview": {"unique_products": len(products), "top10_unique_products": len(top10), "new_entries": len(entries),
   "reentries": len(reentries), "cross_trend_events": len(propagation),
   "max_rank_rise_1h": max([int(x.get("rank_change") or 0) for _, items in series["1h"] for x in items] + [0]),
   "max_rank_rise_24h": max([int(x.get("rank_change") or 0) for _, items in series["24h"] for x in items] + [0])},
  "price_analysis": {"average_price": round(statistics.mean(prices)) if prices else 0, "median_price": round(statistics.median(prices)) if prices else 0,
   "top10_average_price": round(statistics.mean(top_prices)) if top_prices else 0, "top10_median_price": round(statistics.median(top_prices)) if top_prices else 0, "price_buckets": buckets},
  "sale_analysis": {"sale_product_count": len(sales), "sale_share": _percent(len(sales), len(market)), "top10_sale_count": len(top_sales),
   "top10_sale_share": _percent(len(top_sales), len(top10)), "average_discount_rate": round(statistics.mean(discounts)) if discounts else 0,
   "max_discount_rate": max(discounts + [0]), "discount_buckets": {"under_20": sum(0 < x < 20 for x in discounts), "20_29": sum(20 <= x < 30 for x in discounts), "30_49": sum(30 <= x < 50 for x in discounts), "50_plus": sum(x >= 50 for x in discounts)}},
  "ranking_behavior": {"top10_entry_events": sum(_rank(x) <= 10 and (x.get("previous_rank") is None or int(x.get("previous_rank") or 0) > 10) for _, _, x in observations),
   "large_rise_5_plus": sum(x >= 5 for x in rises), "large_rise_10_plus": sum(x >= 10 for x in rises), "new_entry_events": len(entries), "reentry_events": len(reentries)},
  "top10_stays": top_stays[:10],
  "methodology_note": "販売数・売上ではなく、保存されたランキングスナップショット内の観測結果です。"
 }
 for directory in (Path(report_dir), Path(pages_dir)):
  _write(directory / f"{payload['week_start']}.json", payload); _write(directory / "latest.json", payload)
 return payload
