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

 def test_stability_analysis_marks_stable_top_and_rise_persistence(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   snapshots=[{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"a","title":"A","rank":3},{"id":"b","title":"B","rank":50},{"id":"c","title":"C","rank":40}]},
    {"fetched_at":"2026-08-24T12:00:00+09:00","items":[
     {"id":"a","title":"A","rank":5},{"id":"b","title":"B","rank":8,"rank_change":42,"trend_score":9},
     {"id":"c","title":"C","rank":6,"rank_change":34,"trend_score":7}]},
    {"fetched_at":"2026-08-24T14:00:00+09:00","items":[
     {"id":"a","title":"A","rank":4},{"id":"b","title":"B","rank":60},{"id":"c","title":"C","rank":9}]}]
   history.write_text(json.dumps(snapshots), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   stability=report["stability_analysis"]
   self.assertEqual(stability["snapshot_count"],3)
   self.assertEqual(stability["stable_top_products"],[
    {"id":"a","title":"A","top10_snapshots":3,"total_snapshots":3,"observation_rate":100,"best_rank":3,"latest_rank":4},
    {"id":"c","title":"C","top10_snapshots":2,"total_snapshots":3,"observation_rate":67,"best_rank":6,"latest_rank":9}])
   self.assertEqual(stability["rise_persistence"],[
    {"id":"b","title":"B","ranking_type":"api","rank_change":42,"peak_rank":8,
     "peak_observed_at":"2026-08-24T12:00:00+09:00","latest_rank":60,
     "latest_observed_at":"2026-08-24T14:00:00+09:00","rank_after_rise":52,
     "persistence":"一過性","trend_score":9},
    {"id":"c","title":"C","ranking_type":"api","rank_change":34,"peak_rank":6,
     "peak_observed_at":"2026-08-24T12:00:00+09:00","latest_rank":9,
     "latest_observed_at":"2026-08-24T14:00:00+09:00","rank_after_rise":3,
     "persistence":"持続","trend_score":7}])

 def test_rise_persistence_pending_without_later_snapshot(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   history.write_text(json.dumps([{"fetched_at":"2026-08-24T12:00:00+09:00","items":[
    {"id":"a","title":"A","rank":5,"rank_change":20,"trend_score":8}]}]), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   self.assertEqual(report["stability_analysis"]["rise_persistence"],[
    {"id":"a","title":"A","ranking_type":"api","rank_change":20,"peak_rank":5,
     "peak_observed_at":"2026-08-24T12:00:00+09:00","latest_rank":5,
     "latest_observed_at":"2026-08-24T12:00:00+09:00","rank_after_rise":0,
     "persistence":"判定保留","trend_score":8}])
   self.assertEqual(report["stability_analysis"]["stable_top_products"][0]["observation_rate"],100)

 def test_stability_analysis_also_runs_in_legacy_mode(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"
   for kind, hour, items in (("1h", 9, [{"id":"a","title":"A","rank":8,"price":900,"rank_change":6,"status":"new"}]),
                             ("24h", 14, [{"id":"a","title":"A","rank":5,"price":900,"rank_change":3,"previous_rank":8}])):
    path=fanza/kind/"history"/"2026-08-24.json"; path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"fetched_at":f"2026-08-24T{hour:02d}:00:00+09:00","items":items}]), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p")
   self.assertEqual(report["stability_analysis"]["snapshot_count"],2)
   self.assertEqual(report["stability_analysis"]["stable_top_products"][0]["id"],"a")
   self.assertEqual(report["stability_analysis"]["stable_top_products"][0]["observation_rate"],100)

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

 def test_api_circle_ranking_counts_appearances_best_rank_and_flagship(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   snapshots=[{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"a","title":"A","rank":3,"circle":{"name":"C1"}},
     {"id":"b","title":"B","rank":15,"circle":{"name":"C1"}},
     {"id":"c","title":"C","rank":8,"circle":{"name":"C2"}}]},
    {"fetched_at":"2026-08-24T12:00:00+09:00","items":[
     {"id":"a","title":"A","rank":5,"circle":{"name":"C1"}},
     {"id":"b","title":"B","rank":9,"circle":{"name":"C1"}},
     {"id":"c","title":"C","rank":20,"circle":{"name":"C2"}}]}]
   history.write_text(json.dumps(snapshots), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   self.assertEqual(report["top_circles"],[
    {"name":"C1","observed_products":2,"top10_products":2,"total_appearances":4,"best_rank":3,
     "top10_appearances":3,"flagship_title":"A","flagship_best_rank":3},
    {"name":"C2","observed_products":1,"top10_products":1,"total_appearances":2,"best_rank":8,
     "top10_appearances":1,"flagship_title":"C","flagship_best_rank":8}])
   self.assertEqual(report["circle_coverage"],{"snapshots_with_circle":2,"total_snapshots":2,
    "coverage_share":100,"first_circle_snapshot":"2026-08-24T10:00:00+09:00"})

 def test_api_circle_partial_coverage_counts_only_circle_snapshots(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   snapshots=[{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"a","title":"A","rank":2},{"id":"b","title":"B","rank":4}]},
    {"fetched_at":"2026-08-24T12:00:00+09:00","items":[
     {"id":"a","title":"A","rank":2,"circle":{"name":"C1"}},
     {"id":"b","title":"B","rank":4,"circle":{"name":"C1"}}]},
    {"fetched_at":"2026-08-24T14:00:00+09:00","items":[
     {"id":"a","title":"A","rank":1,"circle":{"name":"C1"}},
     {"id":"b","title":"B","rank":30,"circle":{"name":"C1"}}]}]
   history.write_text(json.dumps(snapshots), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   self.assertEqual(report["top_circles"],[
    {"name":"C1","observed_products":2,"top10_products":2,"total_appearances":4,"best_rank":1,
     "top10_appearances":3,"flagship_title":"A","flagship_best_rank":1}])
   self.assertEqual(report["circle_coverage"],{"snapshots_with_circle":2,"total_snapshots":3,
    "coverage_share":67,"first_circle_snapshot":"2026-08-24T12:00:00+09:00"})
   self.assertEqual(report["metadata_coverage"]["circle"],2)

 def test_genre_price_cross_analysis_ranks_and_retention(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   snapshots=[{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"a","title":"A","rank":3,"price":900,"genres":[{"name":"巨乳"}],"rank_change":5},
     {"id":"b","title":"B","rank":15,"price":1500,"genres":[{"name":"巨乳"},{"name":"人妻"}],"rank_change":0},
     {"id":"c","title":"C","rank":8,"price":2500,"genres":[{"name":"人妻"}],"rank_change":10}]},
    {"fetched_at":"2026-08-24T12:00:00+09:00","items":[
     {"id":"a","title":"A","rank":4,"price":900,"genres":[{"name":"巨乳"}],"rank_change":-1},
     {"id":"b","title":"B","rank":12,"price":1500,"genres":[{"name":"巨乳"},{"name":"人妻"}],"rank_change":3},
     {"id":"c","title":"C","rank":9,"price":2500,"genres":[{"name":"人妻"}],"rank_change":-1}]}]
   history.write_text(json.dumps(snapshots), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   cross=report["genre_price_analysis"]
   self.assertEqual(cross["by_genre"],[
    {"name":"人妻","product_count":2,"average_rank":10,"median_rank":10,"top10_products":1,
     "top10_share":50,"rise_rate":50,"average_rank_change":3},
    {"name":"巨乳","product_count":2,"average_rank":8,"median_rank":8,"top10_products":1,
     "top10_share":50,"rise_rate":50,"average_rank_change":2}])
   self.assertEqual(cross["by_price_bucket"],[
    {"label":"〜499円","product_count":0,"top10_count":0,"top10_share":0,"top10_retention_rate":0,"average_rank":0},
    {"label":"500〜999円","product_count":1,"top10_count":1,"top10_share":100,"top10_retention_rate":100,"average_rank":4},
    {"label":"1000〜1999円","product_count":1,"top10_count":0,"top10_share":0,"top10_retention_rate":0,"average_rank":12},
    {"label":"2000〜2999円","product_count":1,"top10_count":1,"top10_share":100,"top10_retention_rate":100,"average_rank":9},
    {"label":"3000円〜","product_count":0,"top10_count":0,"top10_share":0,"top10_retention_rate":0,"average_rank":0}])

 def test_genre_price_cross_analysis_runs_in_legacy_mode_without_genres(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"
   for kind, hour, items in (("1h", 9, [{"id":"a","title":"A","rank":8,"price":900,"rank_change":6,"status":"new"}]),
                             ("24h", 14, [{"id":"a","title":"A","rank":5,"price":900,"rank_change":3,"previous_rank":8}])):
    path=fanza/kind/"history"/"2026-08-24.json"; path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"fetched_at":f"2026-08-24T{hour:02d}:00:00+09:00","items":items}]), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p")
   cross=report["genre_price_analysis"]
   self.assertEqual(cross["by_genre"],[])
   self.assertEqual(cross["by_price_bucket"][1],
    {"label":"500〜999円","product_count":1,"top10_count":1,"top10_share":100,
     "top10_retention_rate":100,"average_rank":5})

 def test_launch_pattern_classifies_all_four_types(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   snapshots=[{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"a","title":"A","rank":5,"release_date":"2026-08-24"},
     {"id":"b","title":"B","rank":60,"release_date":"2026-08-24"},
     {"id":"c","title":"C","rank":6,"release_date":"2026-08-20"},
     {"id":"d","title":"D","rank":40,"release_date":"2026-08-24"},
     {"id":"e","title":"E","rank":90,"release_date":"2026-08-10"}]},
    {"fetched_at":"2026-08-24T12:00:00+09:00","items":[
     {"id":"a","title":"A","rank":4,"release_date":"2026-08-24"},
     {"id":"b","title":"B","rank":30,"release_date":"2026-08-24"},
     {"id":"c","title":"C","rank":50,"release_date":"2026-08-20"},
     {"id":"d","title":"D","rank":35,"release_date":"2026-08-24"},
     {"id":"e","title":"E","rank":80,"release_date":"2026-08-10"}]},
    {"fetched_at":"2026-08-24T14:00:00+09:00","items":[
     {"id":"a","title":"A","rank":6,"release_date":"2026-08-24"},
     {"id":"b","title":"B","rank":8,"release_date":"2026-08-24"},
     {"id":"c","title":"C","rank":55,"release_date":"2026-08-20"},
     {"id":"d","title":"D","rank":38,"release_date":"2026-08-24"},
     {"id":"e","title":"E","rank":70,"release_date":"2026-08-10"}]}]
   history.write_text(json.dumps(snapshots), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   launch=report["launch_pattern_analysis"]
   self.assertEqual(launch["new_release_products"],4)
   self.assertEqual(launch["by_type"],{"発売直後TOP入り型":1,"じわじわ上昇型":1,"一過性型":1,"判定保留":1})
   self.assertEqual(launch["products"],[
    {"id":"a","title":"A","release_date":"2026-08-24","launch_type":"発売直後TOP入り型",
     "first_rank":5,"best_rank":4,"latest_rank":6,"days_to_top10":0,"top10_snapshots":3,"total_snapshots":3},
    {"id":"b","title":"B","release_date":"2026-08-24","launch_type":"じわじわ上昇型",
     "first_rank":60,"best_rank":8,"latest_rank":8,"days_to_top10":0,"top10_snapshots":1,"total_snapshots":3},
    {"id":"c","title":"C","release_date":"2026-08-20","launch_type":"一過性型",
     "first_rank":6,"best_rank":6,"latest_rank":55,"days_to_top10":4,"top10_snapshots":1,"total_snapshots":3},
    {"id":"d","title":"D","release_date":"2026-08-24","launch_type":"判定保留",
     "first_rank":40,"best_rank":35,"latest_rank":38,"days_to_top10":None,"top10_snapshots":0,"total_snapshots":3}])

 def test_launch_pattern_empty_without_release_dates(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"
   for kind, hour, items in (("1h", 9, [{"id":"a","title":"A","rank":8,"price":900,"rank_change":6,"status":"new"}]),
                             ("24h", 14, [{"id":"a","title":"A","rank":5,"price":900,"rank_change":3,"previous_rank":8}])):
    path=fanza/kind/"history"/"2026-08-24.json"; path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"fetched_at":f"2026-08-24T{hour:02d}:00:00+09:00","items":items}]), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p")
   launch=report["launch_pattern_analysis"]
   self.assertEqual(launch["new_release_products"],0)
   self.assertEqual(launch["by_type"],{"発売直後TOP入り型":0,"じわじわ上昇型":0,"一過性型":0,"判定保留":0})
   self.assertEqual(launch["products"],[])

 def test_dlsite_analysis_reads_day_directory_layout_and_stays_separate(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"; dlsite=root/"dlsite"
   history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   history.write_text(json.dumps([{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"f1","title":"FANZAだけの作品","rank":2,"price":1000}]}]), encoding="utf-8")
   snapshots=[("2026-08-24T100000+0900", "2026-08-24T10:00:00+09:00", [
     {"product_id":"RJ001","title":"A作品","rank":3,"price":1000,"rank_change":5,"status":"up"},
     {"product_id":"RJ002","title":"B作品","rank":15,"price":500,"rank_change":0,"status":"stay"},
     {"product_id":"RJ003","title":"C作品","rank":40,"price":2500,"rank_change":None,"status":"new"}]),
    ("2026-08-24T120000+0900", "2026-08-24T12:00:00+09:00", [
     {"product_id":"RJ001","title":"A作品","rank":5,"price":1000,"rank_change":-2,"status":"down"},
     {"product_id":"RJ002","title":"B作品","rank":8,"price":500,"rank_change":7,"status":"up"},
     {"product_id":"RJ003","title":"C作品","rank":9,"price":2500,"rank_change":31,"status":"up"}]),
    ("2026-08-24T140000+0900", "2026-08-24T14:00:00+09:00", [
     {"product_id":"RJ001","title":"A作品","rank":4,"price":1000,"rank_change":1,"status":"up"},
     {"product_id":"RJ002","title":"B作品","rank":12,"price":500,"rank_change":-4,"status":"down"},
     {"product_id":"RJ003","title":"C作品","rank":30,"price":2500,"rank_change":-21,"status":"down"}])]
   for filename, fetched_at, items in snapshots:
    path=dlsite/"history"/"2026-08-24"/f"{filename}.json"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at":fetched_at,"items":items}), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p",dlsite)
   analysis=report["dlsite_analysis"]
   self.assertEqual(analysis["snapshot_count"],3)
   self.assertEqual(analysis["unique_products"],3)
   self.assertEqual(analysis["top10_stays"],[
    {"id":"RJ001","title":"A作品","top10_snapshots":3,"observation_rate":100},
    {"id":"RJ002","title":"B作品","top10_snapshots":1,"observation_rate":33},
    {"id":"RJ003","title":"C作品","top10_snapshots":1,"observation_rate":33}])
   self.assertEqual([(m["id"],m["rank_change"]) for m in analysis["biggest_movers"]],
                    [("RJ003",31),("RJ002",7),("RJ001",5)])
   self.assertEqual(analysis["price_analysis"]["average_price"],1333)
   self.assertEqual(analysis["price_analysis"]["median_price"],1000)
   self.assertEqual(analysis["price_analysis"]["price_buckets"],[
    {"label":"〜499円","count":0,"top10_count":0},
    {"label":"500〜999円","count":1,"top10_count":1},
    {"label":"1000〜1999円","count":1,"top10_count":1},
    {"label":"2000〜2999円","count":1,"top10_count":1},
    {"label":"3000円〜","count":0,"top10_count":0}])
   self.assertEqual(analysis["new_entries"],1)
   self.assertEqual(analysis["reentries"],0)
   # FANZA aggregates are not polluted by DLsite observations.
   self.assertEqual(report["market_overview"]["unique_products"],1)
   self.assertEqual(report["market_overview"]["new_entries"],0)
   self.assertEqual(report["cross_platform"],{"matched_products":0,"match_rate":0,"rows":[]})

 def test_cross_platform_matches_normalized_titles(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); fanza=root/"fanza"; dlsite=root/"dlsite"
   history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   history.write_text(json.dumps([{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"d_1","title":"テスト作品１","rank":2,"price":1000},
     {"id":"d_2","title":"別作品","rank":5,"price":800}]}]), encoding="utf-8")
   path=dlsite/"history"/"2026-08-24"/"2026-08-24T110000+0900.json"; path.parent.mkdir(parents=True)
   path.write_text(json.dumps({"fetched_at":"2026-08-24T11:00:00+09:00","items":[
     {"product_id":"RJ001","title":"テスト作品1","rank":4,"price":1200,"rank_change":2,"status":"up"},
     {"product_id":"RJ002","title":"DLsiteだけの作品","rank":6,"price":900,"rank_change":0,"status":"stay"}]}), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),fanza,root/"r",root/"p",dlsite)
   cross=report["cross_platform"]
   self.assertEqual(cross["matched_products"],1)
   self.assertEqual(cross["match_rate"],50)
   self.assertEqual(cross["rows"],[
    {"title":"テスト作品1","fanza_rank":2,"dlsite_rank":4,
     "fanza_top10_snapshots":1,"dlsite_top10_snapshots":1,"both_top10_days":1}])

 def test_dlsite_empty_fallback_keeps_fanza_report(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); history=root/"fanza/api/history/2026-08-24.json"; history.parent.mkdir(parents=True)
   history.write_text(json.dumps([{"fetched_at":"2026-08-24T10:00:00+09:00","items":[
     {"id":"a","title":"A","rank":3,"price":900}]}]), encoding="utf-8")
   report=generate_weekly_report(datetime(2026,8,24,15,tzinfo=ZoneInfo("Asia/Tokyo")),root/"fanza",root/"r",root/"p")
   self.assertEqual(report["dlsite_analysis"]["snapshot_count"],0)
   self.assertEqual(report["dlsite_analysis"]["unique_products"],0)
   self.assertEqual(report["dlsite_analysis"]["top10_stays"],[])
   self.assertEqual(report["dlsite_analysis"]["biggest_movers"],[])
   self.assertEqual(report["dlsite_analysis"]["price_analysis"]["median_price"],0)
   self.assertEqual(report["cross_platform"],{"matched_products":0,"match_rate":0,"rows":[]})
   self.assertEqual(report["market_overview"]["unique_products"],1)

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
