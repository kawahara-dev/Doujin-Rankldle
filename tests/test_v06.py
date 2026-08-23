import unittest
from datetime import datetime
from pathlib import Path
from src import collector
from src.post_generator import generate_candidates, post_text

class SaleWatchV06Test(unittest.TestCase):
 def item(self,**values):
  return {**{"id":"a","key":"a","title":"A","rank":7,"current_rank":7,"previous_rank":12,"rank_change":5,"price":3080,"regular_price":4400,"discount_rate":30,"on_sale":True},**values}
 def test_sale_start_hot_and_score(self):
  items=[self.item()]; events=collector.apply_sale_watch(items,[self.item(on_sale=False,discount_rate=None)])
  self.assertIn("sale_start",items[0]["sale_events"]); self.assertTrue(items[0]["strong_hot_sale"]); self.assertLessEqual(items[0]["sale_score"],100); self.assertEqual(events[0]["event_type"],"sale_start")
 def test_discount_up_price_drop_and_sale_end(self):
  current=self.item(price=2156,discount_rate=50); collector.apply_sale_watch([current],[self.item()]); self.assertEqual(current["sale_events"],["discount_up","price_drop"])
  ended=self.item(on_sale=False,discount_rate=None); collector.apply_sale_watch([ended],[self.item()]); self.assertIn("sale_end",ended["sale_events"])
 def test_event_candidate_deduplication(self):
  item=self.item(); collector.apply_sale_watch([item],[self.item(on_sale=False)]); first=collector.sale_candidates([item],[],datetime.now()); self.assertEqual(collector.sale_candidates([item],first,datetime.now()),[])
 def test_hourly_zero_price_remains_sale_agnostic(self):
  hourly=collector.compare_rankings([{"id":"a","title":"A","rank":1,"price":0,"url":"x"}],[]); self.assertEqual(hourly[0]["price"],0); self.assertNotIn("on_sale",hourly[0])
 def test_ranking_candidate_and_post_keep_product_url(self):
  item=self.item(url="https://example.test/product/a",status="up",trend_score=20)
  candidate=generate_candidates([item],[],datetime.now())[0]
  self.assertEqual(candidate["url"],item["url"])
  self.assertIn(f'作品ページ👇\n{item["url"]}\n\n#FANZA',candidate["text"])
 def test_all_ranking_post_types_put_url_before_hashtags(self):
  for values in ({"status":"new","previous_rank":None}, {"status":"up","previous_rank":12,"current_rank":8}, {"status":"up","previous_rank":20,"current_rank":15}):
   with self.subTest(values=values):
    item=self.item(url="https://example.test/product/a",**values)
    self.assertIn(f'作品ページ👇\n{item["url"]}\n\n#FANZA',post_text(item))
 def test_sale_candidate_and_post_keep_product_url(self):
  item=self.item(url="https://example.test/product/a"); collector.apply_sale_watch([item],[self.item(on_sale=False)])
  candidate=collector.sale_candidates([item],[],datetime.now())[0]
  self.assertEqual(candidate["url"],item["url"])
  self.assertIn(f'作品ページ👇\n{item["url"]}',candidate["text"])
 def test_missing_legacy_candidate_url_is_safe_and_pages_limit_is_three(self):
  # Legacy candidates are rendered from their completed text, without reading url.
  source=Path("docs/app.js").read_text(encoding="utf-8")
  self.assertIn(".slice(0, 3)",source)
  self.assertNotIn("copyPost(item.url",source)
