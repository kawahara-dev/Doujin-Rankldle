from pathlib import Path

import scripts.dlsite_thumbnail_probe as probe


FIXTURE = Path(__file__).parent / "fixtures" / "dlsite_thumbnail_probe.html"
BASE = "https://www.dlsite.com/maniax/ranking"


def test_extracts_supported_candidates_and_associates_same_container():
    items = probe.parse_thumbnails(FIXTURE.read_text(), BASE)
    by_id = {item["product_id"]: item for item in items}
    assert by_id["RJ100001"]["thumbnail_source"] == "img[src]"
    assert by_id["RJ100002"]["thumbnail_url"] == "https://img.dlsite.jp/b.jpg"
    assert by_id["RJ100002"]["thumbnail_source"] == "img[data-src]"
    assert by_id["RJ100003"]["thumbnail_url"] == "https://www.dlsite.com/thumb/c-small.webp"
    assert by_id["RJ100003"]["thumbnail_source"] == "source[srcset]"
    assert by_id["RJ100004"]["thumbnail_url"] is None
    assert by_id["RJ100005"]["thumbnail_url"] is None
    assert by_id["RJ100006"]["thumbnail_url"] == "https://www.dlsite.com/thumb/f.png"
    assert by_id["RJ100007"]["thumbnail_url"] == "https://www.dlsite.com/thumb/g.jpg"
    assert by_id["RJ100008"]["thumbnail_source"] == "img[data-lazy-image]"
    assert by_id["RJ100009"]["thumbnail_source"] == "style[background-image]"
    assert "RJ999999" not in by_id


def test_duplicate_candidate_is_emitted_once():
    parser = probe.TreeParser()
    parser.feed('<li><a href="/work/RJ1">X</a><img data-src="/x.jpg" src="/x.jpg"></li>')
    anchor = next(node for node in probe.walk(parser.root) if node.tag == "a")
    assert list(probe._image_candidates(probe._container(anchor), BASE)) == [
        ("https://www.dlsite.com/x.jpg", "img[data-src]")
    ]


def test_report_records_request_limits_and_partial_coverage():
    report = probe.build_report(FIXTURE.read_text(), BASE, "2026-08-31T00:00:00+00:00")
    assert report["request_count"] == 1
    assert report["additional_product_requests"] == 0
    assert report["image_requests"] == 0
    assert report["ranking_items"] == 9
    assert report["thumbnail_found"] == 7
    assert report["result"] == "PARTIAL"


def test_main_performs_exactly_one_fetch_and_writes_json(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(probe, "fetch", lambda url, timeout: (calls.append((url, timeout)) or
                        ({"final_url": BASE}, FIXTURE.read_text())))
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["probe", "--output", str(output)])
    assert probe.main() == 0
    assert len(calls) == 1
    assert output.is_file()
