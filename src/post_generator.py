from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def post_text(item: dict[str, Any], ranking_type: str = "24h") -> str:
    title, rank, previous = item["title"], item["current_rank"], item.get("previous_rank")
    label = "1時間ランキング" if ranking_type == "1h" else "24時間ランキング"
    product = f'\n\n作品ページ👇\n{item["url"]}' if item.get("url") else ""
    if item["status"] in ("new", "reentry"):
        return f'【FANZA {label}】\n🆕 NEW ENTRY\n\n「{title}」\n\n初登場 {rank}位\n\nRankIdleが新規ランクインを検知しました📡{product}\n\n#FANZA #同人'
    if rank <= 10 < (previous or 999):
        return f'【FANZA {label}】\n🔥 TOP10入り\n\n「{title}」\n\n#{previous} → #{rank}{product}\n\n#FANZA #同人'
    return f'【FANZA {label}】\n🔥 急上昇\n\n「{title}」\n\n#{previous} → #{rank}\n\n📈 +{item["rank_change"]}ランク{product}\n\n#FANZA #同人'


def generate_candidates(items, existing, now: datetime, cooldown_hours: int = 24, ranking_type: str = "24h"):
    cutoff = now - timedelta(hours=cooldown_hours); recent = {}
    for candidate in existing:
        try: recent[candidate["key"]] = datetime.fromisoformat(candidate["generated_at"])
        except (KeyError, ValueError): pass
    output = list(existing)
    for item in sorted(items, key=lambda x: x.get("trend_score", 0), reverse=True):
        if item.get("trend_score", 0) < 20: continue
        key = item["key"]; important = item["current_rank"] == 1 or item.get("rank_change", 0) >= 50 or (item["current_rank"] <= 10 < (item.get("previous_rank") or 999))
        if key in recent and recent[key] > cutoff and not important: continue
        output.append({"key": key, "title": item["title"], "url": item.get("url", ""), "ranking_type": ranking_type, "status": item.get("status"), "trend_score": item["trend_score"], "previous_rank": item.get("previous_rank"),
                       "current_rank": item["current_rank"], "rank_change": item.get("rank_change", 0), "text": post_text(item, ranking_type), "generated_at": now.isoformat()})
    return output[-200:]
