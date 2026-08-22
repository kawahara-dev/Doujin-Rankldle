import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import collector


class AnalyticsTest(unittest.TestCase):
 def snapshot(self, *items): return {'items': list(items)}
 def item(self, key, rank): return {'id': key, 'title': key.upper(), 'rank': rank}
 def write_history(self, root, ranking_type, snapshots):
  path=root/ranking_type/'history'/'2026-01-01.json'; path.parent.mkdir(parents=True); path.write_text(json.dumps(snapshots),encoding='utf-8')
 def generate(self, one, daily=None):
  temp=tempfile.TemporaryDirectory(); root=Path(temp.name)/'fanza'; analytics=Path(temp.name)/'analytics'
  self.write_history(root,'1h',one)
  if daily is not None:self.write_history(root,'24h',daily)
  patches=(patch.object(collector,'FANZA_DIR',root),patch.object(collector,'ANALYTICS_DIR',analytics))
  for context in patches:context.start()
  self.addCleanup(lambda: [context.stop() for context in reversed(patches)]); self.addCleanup(temp.cleanup)
  return collector.generate_analytics('1h','now')
 def test_latest_ten_and_out_is_null(self):
  payload=self.generate([self.snapshot(self.item('a',rank)) if rank else self.snapshot() for rank in range(1,13)])
  self.assertEqual(payload['snapshot_count'],10); self.assertEqual(payload['items'][0]['rank_history'],list(range(3,13)))
  payload=self.generate([self.snapshot(self.item('a',1)),self.snapshot(),self.snapshot(self.item('a',9))])
  self.assertEqual(payload['items'][0]['rank_history'],[1,None,9])
 def test_top10_count_rate_and_short_sample(self):
  payload=self.generate([self.snapshot(self.item('a',rank)) for rank in (1,11,10,20,5,8)])['items'][0]
  self.assertEqual((payload['top10_count'],payload['sample_count'],payload['top10_rate']),(4,6,67))
 def test_ranking_types_do_not_mix(self):
  daily=[self.snapshot(self.item('daily',1))]
  payload=self.generate([self.snapshot(self.item('hourly',2))],daily)
  self.assertEqual([item['key'] for item in payload['items']],['hourly'])
 def test_status_thresholds(self):
  cases=[(80,10,'STABLE'),(50,10,'ACTIVE'),(20,10,'VOLATILE'),(10,10,'SPIKE'),(100,1,'INSUFFICIENT DATA')]
  for rate,count,expected in cases:self.assertEqual(collector.analytics_status(rate,count),expected)
