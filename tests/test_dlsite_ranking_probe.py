from pathlib import Path

from scripts.dlsite_ranking_probe import build_result, parse_ranking


FIXTURE = Path(__file__).parent / "fixtures" / "dlsite_ranking_probe.html"


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
