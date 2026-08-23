from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any


COMMENT_TEMPLATES = {
    "cross": (
        "え、1Hも24Hも上がってる！これはちょっと気になる〜👀",
        "両方そろって上向ききた〜！この動き追いたい📈",
        "1Hだけかと思ったら24Hも来てる！いい動き👀",
        "こっちもあっちも上昇中！次の更新ちょっと楽しみ📡",
        "1Hから24Hまで動いてるのアツい！この先も見たい🔥",
        "両ランキングで上向き！これはしばらく追いたい👀",
        "お、1Hと24Hどっちも来てる〜📈",
        "短期だけじゃなく24H側も動いてる！気になる〜",
        "え、両方上がってるじゃん！この流れ続くかな👀",
        "CROSS TRENDきた〜！ここからの順位も追いたい📡",
    ),
    "top10": (
        "TOP10入ってきた〜！このまま残れるか気になる👀",
        "お、ここでTOP10入り！いい動きしてる📈",
        "きた〜！一気にTOP10圏内🔥",
        "TOP10の壁越えてきた！次も見たい👀",
        "え、上位まで来てる！これはちょっと追いたい〜",
        "ついにTOP10入り！ここからさらに行くかな📈",
        "おお、TOP10乗った！この後どうなるんだろ👀",
        "上位帯まで上がってきた〜！いい感じの動き📡",
        "TOP10きた！ここから残れるかチェック👀",
        "このタイミングでTOP10入り！ちょっとアツい🔥",
    ),
    "rise10": (
        "え、一気に二桁アップ！？かなり動いた〜📈",
        "+10以上きた！これはさすがに目立つ👀",
        "一気に飛んできた〜！次の順位も気になる🔥",
        "今回かなり大きく上がった！次も見たい📡",
        "え、このジャンプ幅すご！まだ上がるかな👀",
        "二桁ランクアップ！これは追いたくなる動き📈",
        "お、一気に順位上げてきた〜！",
        "今回かなり飛んだ！この流れ続くか見たい👀",
        "大きめの上昇きた〜！次回もチェック📡",
        "これは動いた！二桁アップは普通に気になる🔥",
    ),
    "rise5": (
        "お、しっかり上がってきた〜！次も気になる👀",
        "+5以上きた！いい感じに動いてる📈",
        "今回ちゃんと伸びてる！この先も見たい〜",
        "じわじわじゃなく一段上がった感じ👀",
        "お、この上昇はちょっと気になる！",
        "いい位置まで上がってきた〜📡",
        "今回の更新でグッと上昇！次どうなるかな👀",
        "少し動き出てきた！このまま行くかな📈",
        "ここで+5以上！いい動きしてる〜",
        "おっと、順位しっかり上げてきた👀",
    ),
    "new": (
        "初登場きた〜！ここからどこまで行くかな👀",
        "NEW ENTRY！新しく入ってきた〜📡",
        "お、新顔きた！まずはここから追ってみよ📈",
        "ランキング初登場！次の更新楽しみ〜",
        "え、新しく入ってきた！順位変化見たい👀",
        "NEWきた〜！この後どう動くんだろ",
        "新規ランクイン！ここから追ってみよ📡",
        "お、新しい作品がランキング入り！",
        "初登場！この位置からどこまで上がるかな📈",
        "新顔登場〜！しばらくチェックしたい👀",
    ),
    "reentry": (
        "戻ってきた〜！ここから再浮上あるかな👀",
        "REENTRYきた！またランキング入り📡",
        "お、圏外から帰ってきた〜！",
        "再登場！この後の順位ちょっと気になる📈",
        "え、また入ってきた！ここからどうなるかな👀",
        "復帰きた〜！次の更新も見たい",
        "一度圏外から再ランクイン！動きが気になる📡",
        "おかえりランキング！ここから上がるかな👀",
        "再浮上してきた〜！追ってみたい📈",
        "REENTRYきた！次はどこまで動くか気になる〜",
    ),
    "first": (
        "現在1位！このままトップ守れるか気になる〜👀",
        "首位きた〜！次の更新も1位かな📈",
        "いまトップ！ここからの動きも見たい📡",
        "お、現在1位！このまま行けるかな👀",
        "ランキング首位！上位の動きも気になる〜",
        "1位にいる！次回までキープするかチェック📈",
        "現在トップ〜！順位変化追いたい👀",
        "おお、首位！この後も見ていこ📡",
        "いま一番上！次の更新どうなるかな👀",
        "1位きた！この位置を保つか気になる🔥",
    ),
    "sale_top10": (
        "セール中でTOP10！この組み合わせちょっと気になる💸",
        "お、割引中で上位まで来てる〜👀",
        "SALE＋TOP10きた！順位の動きも見たい📈",
        "セール中でこの順位！次どうなるかな💸",
        "割引と上位ランクが重なってる！気になる〜",
        "お、SALE中にTOP10圏内👀",
        "セールしながら上位を推移中！動き追いたい📡",
        "SALE＋上位ランク！これはチェックしたい💸",
        "割引中でTOP10！順位への影響も気になる👀",
        "セールと上位ランキングが重なってきた〜📈",
    ),
    "sale50": (
        "半額以上きた〜！順位にも動き出るかな💸",
        "50%OFF以上！これは割引大きめ👀",
        "え、半額以上！？ランキングの動きも見たい〜",
        "大きめSALEきた！この後の順位が気になる📈",
        "半額以上の割引！ここからどう動くかな💸",
        "50%OFF以上きた〜！順位への影響も見たい👀",
        "お、かなり値引き入ってる！",
        "半額以上SALE！ランキング側も追いたい📡",
        "割引率かなり高め！この後どうなるんだろ👀",
        "50%以上OFFきた〜！順位も要チェック💸",
    ),
    "sale30": (
        "30%OFF以上きた！順位も動くか気になる💸",
        "お、割引率高め〜！この後も見たい👀",
        "SALE強め！ランキングへの影響も気になる📈",
        "30%以上OFF！順位変化もチェック📡",
        "しっかり割引入ってる〜！動くかな👀",
        "お、このSALE率はちょっと気になる💸",
        "30%OFF以上！この後のランキングも見たい",
        "割引大きめきた〜！順位も追ってみよ📈",
        "SALE中！ここから動き出るかな👀",
        "30%以上の割引！ランキング側も注目📡",
    ),
    "sale": (
        "SALEきた〜！ここから順位も動くかな💸",
        "お、いま割引中！ランキングへの影響が気になる👀",
        "セールと順位の動き、セットで追いたい📡",
        "割引中だ〜！次のランキングも見てみよ📈",
        "ここでSALE！順位がどうなるか気になる〜",
        "お、セール対象になってる！この先もチェック💸",
        "SALE中の順位、ここから動くか見たい👀",
        "割引スタート！ランキング側も追ってみよ📡",
        "いまセール中！次の更新ちょっと楽しみ",
        "価格が動いた〜！順位への影響も見たい📈",
    ),
    "normal": (
        "今この順位！次どう動くかちょっと気になる👀",
        "お、ここで推移中。次の更新も見たい〜",
        "この位置から上がるか下がるか気になる📈",
        "まだ動きあるかな？ちょっと追ってみよ📡",
        "次の更新でどうなるかな〜👀",
        "ここから順位が動くか、もう少し見たい",
        "今回はこの位置！次の変化を追ってみよ📈",
        "お、この順位にいるんだ！この後が気になる👀",
        "いまはここ！次どっちに動くんだろ📡",
        "ランキング眺めてたらこの位置！次も見たい〜",
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
