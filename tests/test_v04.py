import json
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
