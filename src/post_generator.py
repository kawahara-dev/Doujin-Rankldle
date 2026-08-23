from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any


COMMENT_TEMPLATES = {
    "cross": (
        "1Hだけじゃなく24H側でも動いてるのが気になる👀",
        "短期の上昇が24H側にも波及してるのがおもしろい📈",
        "両方のランキングで動きが出てきました。しばらく追いたいところ👀",
        "1Hと24Hがそろって上向き。ちょっと注目したい動き📡",
    ),
    "top10": (
        "短時間でTOP10まで入ってきたのが目を引く📈",
        "TOP10入りを確認。ここから定着するか気になるところ👀",
        "一気に上位帯まで来ました。この後の順位も追いたい📡",
        "TOP10の壁を突破。勢いが続くか観測中👀",
    ),
    "rise10": (
        "一気に二桁ランクアップ。かなり大きめの動き📈",
        "今回は順位が大きくジャンプ。次の更新も気になる👀",
        "短時間でかなり順位を上げています📡",
        "急に動きが強くなってきました。要観測👀",
    ),
    "rise5": (
        "じわっとではなく、しっかり順位を上げてきました📈",
        "今回の更新で目立つ上昇を確認👀",
        "上向きの動きが見えてきました📡",
        "少し勢いが出てきた感じ。次回も追います👀",
    ),
    "new": (
        "新しくランキング入り。まずはここから動きをチェック👀",
        "NEW ENTRYを検知。どこまで上がるか観測開始📡",
        "新顔がランクイン。次の順位変化が気になるところ👀",
        "今回からランキングに登場。しばらく追ってみます📈",
    ),
    "reentry": (
        "圏外から再びランキングへ。戻ってきました👀",
        "REENTRYを確認。ここから再浮上するか注目📡",
        "一度圏外から戻ってきた動きが気になるところ📈",
        "ランキングへ再登場。この後の伸びを観測します👀",
    ),
    "first": (
        "現在トップ。首位をどこまで維持するか注目👀",
        "1位をキープ中。上位の安定感が出ています📡",
        "現在ランキング首位。次回もトップを守れるか観測📈",
        "首位での推移を確認。次の更新まで観測します👀",
    ),
    "sale_top10": (
        "セール中にTOP10入り。価格と順位の動きが重なっています👀",
        "割引中かつ上位ランク。ちょっと気になる組み合わせ📡",
        "SALE中に上位をキープ。この後も観測します💸",
        "セール対象がTOP10圏内。順位の推移も追います👀",
    ),
    "sale50": (
        "半額以上の割引。ランキングとの組み合わせも気になる💸",
        "かなり大きめの値引き。順位への影響も追いたいところ👀",
        "50%OFF以上を確認。セール中の動きに注目📡",
        "半額以上でセール中。ランキングの変化を観測します💸",
    ),
    "sale30": (
        "割引率も高め。セール中の順位変化が気になります👀",
        "30%OFF以上でランクイン。動きを追いたいところ💸",
        "セールとランキング上昇が重なるか観測中📈",
        "30%OFF以上を確認。順位への動きも追います📡",
    ),
    "sale": (
        "セール対象を確認。ランキングの推移も観測します💸",
        "割引中のランキング変化を追いたいところ👀",
        "SALE中の順位を引き続きチェックします📡",
        "価格が動いている間の順位変化に注目です📈",
    ),
    "normal": (
        "今回の順位を確認。次の更新まで動きを追います👀",
        "ランキングの推移を引き続き観測します📡",
        "現在の順位からどう動くかチェックします📈",
        "順位に動きが出るか、次回も確認します👀",
    ),
}


def generate_comment(item: dict[str, Any], ranking_type: str, signal_type: str | None = None) -> str:
    """Return a deterministic, ranking-data-only note for one event."""
    rank = int(item.get("current_rank") or item.get("rank") or 0)
    previous = item.get("previous_rank")
    change = int(item.get("rank_change") or 0)
    status = item.get("status")
    if signal_type == "sale":
        discount = int(item.get("discount_rate") or 0)
        kind = "sale_top10" if rank and rank <= 10 else "sale50" if discount >= 50 else "sale30" if discount >= 30 else "sale"
    elif signal_type == "cross" or ranking_type == "cross" or item.get("cross_signal"):
        kind = "cross"
    elif rank and rank <= 10 and (previous is None or previous > 10):
        kind = "top10"
    elif change >= 10:
        kind = "rise10"
    elif change >= 5:
        kind = "rise5"
    elif status == "new":
        kind = "new"
    elif status == "reentry":
        kind = "reentry"
    elif rank == 1:
        kind = "first"
    else:
        kind = "normal"
    seed = "|".join(str(item.get(field, "")) for field in ("key", "current_rank", "previous_rank", "status")) + f"|{ranking_type}|{kind}"
    index = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big") % len(COMMENT_TEMPLATES[kind])
    return COMMENT_TEMPLATES[kind][index]


def post_text(item: dict[str, Any], ranking_type: str = "24h", comment: str | None = None) -> str:
    title, rank, previous = item["title"], item["current_rank"], item.get("previous_rank")
    label = "1時間ランキング" if ranking_type == "1h" else "24時間ランキング"
    note = comment or item.get("comment") or generate_comment(item, ranking_type)
    product = f'\n\n作品ページ👇\n{item["url"]}' if item.get("url") else ""
    memo = f"\n\n💬 RankIdleメモ\n{note}"
    if item["status"] in ("new", "reentry"):
        return f'【FANZA {label}】\n🆕 NEW ENTRY\n\n「{title}」\n\n初登場 {rank}位{memo}{product}\n\n#FANZA #同人'
    if rank <= 10 < (previous or 999):
        return f'【FANZA {label}】\n🔥 TOP10入り\n\n「{title}」\n\n#{previous} → #{rank}{memo}{product}\n\n#FANZA #同人'
    return f'【FANZA {label}】\n🔥 急上昇\n\n「{title}」\n\n#{previous} → #{rank}\n\n📈 +{item["rank_change"]}ランク{memo}{product}\n\n#FANZA #同人'


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
        comment = generate_comment(item, ranking_type)
        output.append({"key": key, "title": item["title"], "url": item.get("url", ""), "ranking_type": ranking_type, "status": item.get("status"), "trend_score": item["trend_score"], "previous_rank": item.get("previous_rank"),
                       "current_rank": item["current_rank"], "rank_change": item.get("rank_change", 0), "comment": comment, "text": post_text(item, ranking_type, comment), "generated_at": now.isoformat()})
    return output[-200:]
