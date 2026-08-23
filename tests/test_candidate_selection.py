import json
import subprocess
import unittest
from pathlib import Path


class CandidateSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path("docs/app.js").read_text(encoding="utf-8")
        cls.selector_source = source[:source.index("function renderCandidates")]

    def select(self, candidates):
        script = (
            self.selector_source
            + f"\nprocess.stdout.write(JSON.stringify(selectCandidates({json.dumps(candidates)})));"
        )
        result = subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        )
        return json.loads(result.stdout)

    @staticmethod
    def candidate(name, *, priority="rise", generated_at="2026-08-20T00:00:00Z", new=True):
        item = {
            "title": name,
            "text": f"post {name}",
            "generated_at": generated_at,
            "current_rank": 20,
            "previous_rank": 30,
            "rank_change": 5,
            "status": "up",
        }
        if new:
            item["comment"] = f"memo {name}"
            item["text"] += "\n💬 RankIdleメモ"
        if priority == "cross":
            item["ranking_type"] = "cross"
        elif priority == "normal":
            item["rank_change"] = 0
        return item

    def test_three_new_candidates_exclude_legacy_and_limit_to_three(self):
        candidates = [self.candidate("old-cross", priority="cross", new=False)]
        candidates += [self.candidate(f"new-{index}") for index in range(4)]
        selected = self.select(candidates)
        self.assertEqual(len(selected), 3)
        self.assertTrue(all("comment" in item for item in selected))

    def test_same_priority_prefers_newer_generated_at(self):
        older = self.candidate("older", generated_at="2026-08-20T00:00:00Z")
        newer = self.candidate("newer", generated_at="2026-08-21T00:00:00Z")
        self.assertEqual(self.select([older, newer])[0]["title"], "newer")

    def test_comment_field_marks_new_format_without_memo_in_text(self):
        current = self.candidate("comment-only", priority="normal")
        current["text"] = "complete post with gal comment"
        legacy = self.candidate("legacy-cross", priority="cross", new=False)
        self.assertEqual(self.select([legacy, current])[0]["title"], "comment-only")

    def test_legacy_candidates_fill_shortfall(self):
        current = self.candidate("current")
        legacy = [self.candidate(f"legacy-{index}", new=False) for index in range(3)]
        selected = self.select(legacy + [current])
        self.assertEqual(selected[0]["title"], "current")
        self.assertEqual(len(selected), 3)

    def test_selected_text_keeps_rankidle_memo_for_copy(self):
        current = self.candidate("copy")
        selected = self.select([current])
        self.assertIn("💬 RankIdleメモ", selected[0]["text"])


if __name__ == "__main__":
    unittest.main()
