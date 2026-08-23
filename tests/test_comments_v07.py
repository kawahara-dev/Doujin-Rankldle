import unittest
from datetime import datetime
from pathlib import Path

from src import collector
from src.post_generator import COMMENT_TEMPLATES, generate_candidates, generate_comment


class RankIdleCommentTest(unittest.TestCase):
    def item(self, **values):
        return {
            **{
                "key": "d_test",
                "title": "テスト作品",
                "url": "https://example.test/d_test",
                "current_rank": 20,
                "previous_rank": 25,
                "rank_change": 5,
                "status": "up",
                "trend_score": 20,
            },
            **values,
        }

    def assert_template(self, expected, item=None, ranking_type="24h", signal_type=None):
        comment = generate_comment(item or self.item(), ranking_type, signal_type)
        self.assertIn(comment, COMMENT_TEMPLATES[expected])
        self.assertLessEqual(len(comment), 60)
        return comment

    def test_ranking_comment_categories_and_priority(self):
        self.assert_template("cross", self.item(cross_signal=True), "1h")
        self.assert_template("top10", self.item(current_rank=9, previous_rank=14, rank_change=5))
        self.assert_template("rise10", self.item(current_rank=15, previous_rank=27, rank_change=12))
        self.assert_template("rise5")
        self.assert_template("new", self.item(status="new", previous_rank=None, current_rank=18, rank_change=0))
        self.assert_template("reentry", self.item(status="reentry", previous_rank=None, current_rank=18, rank_change=0))

    def test_sale_comment_categories(self):
        self.assert_template("sale50", self.item(discount_rate=50), signal_type="sale")
        self.assert_template("sale30", self.item(discount_rate=30), signal_type="sale")
        self.assert_template("sale_top10", self.item(current_rank=7, discount_rate=50), signal_type="sale")

    def test_comments_are_deterministic_and_distributed(self):
        item = self.item()
        self.assertEqual(generate_comment(item, "24h"), generate_comment(item, "24h"))
        variants = {generate_comment(self.item(key=f"d_{index}"), "24h") for index in range(24)}
        self.assertGreater(len(variants), 1)

    def test_all_templates_are_within_length_limit(self):
        for category, templates in COMMENT_TEMPLATES.items():
            with self.subTest(category=category):
                self.assertGreaterEqual(len(templates), 4)
                self.assertTrue(all(len(comment) <= 60 for comment in templates))

    def test_candidates_save_comment_and_complete_post(self):
        item = self.item()
        candidate = generate_candidates([item], [], datetime.now())[0]
        self.assertEqual(candidate["comment"], generate_comment(item, "24h"))
        self.assertIn(f'💬 RankIdleメモ\n{candidate["comment"]}', candidate["text"])
        self.assertIn(item["url"], candidate["text"])

    def test_cross_and_sale_candidates_save_comments(self):
        signal = {
            **self.item(),
            "ranking_type": "cross",
            "one_hour": {"previous_rank": 25, "current_rank": 20},
            "twenty_four_hour": {"previous_rank": 30, "current_rank": 24},
        }
        cross = collector.cross_candidate(signal, datetime.now())
        self.assertIn(cross["comment"], COMMENT_TEMPLATES["cross"])
        self.assertIn("💬 RankIdleメモ", cross["text"])

        sale_item = self.item(
            on_sale=True, discount_rate=50, price=1000, regular_price=2000,
            sale_events=["sale_start"], hot_sale=True, sale_score=50,
        )
        sale = collector.sale_candidates([sale_item], [], datetime.now())[0]
        self.assertIn(sale["comment"], COMMENT_TEMPLATES["sale50"])
        self.assertIn("💬 RankIdleメモ", sale["text"])

    def test_pages_keeps_legacy_candidates_safe(self):
        source = Path("docs/app.js").read_text(encoding="utf-8")
        self.assertIn('const completedText = item.text || ""', source)
        self.assertNotIn("item.comment.trim", source)


if __name__ == "__main__":
    unittest.main()
