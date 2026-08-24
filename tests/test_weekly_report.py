import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.weekly_report import generate_weekly_report


class WeeklyReportTest(unittest.TestCase):
 def test_partial_week_aggregation_and_pages_sync(self):
  with tempfile.TemporaryDirectory() as temporary:
   root = Path(temporary); fanza = root / "fanza"; reports = root / "reports"; pages = root / "pages"
   for kind, hour, items in (("1h", 9, [{"id":"a","title":"A","rank":8,"price":900,"rank_change":6,"status":"new"}]),
                             ("24h", 14, [{"id":"a","title":"A","rank":5,"price":900,"rank_change":3,"previous_rank":8,"on_sale":True,"discount_rate":30}])):
    path = fanza / kind / "history" / "2026-08-24.json"; path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"fetched_at":f"2026-08-24T{hour:02d}:00:00+09:00","items":items}]), encoding="utf-8")
   report = generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")), fanza, reports, pages)
   self.assertEqual(report["data_status"], "PARTIAL")
   self.assertEqual(report["market_overview"]["cross_trend_events"], 1)
   self.assertEqual(report["sale_analysis"]["top10_sale_share"], 100)
   self.assertEqual(report["stable_top10"], report["top10_stays"])
   self.assertEqual(report["biggest_movers"][0]["id"], "a")
   self.assertEqual(report["biggest_movers"][0]["rank_change"], 6)
   self.assertLessEqual(len(report["creator_insights"]), 3)
   self.assertIn("今週途中の暫定集計", report["x_post_text"])
   self.assertIn("※RankIdle観測データによる集計", report["x_post_text"])
   self.assertEqual(json.loads((pages / "latest.json").read_text()), report)

 def test_complete_requires_all_seven_days(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"
   for kind in ("1h", "24h"):
    folder=fanza/kind/"history"; folder.mkdir(parents=True)
    for day in range(17,24):
     (folder/f"2026-08-{day}.json").write_text(json.dumps([{"fetched_at":f"2026-08-{day}T12:00:00+09:00","items":[]}]))
   report=generate_weekly_report(datetime(2026,8,23,23,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p")
   self.assertEqual(report["data_status"], "COMPLETE")
   self.assertIn("1週間のランキングまとめたよ〜！", report["x_post_text"])
   self.assertNotIn("今週途中の暫定集計", report["x_post_text"])

 def test_creator_insights_are_rule_based_and_limited(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"
   for kind, change in (("1h", 12), ("24h", 8)):
    folder=fanza/kind/"history"; folder.mkdir(parents=True)
    items=[{"id":"a","title":"A","rank":2,"price":500,"rank_change":change,"status":"new","on_sale":True}]
    (folder/"2026-08-24.json").write_text(json.dumps([{"fetched_at":"2026-08-24T12:00:00+09:00","items":items}]))
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p")
   self.assertEqual(len(report["creator_insights"]), 3)
   self.assertTrue(all(isinstance(insight, str) for insight in report["creator_insights"]))
   forbidden=("販売数", "売上", "影響", "原因")
   self.assertFalse(any(word in " ".join(report["creator_insights"]) for word in forbidden))
