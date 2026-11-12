"""Build an observation-only weekly report from saved ranking snapshots."""
from __future__ import annotations

import json
import re
import statistics
import tempfile
import unicodedata
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.metadata import meaningful_genres

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

def _circle_name(item):
 circle = item.get("circle") if isinstance(item.get("circle"), dict) else None
 return str((circle or {}).get("name") or "").strip()


def _metadata_analysis(market, top10, observations):
 genres, circles = {}, {}
 for key, item in market.items():
  names={str(x.get("name") or "").strip() for x in meaningful_genres(item.get("genres"))}
  for name in names: genres.setdefault(name, set()).add(key)
  name = _circle_name(item)
  if name: circles.setdefault(name, set()).add(key)
 def rows(values):
  return [{"name":name,"observed_products":len(keys),"top10_products":len(keys & top10)} for name,keys in sorted(values.items(),key=lambda row:(-len(row[1]),row[0]))[:10]]
 # Observation-based circle stats: appearances, best rank and flagship title.
 # A circle that only appears in observations (e.g. renamed since) is still counted.
 snapshots = {(kind, captured) for kind, captured, _ in observations}
 circle_snapshots = set()
 circle_stats = {}
 first_circle_at = None
 for kind, captured, item in observations:
  name = _circle_name(item)
  if not name: continue
  circle_snapshots.add((kind, captured))
  if first_circle_at is None or captured < first_circle_at: first_circle_at = captured
  rank = _rank(item)
  stats = circle_stats.setdefault(name, {"products": {}, "total_appearances": 0, "top10_appearances": 0})
  stats["total_appearances"] += 1
  if 0 < rank <= 10: stats["top10_appearances"] += 1
  product = stats["products"].setdefault(_key(item), {"appearances": 0, "best_rank": 0, "title": ""})
  product["appearances"] += 1
  if rank > 0 and (product["best_rank"] == 0 or rank < product["best_rank"]):
   product["best_rank"] = rank
   product["title"] = item.get("title", "")
 def circle_rows():
  rows_out = []
  for name in set(circles) | set(circle_stats):
   stats = circle_stats.get(name, {"products": {}, "total_appearances": 0, "top10_appearances": 0})
   keys = circles.get(name, set()) | set(stats["products"])
   best_rank = min((p["best_rank"] for p in stats["products"].values() if p["best_rank"] > 0), default=0)
   flagship = None
   for key, p in stats["products"].items():
    if p["best_rank"] <= 0: continue
    candidate = (p["best_rank"], -p["appearances"], key)
    if flagship is None or candidate < flagship[0]: flagship = (candidate, p["title"], p["best_rank"])
   rows_out.append({"name": name, "observed_products": len(keys), "top10_products": len(keys & top10),
                    "total_appearances": stats["total_appearances"], "best_rank": best_rank,
                    "top10_appearances": stats["top10_appearances"],
                    "flagship_title": flagship[1] if flagship else "",
                    "flagship_best_rank": flagship[2] if flagship else 0})
  rows_out.sort(key=lambda r: (-r["top10_appearances"], -r["total_appearances"], r["best_rank"] or 10 ** 9,
                               -r["observed_products"], r["name"]))
  return rows_out[:10]
 circle_coverage = {"snapshots_with_circle": len(circle_snapshots), "total_snapshots": len(snapshots),
                    "coverage_share": _percent(len(circle_snapshots), len(snapshots)),
                    "first_circle_snapshot": first_circle_at.isoformat() if first_circle_at else None}
 release_keys={key for key,item in market.items() if item.get("release_date")}
 new_releases=set()
 for _,captured,item in observations:
  try: released=datetime.fromisoformat(str(item.get("release_date"))).date()
  except (TypeError, ValueError): continue
  if timedelta(0) <= captured.date()-released <= timedelta(days=7): new_releases.add(_key(item))
 total=len(market)
 genre_price_summary=[]
 for row in rows(genres):
  values=[item.get("price") for key,item in market.items() if key in genres[row["name"]]
          and isinstance(item.get("price"),int) and not isinstance(item.get("price"),bool) and item["price"] > 0]
  genre_price_summary.append({"name":row["name"],"product_count":row["observed_products"],
                              "median_price":round(statistics.median(values)) if values else 0})
 return {"top_genres":rows(genres),"top_circles":circle_rows(),"new_release_products":len(new_releases),
  "new_release_share":_percent(len(new_releases),len(release_keys)),
  "new_release_top10_products":len(new_releases & top10),"genre_price_summary":genre_price_summary,
  "circle_coverage": circle_coverage,
  "metadata_coverage":{"genre":sum(bool(x.get('genres')) for x in market.values()),
   "meaningful_genre":sum(bool(meaningful_genres(x.get('genres'))) for x in market.values()),
   "circle":sum(bool(x.get('circle')) for x in market.values()),"release_date":len(release_keys),"total_products":total}}


def _biggest_movers(observations, limit=10):
 """Return the largest observed rises, once per work and ranking period."""
 movers = {}
 for kind, captured, item in observations:
  change = int(item.get("rank_change") or 0)
  if change <= 0: continue
  identity = (kind, _key(item)); current = movers.get(identity)
  candidate = {"id": identity[1], "title": item.get("title", ""), "ranking_type": kind,
               "rank_change": change, "current_rank": _rank(item),
               "trend_score": item.get("trend_score"),
               "observed_at": captured.isoformat()}
  if current is None or (change, -_rank(item), captured) > (current[0], -current[1]["current_rank"], current[2]):
   movers[identity] = (change, candidate, captured)
 return [row[1] for row in sorted(movers.values(), key=lambda row: (-row[0], row[1]["current_rank"], row[1]["id"], row[1]["ranking_type"]))[:limit]]


def _stability_analysis(observations, top_stays, total_snapshots):
 """Persistence and stability indicators from per-work rank trajectories.

 Stable TOP: a work in TOP10 in at least half of the week's snapshots.
 Rise persistence: for each biggest rise, whether the work was still in
 TOP10 in the latest later snapshot (持続), had dropped out (一過性), or
 has no later snapshot to judge from (判定保留). Observation only.
 """
 trajectories = {}
 for kind, captured, item in observations:
  key = _key(item)
  if not key: continue
  trajectories.setdefault(key, []).append((captured, _rank(item)))
 for rows in trajectories.values(): rows.sort(key=lambda row: row[0])
 stable = []
 for row in top_stays:
  if row["observation_rate"] < 50: continue
  ranks = [rank for _, rank in trajectories.get(row["id"], []) if rank > 0]
  latest = trajectories.get(row["id"], [(None, 0)])[-1][1]
  stable.append({"id": row["id"], "title": row["title"],
                 "top10_snapshots": row["top10_snapshots"], "total_snapshots": total_snapshots,
                 "observation_rate": row["observation_rate"],
                 "best_rank": min(ranks) if ranks else 0, "latest_rank": latest})
 stable.sort(key=lambda x: (-x["observation_rate"], x["best_rank"] or 10 ** 9, x["id"]))
 persistence = []
 for mover in _biggest_movers(observations):
  traj = trajectories.get(mover["id"], [])
  try: rise_at = datetime.fromisoformat(mover["observed_at"])
  except (TypeError, ValueError): rise_at = None
  later = [row for row in traj if rise_at is None or row[0] > rise_at]
  peak_rank = mover["current_rank"]
  if not later:
   latest_rank = traj[-1][1] if traj else 0
   latest_at = traj[-1][0].isoformat() if traj else None
   judgment = "判定保留"
  else:
   latest_rank, latest_at = later[-1][1], later[-1][0].isoformat()
   judgment = "持続" if 0 < latest_rank <= 10 else "一過性"
  persistence.append({"id": mover["id"], "title": mover["title"], "ranking_type": mover["ranking_type"],
                      "rank_change": mover["rank_change"], "peak_rank": peak_rank,
                      "peak_observed_at": mover["observed_at"], "latest_rank": latest_rank,
                      "latest_observed_at": latest_at,
                      "rank_after_rise": latest_rank - peak_rank if latest_rank and peak_rank else 0,
                      "persistence": judgment, "trend_score": mover.get("trend_score")})
 return {"snapshot_count": total_snapshots, "stable_top_products": stable,
         "rise_persistence": persistence}


def _genre_price_analysis(market, observations, top10, total_snapshots):
 """Genre x price cross-analysis from observations only.

 by_genre: per-genre average/median latest rank, TOP10 share, rise rate
 (share of observations with a positive rank change) and mean rank change.
 by_price_bucket: per-bucket product counts, TOP10 share and TOP10
 retention rate (mean per-product TOP10 observation rate).
 """
 by_key = {}
 for _, _, item in observations:
  key = _key(item)
  if key: by_key.setdefault(key, []).append(item)
 genre_keys = {}
 for key, item in market.items():
  for name in {str(x.get("name") or "").strip() for x in meaningful_genres(item.get("genres"))}:
   genre_keys.setdefault(name, set()).add(key)
 def genre_rows():
  rows = []
  for name, keys in genre_keys.items():
   ranks = [_rank(market[k]) for k in keys if _rank(market[k]) > 0]
   changes = [int(item.get("rank_change") or 0) for k in keys for item in by_key.get(k, [])]
   top = keys & top10
   rows.append({"name": name, "product_count": len(keys),
                "average_rank": round(statistics.mean(ranks)) if ranks else 0,
                "median_rank": round(statistics.median(ranks)) if ranks else 0,
                "top10_products": len(top), "top10_share": _percent(len(top), len(keys)),
                "rise_rate": _percent(sum(c > 0 for c in changes), len(changes)),
                "average_rank_change": round(statistics.mean(changes)) if changes else 0})
  rows.sort(key=lambda r: (-r["product_count"], r["name"]))
  return rows[:10]
 buckets = []
 for label, low, high in PRICE_BUCKETS:
  keys = {k for k, x in market.items() if isinstance(x.get("price"), int)
          and not isinstance(x.get("price"), bool) and low <= x["price"] and (high is None or x["price"] <= high)}
  top = keys & top10
  ranks = [_rank(market[k]) for k in keys if _rank(market[k]) > 0]
  rates = [_percent(sum(0 < _rank(item) <= 10 for item in by_key.get(k, [])), total_snapshots) for k in keys]
  buckets.append({"label": label, "product_count": len(keys),
                  "top10_count": len(top), "top10_share": _percent(len(top), len(keys)),
                  "top10_retention_rate": round(statistics.mean(rates)) if rates else 0,
                  "average_rank": round(statistics.mean(ranks)) if ranks else 0})
 return {"by_genre": genre_rows(), "by_price_bucket": buckets}


LAUNCH_TYPES = ("発売直後TOP入り型", "じわじわ上昇型", "一過性型", "判定保留")


def _launch_pattern_analysis(observations):
 """Launch-pattern classification for new releases from rank trajectories.

 Candidates are works first observed within 7 days of their release_date.
 発売直後TOP入り型: already TOP10 at first observation within 2 days of release.
 じわじわ上昇型: started outside TOP10, climbed 10+ ranks and ended in TOP10.
 一過性型: reached TOP10 exactly once, then dropped out.
 判定保留: anything else (e.g. never reached TOP10, single observation).
 Observation only; no sales or causal claims.
 """
 trajectories = {}
 for kind, captured, item in observations:
  key = _key(item)
  if not key: continue
  trajectories.setdefault(key, []).append((captured, item))
 products = []
 for key, rows in trajectories.items():
  rows.sort(key=lambda row: row[0])
  released = None
  for _, item in rows:
   try: released = datetime.fromisoformat(str(item.get("release_date"))).date()
   except (TypeError, ValueError): continue
   if released: break
  if released is None: continue
  first_seen = rows[0][0]
  if not timedelta(0) <= first_seen.date() - released <= timedelta(days=7): continue
  ranks = [_rank(item) for _, item in rows if _rank(item) > 0]
  if not ranks: continue
  first_rank, best_rank, latest_rank = ranks[0], min(ranks), ranks[-1]
  top10_hits = sum(rank <= 10 for rank in ranks)
  first_top10_at = next((captured for captured, item in rows if 0 < _rank(item) <= 10), None)
  days_to_top10 = (first_top10_at.date() - released).days if first_top10_at else None
  if first_rank <= 10 and (first_seen.date() - released).days <= 2:
   launch_type = "発売直後TOP入り型"
  elif first_rank > 10 and best_rank <= 10 and latest_rank <= 10 and first_rank - best_rank >= 10:
   launch_type = "じわじわ上昇型"
  elif best_rank <= 10 and latest_rank > 10 and top10_hits == 1:
   launch_type = "一過性型"
  else:
   launch_type = "判定保留"
  products.append({"id": key, "title": rows[-1][1].get("title", ""), "release_date": released.isoformat(),
                   "launch_type": launch_type, "first_rank": first_rank, "best_rank": best_rank,
                   "latest_rank": latest_rank, "days_to_top10": days_to_top10,
                   "top10_snapshots": top10_hits, "total_snapshots": len(ranks)})
 order = {name: index for index, name in enumerate(LAUNCH_TYPES)}
 products.sort(key=lambda row: (order[row["launch_type"]], row["best_rank"] or 10 ** 9, row["id"]))
 by_type = {name: sum(row["launch_type"] == name for row in products) for name in LAUNCH_TYPES}
 return {"new_release_products": len(products), "by_type": by_type, "products": products}


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


def _normalize_title(title):
 """Normalize a title for cross-platform matching.

 NFKC + strip ／[]（）() + whitespace removal + lowercase. This is the
 normalization used for the measured 4/20 (20%) FANZA x DLsite match rate;
 there are no shared IDs between the platforms, so titles are the only bridge.
 """
 text = unicodedata.normalize("NFKC", str(title or ""))
 text = re.sub(r"[／\[\]()（）]", "", text)
 return re.sub(r"\s+", "", text).lower()


def _snapshots_dlsite(start, end, dlsite_dir):
 """Read DLsite snapshots for the week.

 DLsite history is laid out as history/YYYY-MM-DD/*.json (one snapshot per
 file), unlike FANZA's history/YYYY-MM-DD.json (one file per day holding a
 list of snapshots). Each file is a single snapshot dict with fetched_at +
 items. Items get key = product_id so the shared helpers (_key, _rank,
 _biggest_movers) work unchanged.
 """
 found = []
 for path in sorted((Path(dlsite_dir) / "history").glob("*/*.json")):
  snapshot = _read(path)
  if not isinstance(snapshot, dict): continue
  try: captured = datetime.fromisoformat(snapshot["fetched_at"]).astimezone(JST)
  except (KeyError, TypeError, ValueError): continue
  if not (start <= captured <= end and isinstance(snapshot.get("items"), list)): continue
  items = []
  for item in snapshot["items"]:
   if not isinstance(item, dict): continue
   item = dict(item)
   if not item.get("key"): item["key"] = item.get("product_id", "")
   items.append(item)
  found.append((captured, items))
 return sorted(found, key=lambda row: row[0])


def _dlsite_analysis(observations, total_snapshots):
 """Phase A: DLsite-only weekly aggregation, kept separate from FANZA.

 Reuses the FANZA observation-rate and biggest-mover helpers on the
 DLsite-only observation list so FANZA aggregates are never polluted.
 """
 products = {}
 top10 = set()
 for _, _, item in observations:
  key = _key(item)
  if not key: continue
  products[key] = item
  if 0 < _rank(item) <= 10: top10.add(key)
 top_stays = []
 for key in top10:
  hits = sum(0 < _rank(item) <= 10 for _, _, item in observations if _key(item) == key)
  top_stays.append({"id": key, "title": products[key].get("title", ""), "top10_snapshots": hits,
                    "observation_rate": _percent(hits, total_snapshots)})
 top_stays.sort(key=lambda x: (-x["top10_snapshots"], x["id"]))
 prices = [int(x.get("price")) for x in products.values()
           if isinstance(x.get("price"), int) and not isinstance(x.get("price"), bool) and x["price"] >= 0]
 buckets = []
 for label, low, high in PRICE_BUCKETS:
  matches = {k for k, x in products.items() if isinstance(x.get("price"), int)
             and not isinstance(x.get("price"), bool) and low <= x["price"] and (high is None or x["price"] <= high)}
  buckets.append({"label": label, "count": len(matches), "top10_count": len(matches & top10)})
 return {"snapshot_count": total_snapshots, "unique_products": len(products),
         "top10_stays": top_stays[:10],
         "biggest_movers": _biggest_movers(observations),
         "price_analysis": {"average_price": round(statistics.mean(prices)) if prices else 0,
                            "median_price": round(statistics.median(prices)) if prices else 0,
                            "price_buckets": buckets},
         "new_entries": sum(x.get("status") == "new" for _, _, x in observations),
         "reentries": sum(x.get("status") == "reentry" for _, _, x in observations)}


def _cross_platform(fanza_observations, dlsite_observations):
 """Phase B: small FANZA x DLsite cross table by normalized title.

 Rows cover works that reached TOP10 on both platforms during the week;
 ranks are the latest observed rank per platform. match_rate is the share
 of DLsite weekly titles matched to FANZA. Title matching can mis-match
 same-name works, so articles must note it is title-based matching.
 """
 def latest_by_title(rows):
  latest = {}
  for _, captured, item in rows:
   title = _normalize_title(item.get("title", ""))
   if not title: continue
   if title not in latest or captured >= latest[title][0]:
    latest[title] = (captured, _rank(item), item.get("title", ""))
  return latest
 def top10_days(rows):
  days = {}
  for _, captured, item in rows:
   title = _normalize_title(item.get("title", ""))
   if title and 0 < _rank(item) <= 10: days.setdefault(title, set()).add(captured.date())
  return days
 fanza_latest = latest_by_title(fanza_observations)
 dlsite_latest = latest_by_title(dlsite_observations)
 fanza_days = top10_days(fanza_observations)
 dlsite_days = top10_days(dlsite_observations)
 matched = set(fanza_latest) & set(dlsite_latest)
 rows = []
 for title in matched:
  if title not in fanza_days or title not in dlsite_days: continue
  rows.append({"title": dlsite_latest[title][2] or fanza_latest[title][2],
               "fanza_rank": fanza_latest[title][1], "dlsite_rank": dlsite_latest[title][1],
               "fanza_top10_snapshots": len(fanza_days[title]),
               "dlsite_top10_snapshots": len(dlsite_days[title]),
               "both_top10_days": len(fanza_days[title] & dlsite_days[title])})
 rows.sort(key=lambda row: (row["fanza_rank"] or 10 ** 9, row["dlsite_rank"] or 10 ** 9, row["title"]))
 return {"matched_products": len(matched),
         "match_rate": _percent(len(matched), len(dlsite_latest)),
         "rows": rows}


def _snapshots(kind, start, end, fanza_dir):
 found = []
 for path in sorted((fanza_dir / kind / "history").glob("*.json")):
  for snapshot in _read(path):
   try: captured = datetime.fromisoformat(snapshot["fetched_at"]).astimezone(JST)
   except (KeyError, TypeError, ValueError): continue
   if start <= captured <= end and isinstance(snapshot.get("items"), list): found.append((captured, snapshot["items"]))
 return sorted(found, key=lambda row: row[0])


def generate_weekly_report(now=None, fanza_dir=FANZA_DIR, report_dir=REPORT_DIR, pages_dir=PAGES_DIR, dlsite_dir=None):
 now = now or datetime.now(JST); start, end = week_bounds(now)
 api_rows=_snapshots("api",start,end,Path(fanza_dir)); api_mode=bool(api_rows)
 series = {"api":api_rows} if api_mode else {kind: _snapshots(kind, start, end, Path(fanza_dir)) for kind in ("1h", "24h")}
 observations = [(kind, captured, item) for kind, snapshots in series.items() for captured, items in snapshots for item in items if _key(item)]
 dlsite_dir = Path(dlsite_dir) if dlsite_dir is not None else Path(fanza_dir).parent / "dlsite"
 dlsite_rows = _snapshots_dlsite(start, end, dlsite_dir)
 dlsite_observations = [("dlsite", captured, item) for captured, items in dlsite_rows for item in items if _key(item)]
 dlsite_analysis = _dlsite_analysis(dlsite_observations, len(dlsite_rows))
 cross_platform = _cross_platform(observations, dlsite_observations)
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
 total_snapshots = sum(len(x) for x in series.values())
 for key in top10:
  hits = sum(0 < _rank(item) <= 10 for _, _, item in observations if _key(item) == key)
  top_stays.append({"id": key, "title": products[key].get("title", ""), "top10_snapshots": hits,
                    "observation_rate": _percent(hits, total_snapshots)})
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
 metadata = _metadata_analysis(market,top10,observations) if api_mode else {"top_genres":[],"top_circles":[],"new_release_products":0,"new_release_share":0,"new_release_top10_products":0,"genre_price_summary":[],"circle_coverage":{"snapshots_with_circle":0,"total_snapshots":0,"coverage_share":0,"first_circle_snapshot":None},"metadata_coverage":{"genre":0,"meaningful_genre":0,"circle":0,"release_date":0,"total_products":len(market)}}
 if api_mode and metadata["top_genres"] and len(insights)<3: insights.append(f"APIランキングでは『{metadata['top_genres'][0]['name']}』タグ作品を{metadata['top_genres'][0]['observed_products']}作品観測しました。")
 stability = _stability_analysis(observations, top_stays, total_snapshots)
 genre_price = _genre_price_analysis(market, observations, top10, total_snapshots)
 launch_pattern = _launch_pattern_analysis(observations)
 if stability["stable_top_products"] and len(insights) < 3:
  top = stability["stable_top_products"][0]
  insights.append(f"『{top['title']}』は今週のスナップショットの{top['observation_rate']}%でTOP10に残りました。")
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
  "stability_analysis": stability,
  "genre_price_analysis": genre_price,
  "launch_pattern_analysis": launch_pattern,
  "dlsite_analysis": dlsite_analysis,
  "cross_platform": cross_platform,
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
