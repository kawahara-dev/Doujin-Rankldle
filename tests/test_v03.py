import os, unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from src import collector
from src.post_generator import generate_candidates
from src.providers.fanza_public import parse_ranking_html

class V03Test(unittest.TestCase):
 def test_mode_priority(self):
  self.assertEqual(collector.determine_mode({'PUBLIC_WATCH_ENABLED':'true'}),'public')
  self.assertEqual(collector.determine_mode({'DMM_API_ID':'a','DMM_AFFILIATE_ID':'b','PUBLIC_WATCH_ENABLED':'true'}),'live')
  self.assertEqual(collector.determine_mode({'DMM_API_ID':'a'}),'mock')
 def test_parser(self):
  items=parse_ranking_html(Path('tests/fixtures/fanza_ranking.html').read_text(),'https://www.dmm.co.jp/rank/')
  self.assertEqual([(x['rank'],x['title'],x['price']) for x in items],[(1,'作品A',1980),(12,'作品B',980)])
 def test_diff_status_and_score(self):
  old=[{'id':'a','rank':38},{'id':'b','rank':2},{'id':'c','rank':3}]
  new=[{'id':'a','rank':12,'title':'A','url':'a'},{'id':'b','rank':4,'title':'B','url':'b'},{'id':'c','rank':3,'title':'C','url':'c'},{'id':'d','rank':8,'title':'D','url':'d'}]
  got={x['id']:x for x in collector.compare_rankings(new,old)}
  self.assertEqual((got['a']['status'],got['a']['rank_change'],got['a']['trend_score']),('up',26,35))
  self.assertEqual(got['b']['status'],'down'); self.assertEqual(got['c']['status'],'stay'); self.assertEqual(got['d']['status'],'new')
  self.assertEqual(collector.compare_rankings([{'id':'z','rank':5,'title':'Z','url':'z'}],[],{'z'})[0]['status'],'reentry')
 def test_candidates_and_cooldown(self):
  now=datetime(2026,1,1,tzinfo=timezone.utc); item={'key':'a','title':'A','current_rank':12,'previous_rank':38,'rank_change':26,'status':'up','trend_score':35}
  first=generate_candidates([item],[],now); self.assertEqual(len(first),1); self.assertIn('+26ランク',first[0]['text'])
  self.assertEqual(len(generate_candidates([item],first,now)),1)
 def test_next_scan_uses_cron_not_last_run(self):
  now=datetime(2026,1,1,9,18,tzinfo=timezone.utc)
  self.assertEqual(collector.next_scheduled_run(now),datetime(2026,1,1,14,17,tzinfo=timezone.utc))
 def test_public_failure_preserves_current(self):
  import json, tempfile
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); fanza=root/'fanza'; fanza.mkdir(); current=fanza/'current.json'; current.write_text('{"items":[{"id":"safe"}]}')
   latest=root/'latest.json'; latest.write_text('{"items":[{"id":"safe"}]}'); status=root/'status.json'
   with patch.dict(os.environ,{'PUBLIC_WATCH_ENABLED':'true'},clear=True), patch.object(collector,'DATA_DIR',root), patch.object(collector,'FANZA_DIR',fanza), patch.object(collector,'LATEST_PATH',latest), patch.object(collector,'STATUS_PATH',status), patch.object(collector.FanzaPublicProvider,'fetch',side_effect=RuntimeError('HTTP 403')):
    collector.main()
   self.assertEqual(json.loads(current.read_text())['items'][0]['id'],'safe')
   self.assertEqual(json.loads(latest.read_text())['items'][0]['id'],'safe')
   self.assertEqual(json.loads(status.read_text())['public_watch_status'],'error')
 def test_experience_includes_trends(self): self.assertEqual(collector.experience(1,2,1),17)
