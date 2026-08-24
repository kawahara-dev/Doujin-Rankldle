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
