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

def _metadata_analysis(market, top10, observations):
 genres, circles = {}, {}
 for key, item in market.items():
  names={str(x.get("name") or "").strip() for x in (item.get("genres") or []) if isinstance(x,dict)}-{""}
  for name in names: genres.setdefault(name, set()).add(key)
  circle=item.get("circle") if isinstance(item.get("circle"),dict) else None
  name=str((circle or {}).get("name") or "").strip()
  if name: circles.setdefault(name,set()).add(key)
 def rows(values):
  return [{"name":name,"observed_products":len(keys),"top10_products":len(keys & top10)} for name,keys in sorted(values.items(),key=lambda row:(-len(row[1]),row[0]))[:10]]
 release_keys={key for key,item in market.items() if item.get("release_date")}
 new_releases=set()
 for _,captured,item in observations:
  try: released=datetime.fromisoformat(str(item.get("release_date"))).date()
  except ValueError: continue
  if timedelta(0) <= captured.date()-released <= timedelta(days=7): new_releases.add(_key(item))
 total=len(market)
 return {"top_genres":rows(genres),"top_circles":rows(circles),"new_release_products":len(new_releases),
  "new_release_share":_percent(len(new_releases),len(release_keys)),"metadata_coverage":{"genre":sum(bool(x.get('genres')) for x in market.values()),"circle":sum(bool(x.get('circle')) for x in market.values()),"release_date":len(release_keys),"total_products":total}}


def _biggest_movers(observations, limit=10):
 """Return the largest observed rises, once per work and ranking period."""
 movers = {}
 for kind, captured, item in observations:
  change = int(item.get("rank_change") or 0)
  if change <= 0: continue
  identity = (kind, _key(item)); current = movers.get(identity)
  candidate = {"id": identity[1], "title": item.get("title", ""), "ranking_type": kind,
               "rank_change": change, "current_rank": _rank(item),
               "observed_at": captured.isoformat()}
  if current is None or (change, -_rank(item), captured) > (current[0], -current[1]["current_rank"], current[2]):
   movers[identity] = (change, candidate, captured)
 return [row[1] for row in sorted(movers.values(), key=lambda row: (-row[0], row[1]["current_rank"], row[1]["id"], row[1]["ranking_type"]))[:limit]]


def _creator_insights(overview, price, sale, api_mode=False):
 """Create at most three deterministic observations without causal claims."""
 insights = []
 largest = overview.get("max_rank_rise_api",0) if api_mode else max(overview["max_rank_rise_1h"], overview["max_rank_rise_24h"])
 if largest:
  period = "API" if api_mode else "1H" if overview["max_rank_rise_1h"] >= overview["max_rank_rise_24h"] else "24H"
  insights.append(f"今週の最大上昇は{period}ランキングで+{largest}でした。")
 if api_mode and overview["top10_unique_products"]:
  insights.append(f"APIランキング上位で{overview['top10_unique_products']}作品を観測しました。")
 if overview["new_entries"] or overview["reentries"]:
  insights.append(f"NEWを{overview['new_entries']}件、REENTRYを{overview['reentries']}件観測しました。")
 if overview["cross_trend_events"]:
  insights.append(f"1Hの上昇後に24Hでも上昇したCROSSを{overview['cross_trend_events']}件観測しました。")
 elif sale["sale_product_count"]:
  insights.append(f"観測作品のSALE作品比率は{sale['sale_share']}%でした。")
 elif price["median_price"]:
  insights.append(f"観測作品の価格中央値は¥{price['median_price']:,}でした。")
 return insights[:3]


def _x_post_text(status, overview, price, sale, insights):
 heading = "今週途中の暫定集計だよ〜！" if status == "PARTIAL" else "1週間のランキングまとめたよ〜！"
 largest = max(overview.get("max_rank_rise_api",0),overview["max_rank_rise_1h"], overview["max_rank_rise_24h"])
 highlight = insights[-1] if insights else "今週もランキングの動きを観測しました。"
 return ("📊 今週のFANZA同人トレンド\n\n"
         f"{heading}\n\n"
         f"🔥 最大上昇 +{largest}\n"
         f"🆕 NEW {overview['new_entries']}件\n"
         f"🔄 REENTRY {overview['reentries']}件\n"
         f"📡 CROSS {overview['cross_trend_events']}件\n"
         f"💸 SALE作品比率 {sale['sale_share']}%\n"
         f"💰 中央価格 ¥{price['median_price']:,}\n\n"
         f"{highlight}ちょい注目だね👀\n\n"
         "※RankIdle観測データによる集計")


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
 api_rows=_snapshots("api",start,end,Path(fanza_dir)); api_mode=bool(api_rows)
 series = {"api":api_rows} if api_mode else {kind: _snapshots(kind, start, end, Path(fanza_dir)) for kind in ("1h", "24h")}
 observations = [(kind, captured, item) for kind, snapshots in series.items() for captured, items in snapshots for item in items if _key(item)]
 products = {}; top10 = set()
 for kind, captured, item in observations:
  key = _key(item); products[key] = item
  if 0 < _rank(item) <= 10: top10.add(key)
 # Prefer the latest 24H observation for price/sale statistics and count each work once.
 market = {}
 for captured, items in [row for snapshots in series.values() for row in snapshots]:
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
 hourly_rises = [(at, _key(x)) for at, items in series.get("1h",[]) for x in items if int(x.get("rank_change") or 0) > 0]
 for at, items in series.get("24h",[]):
  daily = {_key(x) for x in items if int(x.get("rank_change") or 0) > 0}
  propagation.update(key for earlier, key in hourly_rises if earlier <= at and key in daily)
 days = {captured.date() for snapshots in series.values() for captured, _ in snapshots}
 expected_days = min(7, (min(now.astimezone(JST), end).date() - start.date()).days + 1)
 complete = expected_days == 7 and len(days) == 7 and all(series.values())
 overview = {"unique_products": len(products), "top10_unique_products": len(top10), "new_entries": len(entries),
   "reentries": len(reentries), "cross_trend_events": len(propagation),
   "max_rank_rise_1h": max([int(x.get("rank_change") or 0) for _, items in series.get("1h",[]) for x in items] + [0]),
   "max_rank_rise_24h": max([int(x.get("rank_change") or 0) for _, items in series.get("24h",[]) for x in items] + [0]),
   "max_rank_rise_api": max([int(x.get("rank_change") or 0) for _, items in series.get("api",[]) for x in items] + [0])}
 price_analysis = {"average_price": round(statistics.mean(prices)) if prices else 0, "median_price": round(statistics.median(prices)) if prices else 0,
   "top10_average_price": round(statistics.mean(top_prices)) if top_prices else 0, "top10_median_price": round(statistics.median(top_prices)) if top_prices else 0, "price_buckets": buckets}
 sale_analysis = {"sale_product_count": len(sales), "sale_share": _percent(len(sales), len(market)), "top10_sale_count": len(top_sales),
   "top10_sale_share": _percent(len(top_sales), len(top10)), "average_discount_rate": round(statistics.mean(discounts)) if discounts else 0,
   "max_discount_rate": max(discounts + [0]), "discount_buckets": {"under_20": sum(0 < x < 20 for x in discounts), "20_29": sum(20 <= x < 30 for x in discounts), "30_49": sum(30 <= x < 50 for x in discounts), "50_plus": sum(x >= 50 for x in discounts)}}
 status = "COMPLETE" if complete else "PARTIAL"
 insights = _creator_insights(overview, price_analysis, sale_analysis,api_mode)
 metadata = _metadata_analysis(market,top10,observations) if api_mode else {"top_genres":[],"top_circles":[],"new_release_products":0,"new_release_share":0,"metadata_coverage":{"genre":0,"circle":0,"release_date":0,"total_products":len(market)}}
 if api_mode and metadata["top_genres"] and len(insights)<3: insights.append(f"APIランキングでは『{metadata['top_genres'][0]['name']}』タグ作品を{metadata['top_genres'][0]['observed_products']}作品観測しました。")
 stable_top10 = top_stays[:10]
 payload = {
  "week_start": start.date().isoformat(), "week_end": end.date().isoformat(),
  "generated_at": now.astimezone(JST).replace(microsecond=0).isoformat(), "data_status": status,
  "observed_days": len(days), "expected_days": expected_days,
  "snapshot_counts": {kind: len(rows) for kind, rows in series.items()},
  "ranking_source": "api" if api_mode else "legacy",
  "market_overview": overview,
  "price_analysis": price_analysis,
  "sale_analysis": sale_analysis,
  **metadata,
  "ranking_behavior": {"top10_entry_events": sum(_rank(x) <= 10 and (x.get("previous_rank") is None or int(x.get("previous_rank") or 0) > 10) for _, _, x in observations),
   "large_rise_5_plus": sum(x >= 5 for x in rises), "large_rise_10_plus": sum(x >= 10 for x in rises), "new_entry_events": len(entries), "reentry_events": len(reentries)},
  "biggest_movers": _biggest_movers(observations),
  "creator_insights": insights,
  "x_post_text": _x_post_text(status, overview, price_analysis, sale_analysis, insights),
  "stable_top10": stable_top10,
  # Kept while deployed Pages clients transition to the specification name above.
  "top10_stays": stable_top10,
  "methodology_note": "販売数・売上ではなく、保存されたランキングスナップショット内の観測結果です。"
 }
 for directory in (Path(report_dir), Path(pages_dir)):
  _write(directory / f"{payload['week_start']}.json", payload); _write(directory / "latest.json", payload)
 return payload
