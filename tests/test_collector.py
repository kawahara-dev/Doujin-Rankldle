import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import collector


class CollectorModeTest(unittest.TestCase):
    def run_collector(self, environment):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            latest_path = data_dir / "latest.json"
            status_path = data_dir / "status.json"
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


if __name__ == "__main__":
    unittest.main()
