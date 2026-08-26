import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src import collector
from src.post_generator import post_text
from src.weekly_report import generate_weekly_report


class ApiRankingMigrationTest(unittest.TestCase):
 def item(self, rank, key="a", **extra):
  return {"rank":rank,"id":key,"key":key,"title":key.upper(),"price":500,
          "url":f"https://normal/{key}","affiliate_url":f"https://affiliate/{key}",**extra}

 def sandbox(self, root):
  return (patch.object(collector,"FANZA_DIR",root/"fanza"),
          patch.object(collector,"LATEST_PATH",root/"latest.json"),
          patch.object(collector,"STATUS_PATH",root/"status.json"),
          patch.object(collector,"POSTS_PATH",root/"posts/candidates.json"),
          patch.object(collector,"IMPORT_PATH",root/"import/fanza.json"))

 def run_api(self, root, items):
  patches=self.sandbox(root)
  with patches[0],patches[1],patches[2],patches[3],patches[4], \
       patch.dict(os.environ,{"DMM_API_ID":"api","DMM_AFFILIATE_ID":"affiliate"},clear=True), \
       patch.object(collector,"fetch_items",return_value=items):
   collector.main()

 def test_api_statuses_rank_change_reentry_and_scoring_are_isolated(self):
  first=collector.compare_rankings([self.item(10)],[],ranking_type="api")[0]
  self.assertEqual(first["status"],"new")
  up=collector.compare_rankings([self.item(5)],[{**self.item(10),"current_rank":10}],ranking_type="api")[0]
  down=collector.compare_rankings([self.item(15)],[{**self.item(10),"current_rank":10}],ranking_type="api")[0]
  stay=collector.compare_rankings([self.item(10)],[{**self.item(10),"current_rank":10}],ranking_type="api")[0]
  reentry=collector.compare_rankings([self.item(8)],[],seen=["a"],ranking_type="api")[0]
  self.assertEqual((up["status"],up["rank_change"]),("up",5))
  self.assertEqual((down["status"],down["rank_change"]),("down",-5))
  self.assertEqual((stay["status"],stay["rank_change"]),("stay",0))
  self.assertEqual(reentry["status"],"reentry")
  self.assertEqual(up["trend_score"],20)  # API-only rise5
  for kind in ("1h","24h",None):
   legacy=collector.compare_rankings([self.item(15)],[{**self.item(20),"current_rank":20}],ranking_type=kind)[0]
   self.assertEqual(legacy["trend_score"],0)

 def test_api_momentum_and_strong_momentum(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); history=root/"fanza/api/history/2026-08-26.json"; history.parent.mkdir(parents=True)
   history.write_text(json.dumps([
    {"items":[self.item(18,current_rank=18)]},{"items":[self.item(12,current_rank=12)]}]))
   current=collector.compare_rankings([self.item(7)],[self.item(12,current_rank=12)],ranking_type="api")
   with patch.object(collector,"FANZA_DIR",root/"fanza"):
    collector.apply_api_momentum(current)
   self.assertEqual(current[0]["momentum"],"UP")
   self.assertTrue(current[0]["strong_momentum"])

 def test_api_duplicate_does_not_append_history(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); items=[self.item(1)]
   with patch.object(collector,"generate_weekly_report",wraps=generate_weekly_report) as weekly:
    self.run_api(root,items)
    history=next((root/"fanza/api/history").glob("*.json"))
    current=root/"fanza/api/current.json"; analytics=root/"analytics/fanza_api.json"
    posts=root/"posts/fanza_api_candidates.json"
    before={path:path.read_bytes() for path in (history,current,analytics,posts)}
    status_before=json.loads((root/"status.json").read_text())

    self.run_api(root,items)

   self.assertEqual(weekly.call_count,2)
   self.assertEqual(weekly.call_args.args[1:],(root/"fanza",root/"reports/weekly",root/"docs/data/reports/weekly"))
   for path,contents in before.items(): self.assertEqual(path.read_bytes(),contents)
   status=json.loads((root/"status.json").read_text())
   self.assertTrue(status["duplicate_api_snapshot"])
   for field in ("total_runs","total_items_collected","trend_events","exp","rankings"):
    self.assertEqual(status[field],status_before[field])

 def test_api_metadata_refresh_only_updates_current_and_latest(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); initial=[self.item(1,genres=[],circle=None,release_date=None)]
   self.run_api(root,initial)
   history=next((root/"fanza/api/history").glob("*.json")); before=history.read_bytes()
   status_before=json.loads((root/"status.json").read_text()); analytics=(root/"analytics/fanza_api.json").read_bytes(); posts=(root/"posts/fanza_api_candidates.json").read_bytes()
   changed=[self.item(1,genres=[{"id":"1","name":"巨乳"}],circle={"id":"c","name":"Circle"},release_date="2026-08-26")]
   self.run_api(root,changed)
   current=json.loads((root/"fanza/api/current.json").read_text())["items"][0]
   status=json.loads((root/"status.json").read_text())
   self.assertEqual(current["genres"],changed[0]["genres"])
   self.assertEqual(history.read_bytes(),before)
   self.assertEqual((status["total_runs"],status["exp"]),(status_before["total_runs"],status_before["exp"]))
   self.assertEqual((root/"analytics/fanza_api.json").read_bytes(),analytics)
   self.assertEqual((root/"posts/fanza_api_candidates.json").read_bytes(),posts)

 def test_api_failure_preserves_all_outputs(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); paths=[root/"fanza/api/current.json",root/"fanza/api/history/day.json",
                                root/"analytics/fanza_api.json",root/"posts/fanza_api_candidates.json"]
   for index,path in enumerate(paths): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(f"preserved-{index}")
   before=[path.read_bytes() for path in paths]; patches=self.sandbox(root)
   with patches[0],patches[1],patches[2],patches[3],patches[4], \
        patch.dict(os.environ,{"DMM_API_ID":"api","DMM_AFFILIATE_ID":"affiliate"},clear=True), \
        patch.object(collector,"fetch_items",side_effect=RuntimeError("API failed")),self.assertRaises(RuntimeError):
    collector.main()
   self.assertEqual([path.read_bytes() for path in paths],before)

 def test_api_does_not_cross_or_mutate_legacy_market_signals(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); (root/"fanza/1h").mkdir(parents=True)
   (root/"fanza/1h/current.json").write_text(json.dumps({"items":[self.item(2,rank_change=5)]}))
   legacy={"1h_max_rise":9,"24h_max_rise":7,"cross_trend":2,"active_sales":3}
   (root/"status.json").write_text(json.dumps({"market_signals":legacy}))
   self.run_api(root,[self.item(1)])
   current=json.loads((root/"fanza/api/current.json").read_text())["items"][0]
   signals=json.loads((root/"status.json").read_text())["market_signals"]
   self.assertNotIn("cross_signal",current)
   self.assertEqual({key:signals[key] for key in legacy},legacy)
   self.assertEqual(signals["api_new_entry"],1)

 def test_existing_cross_trend_remains(self):
  one=collector.compare_rankings([self.item(5)],[self.item(10,current_rank=10)],ranking_type="1h")
  daily=collector.compare_rankings([self.item(8)],[self.item(15,current_rank=15)],ranking_type="24h")
  self.assertEqual(len(collector.add_cross_signals(one,daily,"1h")),1)

 def test_api_post_prefers_affiliate_and_falls_back(self):
  item={**self.item(8),"current_rank":8,"previous_rank":16,"rank_change":8,"status":"up"}
  self.assertIn("https://affiliate/a",post_text(item,"api"))
  item["affiliate_url"]=""
  self.assertIn("https://normal/a",post_text(item,"api"))

 def test_weekly_api_mode_and_legacy_fallback(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); fanza=root/"fanza"; api=fanza/"api/history/2026-08-24.json"; api.parent.mkdir(parents=True)
   api.write_text(json.dumps([{"fetched_at":"2026-08-24T12:00:00+09:00","items":[self.item(4,status="new",rank_change=6)]}]))
   now=datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo"))
   report=generate_weekly_report(now,fanza,root/"r",root/"p")
   self.assertEqual(report["ranking_source"],"api")
   api.unlink()
   legacy=fanza/"24h/history/2026-08-24.json"; legacy.parent.mkdir(parents=True)
   legacy.write_text(json.dumps([{"fetched_at":"2026-08-24T12:00:00+09:00","items":[self.item(5)]}]))
   report=generate_weekly_report(now,fanza,root/"r",root/"p")
   self.assertEqual(report["ranking_source"],"legacy")

 def test_dashboard_defaults_to_api_and_has_disclaimer(self):
  app=Path("docs/app.js").read_text(); page=Path("docs/index.html").read_text()
  self.assertIn('let selectedRanking = "api"',app)
  self.assertIn('data-ranking="api" class="active"',page)
  self.assertIn("1時間 / 24時間ランキングとは別",page)


if __name__ == "__main__": unittest.main()
