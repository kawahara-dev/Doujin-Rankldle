import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import collector


class CollectorModeTest(unittest.TestCase):
    def run_collector(self, environment, old_status=None):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            latest_path = data_dir / "latest.json"
            status_path = data_dir / "status.json"
            if old_status is not None:
                status_path.write_text(json.dumps(old_status), encoding="utf-8")
            with (
                patch.dict(os.environ, environment, clear=True),
                patch.object(collector, "LATEST_PATH", latest_path),
                patch.object(collector, "STATUS_PATH", status_path),
            ):
                collector.main()
            return (
                json.loads(latest_path.read_text(encoding="utf-8")),
                json.loads(status_path.read_text(encoding="utf-8")),
            )

    def test_missing_credentials_generate_mock_data_without_api_call(self):
        with patch.object(collector, "fetch_items") as fetch_items:
            latest, status = self.run_collector({"DMM_API_ID": "only-one-key"})

        fetch_items.assert_not_called()
        self.assertEqual(status["mode"], "mock")
        self.assertGreater(len(latest["items"]), 0)
        self.assertTrue(all(item["id"].startswith("mock-") for item in latest["items"]))

    def test_complete_credentials_use_live_api(self):
        live_items = [{"id": "live-item", "title": "Live", "price": 100,
                       "url": "https://example.com/live", "rank": 1}]
        with patch.object(collector, "fetch_items", return_value=live_items) as fetch_items:
            latest, status = self.run_collector(
                {"DMM_API_ID": "api", "DMM_AFFILIATE_ID": "affiliate"}
            )

        fetch_items.assert_called_once_with()
        self.assertEqual(status["mode"], "live")
        self.assertEqual(latest["items"], live_items)

    def test_cumulative_stats_exp_level_and_first_run(self):
        old = {
            "first_run": "2026-01-01T00:00:00+09:00", "last_run": "2026-01-02T00:00:00+09:00",
            "total_runs": 9, "total_items_collected": 95, "items_collected": 5,
            "runs_today": 2, "run_date": "2000-01-01", "mode": "mock",
        }
        _, status = self.run_collector({}, old)
        self.assertEqual(status["total_runs"], 10)
        self.assertEqual(status["total_items_collected"], 100)
        self.assertEqual(status["first_run"], old["first_run"])
        self.assertEqual(status["exp"], 150)
        self.assertEqual((status["level"], status["level_exp"]), (2, 50))

    def test_old_status_migrates_without_losing_known_item_count(self):
        old = {"last_run": "2026-01-01T00:00:00+09:00", "total_runs": 3,
               "items_collected": 7, "runs_today": 1, "mode": "mock"}
        _, status = self.run_collector({}, old)
        self.assertEqual(status["first_run"], old["last_run"])
        self.assertEqual(status["total_items_collected"], 12)


class GameSystemTest(unittest.TestCase):
    def test_experience_and_level_calculation(self):
        self.assertEqual(collector.experience(10, 25), 75)
        self.assertEqual(collector.level_progress(75), (1, 75))
        self.assertEqual(collector.level_progress(100), (2, 0))

    def test_achievements_are_derived_from_totals(self):
        achievements = collector.achievement_progress(100, 999)
        by_id = {item["id"]: item for item in achievements}
        self.assertTrue(by_id["first_boot"]["unlocked"])
        self.assertTrue(by_id["scanner_2"]["unlocked"])
        self.assertFalse(by_id["scanner_3"]["unlocked"])
        self.assertFalse(by_id["collector_2"]["unlocked"])

    def test_normalize_status_defaults_unknown_mode_to_mock(self):
        self.assertEqual(collector.normalize_status({})["mode"], "mock")
        self.assertEqual(collector.normalize_status({"mode": "live"})["mode"], "live")


if __name__ == "__main__":
    unittest.main()
