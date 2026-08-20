"""Collect rankings in mock, public-watch, or authenticated API mode."""
from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.post_generator import generate_candidates
from src.providers.fanza_api import FanzaApiProvider
from src.providers.fanza_public import FanzaPublicProvider

ROOT=Path(__file__).resolve().parents[1]; DATA_DIR=ROOT/'data'; LATEST_PATH=DATA_DIR/'latest.json'; STATUS_PATH=DATA_DIR/'status.json'
FANZA_DIR=DATA_DIR/'fanza'; POSTS_PATH=DATA_DIR/'posts'/'candidates.json'; JST=ZoneInfo('Asia/Tokyo')
EXP_PER_RUN=5; EXP_PER_ITEM=1; EXP_PER_TREND=10; EXP_PER_LEVEL=100; HISTORY_DAYS=90
TREND={'new':20,'top10':20,'rise10':20,'rise20_extra':15,'rise50_extra':20,'streak3':10}
ACHIEVEMENTS=(("first_boot","FIRST BOOT","runs",1),("scanner_1","SCANNER I","runs",10),("scanner_2","SCANNER II","runs",100),("scanner_3","SCANNER III","runs",1000),("collector_1","DATA COLLECTOR I","items",100),("collector_2","DATA COLLECTOR II","items",1000),("collector_3","DATA COLLECTOR III","items",10000))

def atomic_write(path:Path,payload:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f: json.dump(payload,f,ensure_ascii=False,indent=2); f.write('\n'); tmp=Path(f.name)
 tmp.replace(path)
def read_json(path,default):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except (FileNotFoundError,json.JSONDecodeError):return default
def read_status(): return read_json(STATUS_PATH,{})
def determine_mode(env=os.environ):
 if env.get('DMM_API_ID','').strip() and env.get('DMM_AFFILIATE_ID','').strip(): return 'live'
 if env.get('PUBLIC_WATCH_ENABLED','').lower()=='true': return 'public'
 return 'mock'
def normalize_status(s):
 runs=max(0,int(s.get('total_runs',0) or 0)); items=max(0,int(s.get('total_items_collected',s.get('items_collected',0)) or 0)); mode=s.get('mode','mock')
 return {**s,'total_runs':runs,'total_items_collected':items,'items_collected':max(0,int(s.get('items_collected',0) or 0)),'runs_today':max(0,int(s.get('runs_today',0) or 0)),'first_run':s.get('first_run') or s.get('last_run'),'last_run':s.get('last_run'),'mode':mode if mode in ('mock','public','live') else 'mock','trend_events':int(s.get('trend_events',0) or 0),'processed_updates':list(s.get('processed_updates',[]))}
def experience(runs,items,trends=0): return runs*5+items+trends*10
def level_progress(exp):return exp//100+1,exp%100
def next_scheduled_run(now):
 hours=(3,9,14,22)
 for day in range(2):
  for hour in hours:
   candidate=(now+timedelta(days=day)).replace(hour=hour,minute=17,second=0,microsecond=0)
   if candidate>now:return candidate
 raise RuntimeError('schedule unavailable')
def achievement_progress(runs,items):
 values={'runs':runs,'items':items}; return [{'id':i,'name':n,'kind':k,'current':values[k],'target':t,'unlocked':values[k]>=t} for i,n,k,t in ACHIEVEMENTS]
def fetch_items(): return FanzaApiProvider().fetch()
def mock_items():
 return [{'id':f'mock-{r:03d}','title':t,'price':p,'url':f'https://example.com/mock-products/{r}','rank':r} for r,(t,p) in enumerate([('モック作品：真夏のランキング',1980),('モック作品：放課後コレクション',2480),('モック作品：秘密のスタジオ',2980),('モック作品：週末スペシャル',1480),('モック作品：プライベートタイム',3280)],1)]
def stable_key(item): return (item.get('id') or item.get('url','').split('?')[0]).strip()
def compare_rankings(items,previous,seen=None,streaks=None):
 old={stable_key(x):int(x.get('current_rank',x.get('rank',0))) for x in previous}; seen=set(seen or []); streaks=streaks or {}; result=[]
 for raw in items:
  x=dict(raw); key=stable_key(x); current=int(x.get('rank',0)); prev=old.get(key); change=(prev-current) if prev else 0
  status='new' if prev is None and key not in seen else ('reentry' if prev is None else ('up' if change>0 else 'down' if change<0 else 'stay'))
  streak=int(streaks.get(key,0))+1 if prev is not None else 1; score=TREND['new'] if status in ('new','reentry') else 0
  if current<=10 and (prev is None or prev>10):score+=TREND['top10']
  if change>=10:score+=TREND['rise10']
  if change>=20:score+=TREND['rise20_extra']
  if change>=50:score+=TREND['rise50_extra']
  if streak>=3:score+=TREND['streak3']
  x.update(key=key,current_rank=current,previous_rank=prev,rank_change=change,status=status,trend_score=min(100,score),consecutive_appearances=streak); result.append(x)
 return result
def save_history(now,payload):
 path=FANZA_DIR/'history'/f'{now.date().isoformat()}.json'; entries=read_json(path,[])
 signature=[(x['key'],x['current_rank']) for x in payload['items']]
 if not entries or [(x['key'],x['current_rank']) for x in entries[-1]['items']]!=signature: entries.append(payload); atomic_write(path,entries[-4:])
 files=sorted(path.parent.glob('*.json')); [p.unlink() for p in files[:-HISTORY_DAYS]]
def main():
 now=datetime.now(JST).replace(microsecond=0); stamp=now.isoformat(); mode=determine_mode(); old=normalize_status(read_status())
 try:
  raw=fetch_items() if mode=='live' else FanzaPublicProvider().fetch() if mode=='public' else mock_items()
  previous=read_json(FANZA_DIR/'current.json',{}).get('items',[]) if mode=='public' else []
  items=compare_rankings(raw,previous,old.get('seen_public_keys'),old.get('public_streaks')) if mode=='public' else raw
 except Exception as exc:
  if mode!='public': raise
  status={**old,'mode':'public','public_watch_status':'error','last_public_watch_error':str(exc),'items_collected':0}
  atomic_write(STATUS_PATH,status); print(f'PUBLIC WATCH ERROR: {exc}'); return
 run_date=stamp[:10]; runs=old['total_runs']+1; total=old['total_items_collected']+len(items); trends=sum(x.get('trend_score',0)>=20 for x in items) if mode=='public' else 0
 update_key='|'.join(f"{stable_key(x)}:{x.get('current_rank',x.get('rank'))}" for x in items); processed=old['processed_updates']; new_trends=trends if update_key not in processed else 0; processed=(processed+[update_key])[-100:]
 trend_total=old['trend_events']+new_trends; exp=experience(runs,total,trend_total); level,level_exp=level_progress(exp)
 status={**old,'first_run':old['first_run'] or stamp,'last_run':stamp,'total_runs':runs,'total_items_collected':total,'items_collected':len(items),'run_date':run_date,'runs_today':old['runs_today']+1 if old.get('run_date')==run_date else 1,'mode':mode,'exp':exp,'level':level,'level_exp':level_exp,'exp_to_next_level':100,'trend_events':trend_total,'processed_updates':processed}
 latest={'updated_at':stamp,'items':items}
 if mode=='public':
  payload={'fetched_at':stamp,'items':items}; atomic_write(FANZA_DIR/'current.json',payload); save_history(now,payload)
  existing=read_json(POSTS_PATH,[]); atomic_write(POSTS_PATH,generate_candidates(items,existing,now,int(os.getenv('POST_COOLDOWN_HOURS','24'))))
  status.update(public_watch_status='ok',last_public_watch_success=stamp,last_public_watch_error=None,seen_public_keys=sorted(set(old.get('seen_public_keys',[]))|{x['key'] for x in items}),public_streaks={x['key']:x['consecutive_appearances'] for x in items})
 atomic_write(LATEST_PATH,latest); atomic_write(STATUS_PATH,status); print(f'{len(items)} 件を収集しました ({stamp}, mode={mode})')
if __name__=='__main__':main()
