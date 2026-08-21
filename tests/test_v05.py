import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import collector


class RankingSeparationV05Test(unittest.TestCase):
    def sandbox(self, root):
        return (patch.object(collector, "FANZA_DIR", root / "fanza"),
                patch.object(collector, "LATEST_PATH", root / "latest.json"),
                patch.object(collector, "STATUS_PATH", root / "status.json"),
                patch.object(collector, "POSTS_PATH", root / "posts" / "candidates.json"),
                patch.object(collector, "IMPORT_PATH", root / "import" / "fanza.json"))

    def run_import(self, root, ranking_type, items, captured_at):
        path = root / "import" / "fanza.json"; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"source":"fanza_manual", "ranking_type":ranking_type,
                                    "captured_at":captured_at, "items":items}), encoding="utf-8")
        patches=self.sandbox(root)
        with patches[0],patches[1],patches[2],patches[3],patches[4],patch.dict("os.environ", {}, clear=True): collector.main()

    @staticmethod
    def item(rank, key="a", price=0):
        return {"rank":rank,"title":key.upper(),"price":price,"id":key,"url":f"https://example/{key}"}

    def test_imports_route_and_only_compare_with_same_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.run_import(root,"1h",[self.item(12)],"one-a")
            self.run_import(root,"24h",[self.item(18)],"day-a")
            daily=json.loads((root/"fanza/24h/current.json").read_text())["items"][0]
            self.assertIsNone(daily["previous_rank"])
            self.run_import(root,"1h",[self.item(5)],"one-b")
            hourly=json.loads((root/"fanza/1h/current.json").read_text())["items"][0]
            self.assertEqual((hourly["previous_rank"],hourly["rank_change"]),(12,7))
            self.run_import(root,"24h",[self.item(10)],"day-b")
            daily=json.loads((root/"fanza/24h/current.json").read_text())["items"][0]
            self.assertEqual((daily["previous_rank"],daily["rank_change"]),(18,8))
            candidates=json.loads((root/"posts/fanza_24h_candidates.json").read_text())
            self.assertTrue(any(x["ranking_type"] == "cross" for x in candidates))

    def test_duplicate_scope_includes_ranking_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); items=[self.item(1)]
            self.run_import(root,"1h",items,"same"); self.run_import(root,"24h",items,"same")
            status=json.loads((root/"status.json").read_text())
            self.assertEqual(status["total_runs"],2)
            self.run_import(root,"24h",items,"same")
            self.assertTrue(json.loads((root/"status.json").read_text())["duplicate_import"])

    def test_unknown_rejected_and_hourly_zero_price_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/"fanza.json"
            path.write_text(json.dumps({"ranking_type":"unknown","items":[self.item(1)]}))
            with patch.object(collector,"IMPORT_PATH",path), self.assertRaisesRegex(RuntimeError,"ranking_type"): collector.import_items()
            path.write_text(json.dumps({"ranking_type":"1h","items":[self.item(1,price=0)]}))
            with patch.object(collector,"IMPORT_PATH",path): self.assertEqual(collector.import_items()[0]["price"],0)

    def test_legacy_data_is_copied_to_24h_without_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old=root/"fanza/current.json"; old.parent.mkdir(parents=True)
            old.write_text(json.dumps({"items":[self.item(1)]}))
            with patch.object(collector,"FANZA_DIR",root/"fanza"): collector.migrate_legacy_fanza()
            self.assertTrue(old.exists()); self.assertTrue((root/"fanza/24h/current.json").exists())

    def test_cross_signal_bonus_is_capped(self):
        current=collector.compare_rankings([self.item(1)], [{**self.item(50),"current_rank":50}])
        other=collector.compare_rankings([self.item(2)], [{**self.item(20),"current_rank":20}])
        signals=collector.add_cross_signals(current,other,"1h")
        self.assertEqual(len(signals),1); self.assertLessEqual(current[0]["trend_score"],100)


if __name__ == "__main__": unittest.main()
