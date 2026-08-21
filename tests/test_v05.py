import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import collector
from src.providers.fanza_public import FanzaAgeGateError


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

    def test_duplicate_import_does_not_mutate_ranking_or_progress_state(self):
        for ranking_type, captured_at in (("1h", "same-capture"), ("24h", "first-capture")):
            with self.subTest(ranking_type=ranking_type), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); items=[self.item(1)]
                self.run_import(root,ranking_type,items,captured_at)
                status_path=root/"status.json"; first_status=json.loads(status_path.read_text())
                tracked={path.relative_to(root):path.read_bytes() for path in root.rglob("*")
                         if path.is_file() and path != status_path and "import" not in path.parts}

                # 1h exercises duplicate captured_at detection; 24h exercises identical
                # ranking-content detection even when captured_at differs.
                second_capture=captured_at if ranking_type=="1h" else "second-capture"
                self.run_import(root,ranking_type,items,second_capture)
                second_status=json.loads(status_path.read_text())

                first_without_heartbeat={k:v for k,v in first_status.items()
                                         if k not in ("last_run","duplicate_import")}
                second_without_heartbeat={k:v for k,v in second_status.items()
                                          if k not in ("last_run","duplicate_import")}
                self.assertEqual(second_without_heartbeat,first_without_heartbeat)
                self.assertTrue(second_status["duplicate_import"])
                self.assertEqual(second_status["rankings"][f"fanza_{ranking_type}"]["streaks"]["a"],1)
                current=json.loads((root/f"fanza/{ranking_type}/current.json").read_text())
                self.assertEqual(current["items"][0]["consecutive_appearances"],1)
                self.assertEqual({path.relative_to(root):path.read_bytes() for path in root.rglob("*")
                                  if path.is_file() and path != status_path and "import" not in path.parts},tracked)

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

    def test_age_gate_falls_back_to_each_manual_ranking_type(self):
        for ranking_type in ("1h", "24h"):
            with self.subTest(ranking_type=ranking_type), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); import_path=root/"import/fanza.json"
                import_path.parent.mkdir(parents=True)
                import_path.write_text(json.dumps({"source":"fanza_manual", "ranking_type":ranking_type,
                                                   "captured_at":f"{ranking_type}-age-gate",
                                                   "items":[self.item(1)]}), encoding="utf-8")
                patches=self.sandbox(root)
                with patches[0],patches[1],patches[2],patches[3],patches[4], \
                     patch.dict("os.environ", {"PUBLIC_WATCH_ENABLED":"true"}, clear=True), \
                     patch.object(collector.FanzaPublicProvider, "fetch",
                                  side_effect=FanzaAgeGateError("FANZA age verification page reached")):
                    result=collector.main()

                status=json.loads((root/"status.json").read_text())
                current=root/f"fanza/{ranking_type}/current.json"
                history=root/f"fanza/{ranking_type}/history"
                self.assertIsNone(result)
                self.assertEqual((status["mode"],status["ranking_type"],status["input_source"]),
                                 ("import",ranking_type,"manual_import"))
                self.assertIn(f"fanza_{ranking_type}",status["rankings"])
                self.assertTrue(current.is_file())
                self.assertEqual(json.loads(current.read_text())["ranking_type"],ranking_type)
                self.assertEqual(len(list(history.glob("*.json"))),1)

    def test_age_gate_without_manual_import_exits_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); patches=self.sandbox(root)
            with patches[0],patches[1],patches[2],patches[3],patches[4], \
                 patch.dict("os.environ", {"PUBLIC_WATCH_ENABLED":"true"}, clear=True), \
                 patch.object(collector.FanzaPublicProvider, "fetch",
                              side_effect=FanzaAgeGateError("FANZA age verification page reached")):
                result=collector.main()

            status=json.loads((root/"status.json").read_text())
            self.assertIsNone(result)
            self.assertEqual((status["mode"],status["public_watch_status"]),("public","age_gate"))
            self.assertFalse((root/"latest.json").exists())


if __name__ == "__main__": unittest.main()
