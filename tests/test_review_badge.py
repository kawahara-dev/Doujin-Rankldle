import json
import subprocess
import unittest
from pathlib import Path


class ReviewBadgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path("docs/app.js").read_text(encoding="utf-8")
        cls.source = source[:source.index("function renderCandidates")]

    def run_node(self, expression):
        script = self.source + "\nprocess.stdout.write(JSON.stringify(" + expression + "));"
        result = subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        )
        return json.loads(result.stdout)

    def test_both_fields_show_stars_and_count(self):
        label = self.run_node(
            'reviewLabel({review_average: 4.74, review_count: 1401})'
        )
        self.assertEqual(label, "★4.7 (1,401件)")

    def test_average_rounds_to_one_decimal(self):
        self.assertEqual(
            self.run_node('reviewLabel({review_average: 5.0, review_count: 52})'),
            "★5.0 (52件)",
        )
        self.assertEqual(
            self.run_node('reviewLabel({review_average: 3.42, review_count: 1})'),
            "★3.4 (1件)",
        )

    def test_average_only_shows_stars(self):
        self.assertEqual(
            self.run_node('reviewLabel({review_average: 4.63})'), "★4.6"
        )

    def test_count_only_shows_review_count(self):
        self.assertEqual(
            self.run_node('reviewLabel({review_count: 179})'), "レビュー 179件"
        )

    def test_missing_or_invalid_returns_null(self):
        for item in (
            {},
            {"review_average": None, "review_count": None},
            {"review_average": "bad"},
            {"review_average": 6},
            {"review_average": -1},
            {"review_count": -5},
            {"review_count": "bad"},
        ):
            self.assertIsNone(
                self.run_node("reviewLabel(" + json.dumps(item) + ")"), item
            )

    def test_numeric_strings_are_accepted(self):
        self.assertEqual(
            self.run_node(
                'reviewLabel({review_average: "4.74", review_count: "1401"})'
            ),
            "★4.7 (1,401件)",
        )

    def test_render_items_wires_review_badge_and_styles_exist(self):
        app = Path("docs/app.js").read_text(encoding="utf-8")
        self.assertIn("reviewLabel(item)", app)
        self.assertIn('badge.className="review-badge"', app)
        style = Path("docs/style.css").read_text(encoding="utf-8")
        self.assertIn(".review-badge", style)
        page = Path("docs/index.html").read_text(encoding="utf-8")
        self.assertIn("REVIEW ★", page)


if __name__ == "__main__":
    unittest.main()
