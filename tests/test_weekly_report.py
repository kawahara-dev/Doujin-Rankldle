import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.weekly_report import generate_weekly_report
from src.metadata import meaningful_genres


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

 def test_api_metadata_counts_unique_products_and_coverage(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   item={"id":"a","rank":5,"genres":[{"name":"巨乳"},{"name":"巨乳"}],"circle":{"name":"C"},"release_date":"2026-08-20"}
   history.write_text(json.dumps([{"fetched_at":"2026-08-24T10:00:00+09:00","items":[item]},{"fetched_at":"2026-08-24T12:00:00+09:00","items":[item,{"id":"b","rank":20}]}]))
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   self.assertEqual(report["top_genres"],[{"name":"巨乳","observed_products":1,"top10_products":1}])
   self.assertEqual(report["top_circles"][0]["observed_products"],1)
   self.assertEqual(report["new_release_products"],1)
   self.assertEqual(report["metadata_coverage"],{"genre":1,"meaningful_genre":1,"circle":1,"release_date":1,"total_products":2})

 def test_meaningful_genres_preserve_raw_and_exclude_by_id_or_name(self):
  raw=[{"id":"156023","name":"renamed"},{"id":"x","name":"男性向け"},
       {"id":"156021","name":"専売"},{"id":"2001","name":"巨乳"},
       {"id":"new","name":"未知タグ"}]
  before=json.dumps(raw,ensure_ascii=False)
  self.assertEqual([x["name"] for x in meaningful_genres(raw)],["巨乳","未知タグ"])
  self.assertEqual(json.dumps(raw,ensure_ascii=False),before)

 def test_api_metadata_uses_meaningful_genres_and_positive_prices(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   generic=[{"id":"156023","name":"成人向け"},{"name":"男性向け"},{"name":"専売"}]
   items=[{"id":"a","rank":5,"price":990,"genres":generic+[{"name":"巨乳"}],"release_date":"2026-08-22"},
          {"id":"b","rank":15,"price":0,"genres":generic+[{"name":"巨乳"}],"circle":None},
          {"id":"c","rank":8,"price":770,"genres":generic,"release_date":"2026-08-01"}]
   history.write_text(json.dumps([{"fetched_at":"2026-08-24T12:00:00+09:00","items":items}]))
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   self.assertEqual(report["top_genres"],[{"name":"巨乳","observed_products":2,"top10_products":1}])
   self.assertEqual(report["genre_price_summary"],[{"name":"巨乳","product_count":2,"median_price":990}])
   self.assertEqual(report["new_release_products"],1)
   self.assertEqual(report["new_release_top10_products"],1)
   self.assertEqual(report["top_circles"],[])
   self.assertEqual(report["metadata_coverage"]["genre"],3)
   self.assertEqual(report["metadata_coverage"]["meaningful_genre"],2)
   self.assertEqual(report["metadata_coverage"]["circle"],0)
