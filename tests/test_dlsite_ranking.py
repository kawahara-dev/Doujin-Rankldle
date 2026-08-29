from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.dlsite_collector import collect, compare
from src.providers import dlsite_ranking
from src.providers.dlsite_ranking import DLsiteRankingError, DLsiteRankingProvider


def ranking_html(count=20, missing_price=False, malformed=False):
    rows = []
    for rank in range(1, count + 1):
        product_id = f"RJ{100000 + rank}"
        price = "" if missing_price and rank == 2 else f"<span>{rank:,}00円</span>"
        href = "/outside" if malformed and rank == 3 else f"/maniax/work/=/product_id/{product_id}.html"
        rows.append(f'<li class="work_1col" data-rank="{rank}"><a href="{href}">Title {rank}</a>{price}</li>')
    return "<ol>" + "".join(rows) + "</ol>"


def test_provider_parses_top20_and_explicit_fields(monkeypatch):
    access = {"http_status": 200, "final_url": "https://www.dlsite.com/maniax/ranking"}
    monkeypatch.setattr(dlsite_ranking, "fetch", lambda *_: (access, ranking_html(missing_price=True)))
    provider = DLsiteRankingProvider()
    items = provider.fetch()
    assert len(items) == 20
    assert items[0] == {"rank": 1, "product_id": "RJ100001", "title": "Title 1",
                        "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ100001.html", "price": 100}
    assert items[1]["price"] is None


def test_provider_drops_malformed_or_external_product_url(monkeypatch):
    access = {"http_status": 200, "final_url": "https://www.dlsite.com/maniax/ranking"}
    monkeypatch.setattr(dlsite_ranking, "fetch", lambda *_: (access, ranking_html(malformed=True)))
    items = DLsiteRankingProvider().fetch()
    assert len(items) == 19
    assert all(item["product_id"] != "RJ100003" for item in items)


def test_provider_rejects_empty_ranking_and_block(monkeypatch):
    access = {"http_status": 200, "final_url": "https://www.dlsite.com/maniax/ranking"}
    monkeypatch.setattr(dlsite_ranking, "fetch", lambda *_: (access, "<html>empty</html>"))
    with pytest.raises(DLsiteRankingError, match="insufficient"):
        DLsiteRankingProvider().fetch()


def test_collector_rejects_duplicate_ranks_from_normal_parser(monkeypatch, tmp_path):
    html = ranking_html(20).replace('data-rank="20"', 'data-rank="5"')
    access = {"http_status": 200, "final_url": "https://www.dlsite.com/maniax/ranking"}
    monkeypatch.setattr(dlsite_ranking, "fetch", lambda *_: (access, html))

    status = collect(DLsiteRankingProvider(), data_dir=tmp_path / "data", docs_dir=tmp_path / "docs")

    assert status["last_error"] == "parser failure: duplicate ranks"
    assert not (tmp_path / "data" / "current.json").exists()


def test_parser_preserves_ranked_item_with_missing_product_id(monkeypatch):
    html = ranking_html(19) + '<li data-rank="20"><a href="/maniax/work/sample.html">No ID</a></li>'
    access = {"http_status": 200, "final_url": "https://www.dlsite.com/maniax/ranking"}
    monkeypatch.setattr(dlsite_ranking, "fetch", lambda *_: (access, html))
    missing = next(item for item in DLsiteRankingProvider().fetch() if item["product_id"] is None)
    assert missing["rank"] == 20
    assert missing["title"] == "No ID"
    monkeypatch.setattr(dlsite_ranking, "fetch", lambda *_: ({**access, "http_status": 403}, "denied"))
    with pytest.raises(DLsiteRankingError, match="403"):
        DLsiteRankingProvider().fetch()


def test_ranking_states_include_new_up_down_stay_and_reentry():
    previous = [{"product_id": "RJ1", "rank": 4}, {"product_id": "RJ2", "rank": 2},
                {"product_id": "RJ3", "rank": 3}]
    raw = [{"product_id": "RJ1", "rank": 1}, {"product_id": "RJ2", "rank": 5},
           {"product_id": "RJ3", "rank": 3}, {"product_id": "RJ4", "rank": 4},
           {"product_id": "RJ5", "rank": 6}]
    result = compare(raw, previous, {"RJ1", "RJ2", "RJ3", "RJ5"})
    assert [(x["status"], x["rank_change"]) for x in result] == [
        ("up", 3), ("down", -3), ("stay", 0), ("new", None), ("reentry", None)]


class FakeProvider:
    http_status = 200

    def __init__(self, items=None, error=None):
        self.items, self.error = items, error

    def fetch(self):
        if self.error:
            raise self.error
        return self.items


def items(offset=0):
    return [{"rank": rank, "product_id": f"RJ{rank}", "title": f"T{rank}",
             "url": f"https://www.dlsite.com/work/=/product_id/RJ{rank}.html", "price": 100 + offset}
            for rank in range(1, 21)]


def test_duplicate_does_not_add_history_or_change_current(tmp_path):
    data, docs = tmp_path / "data", tmp_path / "docs"
    first = datetime(2026, 8, 29, 9, 40, tzinfo=ZoneInfo("Asia/Tokyo"))
    collect(FakeProvider(items()), first, data, docs)
    current_before = (data / "current.json").read_bytes()
    history_before = list((data / "history").glob("*/*.json"))
    status = collect(FakeProvider(items(offset=99)), first.replace(hour=15), data, docs)
    assert status["duplicate"] is True
    assert (data / "current.json").read_bytes() == current_before
    assert list((data / "history").glob("*/*.json")) == history_before
    assert status["total_successful_snapshots"] == 1


@pytest.mark.parametrize("error", [DLsiteRankingError("HTTP 403", 403),
                                    DLsiteRankingError("parser failure", 200),
                                    DLsiteRankingError("insufficient ranking items: 0", 200)])
def test_failure_preserves_current_and_history(tmp_path, error):
    data, docs = tmp_path / "data", tmp_path / "docs"
    now = datetime(2026, 8, 29, 9, 40, tzinfo=ZoneInfo("Asia/Tokyo"))
    collect(FakeProvider(items()), now, data, docs)
    current_before = (data / "current.json").read_bytes()
    history_before = [(p, p.read_bytes()) for p in (data / "history").glob("*/*.json")]
    status = collect(FakeProvider(error=error), now.replace(hour=15), data, docs)
    assert status["last_error"]
    assert (data / "current.json").read_bytes() == current_before
    assert [(p, p.read_bytes()) for p in (data / "history").glob("*/*.json")] == history_before
