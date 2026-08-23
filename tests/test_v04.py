import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import collector


class ManualImportV04Test(unittest.TestCase):
    def load(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fanza.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(collector, "IMPORT_PATH", path):
                return collector.import_items()

    def test_envelope_and_legacy_formats(self):
        item = {"rank": 1, "title": "A", "price": 100, "url": "https://example/a"}
        self.assertEqual(self.load({"source": "fanza_manual", "captured_at": "2026-01-01T00:00:00Z", "items": [item]})[0]["title"], "A")
        self.assertEqual(self.load([item])[0]["rank"], 1)

    def test_duplicate_rank_and_item_are_rejected(self):
        base = {"title": "A", "price": 0, "url": "https://example/a"}
        with self.assertRaisesRegex(RuntimeError, "duplicate rank"):
            self.load([{**base, "rank": 1}, {**base, "rank": 1, "url": "https://example/b"}])
        with self.assertRaisesRegex(RuntimeError, "duplicate item"):
            self.load([{**base, "rank": 1}, {**base, "rank": 2}])

    def test_required_fields_and_types_are_checked(self):
        for item, message in [
            ({"title": "A", "url": "u", "price": 0}, "rank must"),
            ({"rank": 1, "title": "", "url": "u", "price": 0}, "title is empty"),
            ({"rank": 1, "title": "A", "price": 0}, "both missing"),
            ({"rank": 1, "title": "A", "url": "u", "price": "100"}, "price must"),
        ]:
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message): self.load([item])

    def test_bookmarklet_is_minimal_and_has_copy_fallback(self):
        source = Path("docs/bookmarklet.js").read_text(encoding="utf-8")
        for field in ("rank", "title", "price", "url", "id", "captured_at"): self.assertIn(field, source)
        self.assertIn("navigator.clipboard", source); self.assertIn("textarea", source)
        for forbidden in ("cookie=", "captcha", "レビュー", "sampleImage"): self.assertNotIn(forbidden, source)

    def test_bookmarklet_supports_mobile_card_discovery_and_debug_counts(self):
        source = Path("docs/bookmarklet.js").read_text(encoding="utf-8")
        fixture = Path("tests/fixtures/fanza_ranking_mobile.html").read_text(encoding="utf-8")
        for marker in ("販売数", "depth < 10", "Product Links:", "Candidate Cards:", "Ranks Found:"):
            self.assertIn(marker, source)
        for expected in ("d_mobile001", "d_mobile002", "3,080円", "¥1,650", "販売数：1,972"):
            self.assertIn(expected, fixture)

    def test_notification_badge_regression_fixture_and_card_boundary_guards(self):
        source = Path("docs/bookmarklet.js").read_text(encoding="utf-8")
        fixture = Path("tests/fixtures/fanza_ranking_notification_badge.html").read_text(encoding="utf-8")
        self.assertIn('class="badge">34', fixture)
        for cid in ("d_badge001", "d_badge002", "d_badge003"):
            self.assertEqual(fixture.count(cid), 2)
        for rank in (1, 2, 3):
            self.assertIn(f'class="rank">{rank}', fixture)
        for price in ("880円", "1,100円", "1,320円"):
            self.assertIn(price, fixture)
        for guard in ("productCids(card).size !== 1", "cids.size > 1", "sales.previousElementSibling",
                      "DOM Order Fallback Used", "全商品の順位が同一です", "全商品の価格が同一です"):
            self.assertIn(guard, source)

    def test_24_hour_fixture_has_twenty_explicit_ranked_products(self):
        fixture = Path("tests/fixtures/fanza_ranking_24h.html").read_text(encoding="utf-8")
        cards = re.findall(r'<article class="daily-card" data-rank="(\d+)">(.*?)</article>', fixture, re.S)
        self.assertEqual(len(cards), 20)
        self.assertEqual([int(rank) for rank, _ in cards], list(range(1, 21)))
        self.assertTrue(all("販売数" in body and re.search(r"(?:¥[\d,]+|[\d,]+円)", body)
                            for _, body in cards))

    def test_sale_scope_fixture_keeps_price_outside_ranking_card(self):
        source = Path("docs/bookmarklet.js").read_text(encoding="utf-8")
        fixture = Path("tests/fixtures/fanza_ranking_sale_scope.html").read_text(encoding="utf-8")
        ranking_card = re.search(r'<div class="ranking-card">(.*?)</div>\s*<div class="sale-info">',
                                 fixture, re.S).group(1)
        self.assertIn("販売数：1,972", ranking_card)
        self.assertIn("saleScopeテスト作品", ranking_card)
        self.assertNotRegex(ranking_card, r"(?:[¥￥][\d,]+|[\d,]+円|%OFF)")
        for expected in ("30%OFF", "3,080円", "設定価格4,400円", "9/18まで"):
            self.assertIn(expected, fixture)
        for behavior in ("saleScopeOf(card, cid)", "priceOf(saleScope.scope)",
                         "saleOf(saleScope.scope)", "cids.size > 1", "depth <= 8"):
            self.assertIn(behavior, source)
        for debug_label in ("Price Found:", "Regular Price Found:", "Sale Scope Found:",
                            "Sale Scope Depth:", "Sale Items:"):
            self.assertIn(debug_label, source)

    def test_1_hour_fixture_dom_order_matches_safe_partial_ranking(self):
        source = Path("docs/bookmarklet.js").read_text(encoding="utf-8")
        fixture = Path("tests/fixtures/fanza_ranking_1h.html").read_text(encoding="utf-8")
        cards = re.findall(r'<article class="hourly-row(?: incomplete)?">(.*?)</article>', fixture, re.S)
        safe_cids = [re.search(r"cid=(d_hourly\d+)", card).group(1)
                     for card in cards if "販売数" in card]
        self.assertEqual(len(cards), 21)
        self.assertEqual(safe_cids, [f"d_hourly{i:03}" for i in range(1, 20)])
        self.assertEqual(sum("販売数" not in card for card in cards), 2)
        self.assertEqual(sum(not re.search(r"(?:¥[\d,]+|[\d,]+円)", card)
                             for card in cards if "販売数" in card), 1)
        for policy in ("out.length >= 10", "explicitRanks === 0", "stableDomOrder",
                       "Missing Products:", "Price Missing:", "Sales Missing:",
                       "Missing Product Diagnostics:"):
            self.assertIn(policy, source)

    def test_1_hour_price_scope_fixture_and_safety_guards(self):
        source = Path("docs/bookmarklet.js").read_text(encoding="utf-8")
        fixture = Path("tests/fixtures/fanza_ranking_1h_price_scope.html").read_text(encoding="utf-8")
        self.assertRegex(fixture, r"d_mobile_price[\s\S]*770円")
        pc_card = re.search(r'data-rank="2">(.*?)</div><strong class="price">1,100円', fixture, re.S)
        self.assertIsNotNone(pc_card)
        self.assertNotIn("1,100円", pc_card.group(1))
        unsafe = re.search(r'unsafe-multi-product(.*?)</section>', fixture, re.S).group(1)
        self.assertIn("d_no_price", unsafe)
        self.assertIn("d_other_price", unsafe)
        self.assertIn("9,999円", unsafe)
        for behavior in ("priceScopeOf(card, cid)", "priceOf(priceScope.scope)",
                         "cids.size > 1", "depth <= 8", "hasPrice(candidate)"):
            self.assertIn(behavior, source)
        for debug_label in ("Price Scope Found:", "Price Scope Depth:"):
            self.assertIn(debug_label, source)

    def test_bookmarklet_minifier_keeps_code_after_line_comments_and_is_valid_javascript(self):
        script = r'''const { minify } = require("./docs/bookmarklet-minifier.js");
const fixture = `(() => {
  const before = "// inside a string"; // an inline comment
  // a whole-line comment
  const after = 42;
  alert(before + after);
})();`;
const output = minify(fixture);
if (!output.startsWith("javascript:(()=>{")) throw new Error("invalid prefix: " + output);
if (!output.includes("const after = 42")) throw new Error("code after comment was removed");
new Function(output.slice("javascript:".length));'''
        subprocess.run(["node", "-e", script], check=True)

    def test_generated_bookmarklet_has_expected_prefix_and_valid_syntax(self):
        script = r'''const fs = require("fs");
const { minify } = require("./docs/bookmarklet-minifier.js");
const output = minify(fs.readFileSync("docs/bookmarklet.js", "utf8"));
if (!output.startsWith("javascript:(()=>{")) throw new Error("invalid prefix");
new Function(output.slice("javascript:".length));'''
        subprocess.run(["node", "-e", script], check=True)

    def test_missing_prices_are_valid_after_card_confirmation(self):
        script = r'''const { validate } = require("./docs/bookmarklet.js");
const items = Array.from({length: 19}, (_, i) => ({rank: i + 1, title: `T${i}`, price: 0, url: `u${i}`}));
if (validate(items) !== "") throw new Error(validate(items));'''
        subprocess.run(["node", "-e", script], check=True)

    def test_captured_at_prevents_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); import_path = root / "import" / "fanza.json"; import_path.parent.mkdir()
            import_path.write_text(json.dumps({"source": "fanza_manual", "captured_at": "2026-01-01T00:00:00Z", "items": [{"rank": 1, "title": "A", "price": 100, "id": "a", "url": "https://example/a"}]}))
            fanza=root/"fanza"; latest=root/"latest.json"; status=root/"status.json"; posts=root/"posts.json"
            patches=(patch.object(collector,"IMPORT_PATH",import_path),patch.object(collector,"FANZA_DIR",fanza),patch.object(collector,"LATEST_PATH",latest),patch.object(collector,"STATUS_PATH",status),patch.object(collector,"POSTS_PATH",posts))
            with patches[0],patches[1],patches[2],patches[3],patches[4]: collector.main(); first=json.loads(status.read_text()); collector.main(); second=json.loads(status.read_text())
            self.assertEqual((first["total_runs"],first["total_items_collected"],first["exp"]),(second["total_runs"],second["total_items_collected"],second["exp"]))
            self.assertTrue(second["duplicate_import"])


if __name__ == "__main__": unittest.main()
