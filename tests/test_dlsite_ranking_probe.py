from pathlib import Path

from scripts.dlsite_ranking_probe import build_result, parse_ranking


FIXTURE = Path(__file__).parent / "fixtures" / "dlsite_ranking_probe.html"


def ranking_rows(count: int) -> str:
    return "".join(
        f'<li data-rank="{rank}"><a href="/maniax/work/=/product_id/RJ{100000 + rank}.html">Title {rank}</a></li>'
        for rank in range(1, count + 1)
    )


def test_parser_extracts_explicit_fields_without_inventing_missing_values():
    items, selectors = parse_ranking(FIXTURE.read_text(), "https://example.test/ranking")
    assert [item["rank"] for item in items] == [1, 2, None]
    assert [item["dom_position"] for item in items] == [1, 2, 3]
    assert items[0]["product_id"] == "RJ123456"
    assert items[0]["title"] == "Sample One"
    assert items[0]["url"] == "https://example.test/maniax/work/=/product_id/RJ123456.html"
    assert items[0]["price"] == 990
    assert items[1]["price"] == 1100
    assert items[2]["price"] is None
    assert items[2]["circle"] is None
    assert ".work_1col" in selectors["product"]


def test_malformed_and_empty_html_have_no_ranking():
    assert parse_ranking("<li><a href='/not-a-product'>broken", "https://example.test")[0] == []
    result = build_result({"requested_url": "x", "final_url": "x", "http_status": 200,
                           "content_type": "text/html", "response_size": 0,
                           "redirected": False, "elapsed_time": 0.1}, "", {"checked": False})
    assert result["ranking"]["detected"] is False
    assert result["assessment"]["confidence"] == "LOW"


def test_access_block_stops_parsing():
    access = {"requested_url": "x", "final_url": "x", "http_status": 403,
              "content_type": "text/html", "response_size": 10,
              "redirected": False, "elapsed_time": 0.1}
    result = build_result(access, FIXTURE.read_text(), {"checked": False})
    assert result["access"]["status"] == "ACCESS_BLOCKED"
    assert result["ranking"]["items_detected"] == 0
    assert result["assessment"]["confidence"] == "BLOCKED"


def test_full_normal_ranking_does_not_start_fallback():
    html = ranking_rows(20) + '<li data-rank="20"><a href="/maniax/work/no-id.html">Fallback</a></li>'

    items, _ = parse_ranking(html, "https://www.dlsite.com/maniax/ranking", limit=20)

    assert len(items) == 20
    assert all(item["product_id"] is not None for item in items)
    assert len({item["rank"] for item in items}) == 20


def test_fallback_completes_partial_ranking_up_to_limit():
    html = ranking_rows(19) + '<li data-rank="20"><a href="/maniax/work/no-id.html">Fallback 20</a></li>'

    items, _ = parse_ranking(html, "https://www.dlsite.com/maniax/ranking", limit=20)

    assert len(items) == 20
    assert items[-1]["product_id"] is None
    assert {item["rank"] for item in items} == set(range(1, 21))


def test_fallback_skips_an_already_used_explicit_rank():
    html = ranking_rows(19) + '<li data-rank="5"><a href="/maniax/work/no-id.html">Duplicate 5</a></li>'

    items, _ = parse_ranking(html, "https://www.dlsite.com/maniax/ranking", limit=20)

    assert len(items) == 19
    assert all(item["product_id"] is not None for item in items)
    assert len({item["rank"] for item in items}) == 19


def test_parser_never_exceeds_requested_limit():
    items, _ = parse_ranking(ranking_rows(21), "https://www.dlsite.com/maniax/ranking", limit=20)

    assert len(items) == 20
