from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def post_text(item: dict[str, Any]) -> str:
    title, rank, previous = item["title"], item["current_rank"], item.get("previous_rank")
    if item["status"] in ("new", "reentry"):
        return f'🆕 NEW ENTRY\n\n「{title}」\n\nFANZA同人ランキング\n初登場 {rank}位\n\nRankIdleが新規ランクインを検知しました📡\n\n#FANZA #同人'
    if rank <= 10 < (previous or 999):
        return f'🔥 TOP10入り\n\n「{title}」\n\n前回 {previous}位\n↓\n現在 {rank}位\n\nTOP10へランクアップ📈\n\n#FANZA #同人'
    return f'🔥 FANZA同人 急上昇\n\n「{title}」\n\n前回 {previous}位\n↓\n現在 {rank}位\n\n📈 +{item["rank_change"]}ランク\n\nRankIdleが今回の巡回で急上昇を検知しました📡\n\n#FANZA #同人'


def generate_candidates(items, existing, now: datetime, cooldown_hours: int = 24):
    cutoff = now - timedelta(hours=cooldown_hours); recent = {}
    for candidate in existing:
        try: recent[candidate["key"]] = datetime.fromisoformat(candidate["generated_at"])
        except (KeyError, ValueError): pass
    output = list(existing)
    for item in sorted(items, key=lambda x: x.get("trend_score", 0), reverse=True):
        if item.get("trend_score", 0) < 20: continue
        key = item["key"]; important = item["current_rank"] == 1 or item.get("rank_change", 0) >= 50 or (item["current_rank"] <= 10 < (item.get("previous_rank") or 999))
        if key in recent and recent[key] > cutoff and not important: continue
        output.append({"key": key, "title": item["title"], "trend_score": item["trend_score"], "previous_rank": item.get("previous_rank"),
                       "current_rank": item["current_rank"], "rank_change": item.get("rank_change", 0), "text": post_text(item), "generated_at": now.isoformat()})
    return output[-200:]
