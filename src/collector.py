"""Collect rankings in mock, public-watch, or authenticated API mode."""
from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.post_generator import generate_candidates, generate_comment
from src.providers.fanza_api import FanzaApiProvider
from src.providers.fanza_public import FanzaAgeGateError, FanzaPublicProvider
from src.weekly_report import PAGES_DIR, REPORT_DIR, generate_weekly_report

ROOT=Path(__file__).resolve().parents[1]; DATA_DIR=ROOT/'data'; LATEST_PATH=DATA_DIR/'latest.json'; STATUS_PATH=DATA_DIR/'status.json'
FANZA_DIR=DATA_DIR/'fanza'; DEFAULT_FANZA_DIR=FANZA_DIR; POSTS_PATH=DATA_DIR/'posts'/'candidates.json'; JST=ZoneInfo('Asia/Tokyo')
ANALYTICS_DIR=DATA_DIR/'analytics'; ANALYTICS_SNAPSHOTS=10
IMPORT_PATH=DATA_DIR/'import'/'fanza.json'
EXP_PER_RUN=5; EXP_PER_ITEM=1; EXP_PER_TREND=10; EXP_PER_LEVEL=100; HISTORY_DAYS=90
TREND={'new':20,'top10':20,'rise10':20,'rise20_extra':15,'rise50_extra':20,'streak3':10}
RANKING_TYPES=('1h','24h'); CROSS_TREND_BONUS=20
ACHIEVEMENTS=(("first_boot","FIRST BOOT","runs",1),("scanner_1","SCANNER I","runs",10),("scanner_2","SCANNER II","runs",100),("scanner_3","SCANNER III","runs",1000),("collector_1","DATA COLLECTOR I","items",100),("collector_2","DATA COLLECTOR II","items",1000),("collector_3","DATA COLLECTOR III","items",10000))
SALE_FIELDS=('regular_price','discount_rate','on_sale','sale_end_raw','sale_end')

def atomic_write(path:Path,payload:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f: json.dump(payload,f,ensure_ascii=False,indent=2); f.write('\n'); tmp=Path(f.name)
 tmp.replace(path)
def read_json(path,default):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except (FileNotFoundError,json.JSONDecodeError):return default
def read_status(): return read_json(STATUS_PATH,{})
def determine_mode(env=os.environ, import_path=None):
 import_path=IMPORT_PATH if import_path is None else Path(import_path)
 if env.get('DMM_API_ID','').strip() and env.get('DMM_AFFILIATE_ID','').strip(): return 'live'
 if env.get('PUBLIC_WATCH_ENABLED','').lower()=='true': return 'public'
 if import_path.is_file(): return 'import'
 return 'mock'
def normalize_status(s):
 runs=max(0,int(s.get('total_runs',0) or 0)); items=max(0,int(s.get('total_items_collected',s.get('items_collected',0)) or 0)); mode=s.get('mode','mock')
 return {**s,'total_runs':runs,'total_items_collected':items,'items_collected':max(0,int(s.get('items_collected',0) or 0)),'runs_today':max(0,int(s.get('runs_today',0) or 0)),'first_run':s.get('first_run') or s.get('last_run'),'last_run':s.get('last_run'),'mode':mode if mode in ('mock','public','import','live') else 'mock','trend_events':int(s.get('trend_events',0) or 0),'processed_updates':list(s.get('processed_updates',[]))}
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
def ranking_type_from_import():
 payload=read_json(IMPORT_PATH,None)
 ranking_type=payload.get('ranking_type') if isinstance(payload,dict) else None
 # Legacy array imports remain 24h-compatible; envelopes must be explicit from v0.5.
 if isinstance(payload,list) or ranking_type is None: return '24h'
 if ranking_type not in RANKING_TYPES: raise RuntimeError('manual FANZA ranking import: ranking_type must be 1h or 24h')
 return ranking_type
def import_items():
 payload=read_json(IMPORT_PATH,None); ranking_type=ranking_type_from_import(); raw=payload.get('items') if isinstance(payload,dict) else payload
 if not isinstance(raw,list) or not raw: raise RuntimeError('manual FANZA ranking import has no items')
 result=[]; ranks=set(); products=set()
 for index,item in enumerate(raw,1):
  if not isinstance(item,dict): raise RuntimeError(f'manual FANZA ranking item {index} is not an object')
  if 'rank' not in item or isinstance(item.get('rank'),bool) or not isinstance(item.get('rank'),int): raise RuntimeError(f'manual FANZA ranking item {index}: rank must be an integer')
  rank=item['rank']; title=str(item.get('title','')).strip(); key=stable_key(item)
  if rank<1: raise RuntimeError(f'manual FANZA ranking item {index}: rank must be positive')
  if not title: raise RuntimeError(f'manual FANZA ranking item {index}: title is empty')
  if not key: raise RuntimeError(f'manual FANZA ranking item {index}: id and url are both missing')
  if rank in ranks: raise RuntimeError(f'manual FANZA ranking import has duplicate rank: {rank}')
  if key in products: raise RuntimeError(f'manual FANZA ranking import has duplicate item: {key}')
  price=item.get('price',0)
  if isinstance(price,bool) or not isinstance(price,int): raise RuntimeError(f'manual FANZA ranking item {index}: price must be an integer')
  ranks.add(rank); products.add(key)
  result.append({**item,'id':str(item.get('id',key)),'title':title,'url':str(item.get('url','')),'price':int(item.get('price',0) or 0),'rank':rank})
 return sorted(result,key=lambda item:item['rank'])
def import_metadata():
 payload=read_json(IMPORT_PATH,{})
 return payload if isinstance(payload,dict) else {}
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
def apply_sale_watch(items,previous):
 old={stable_key(x):x for x in previous}; events=[]
 for item in items:
  item['regular_price']=item.get('regular_price'); item['discount_rate']=item.get('discount_rate'); item['on_sale']=bool(item.get('on_sale',False)); item['sale_end_raw']=item.get('sale_end_raw'); item['sale_end']=item.get('sale_end')
  before=old.get(stable_key(item),{}); kinds=[]
  if item['on_sale'] and not before.get('on_sale',False): kinds.append('sale_start')
  if item.get('discount_rate') is not None and before.get('discount_rate') is not None and item['discount_rate']>before['discount_rate']: kinds.append('discount_up')
  if item.get('price',0)>0 and before.get('price',0)>item['price']: kinds.append('price_drop')
  if before.get('on_sale',False) and not item['on_sale']: kinds.append('sale_end')
  hot=item['on_sale'] and (int(item.get('discount_rate') or 0)>=30 or item['current_rank']<=10 or item.get('rank_change',0)>=5)
  strong=hot and int(item.get('discount_rate') or 0)>=30 and item['current_rank']<=10
  score=(20 if 'sale_start' in kinds else 0)+(25 if int(item.get('discount_rate') or 0)>=50 else 15 if int(item.get('discount_rate') or 0)>=30 else 10 if int(item.get('discount_rate') or 0)>=20 else 0)+(20 if item['current_rank']<=10 and item['on_sale'] else 0)+(10 if item.get('rank_change',0)>=5 and item['on_sale'] else 0)+(20 if item.get('cross_signal') and item['on_sale'] else 0)
  item.update(sale_events=kinds,hot_sale=hot,strong_hot_sale=strong,sale_score=min(100,score))
  events.extend({'key':f"{stable_key(item)}:{kind}:{item.get('discount_rate')}:{item.get('price')}",'item_id':stable_key(item),'event_type':kind,'discount_rate':item.get('discount_rate'),'price':item.get('price')} for kind in kinds)
 return events

def sale_candidates(items,existing,now):
 seen={x.get('event_key') for x in existing}; output=[]
 priority={'cross':1,'discount50':2,'top10':3,'discount_up':4,'sale_start':5,'hot':6}
 for item in items:
  if not item.get('on_sale'): continue
  types=(['cross'] if item.get('cross_signal') else [])+(['discount50'] if (item.get('discount_rate') or 0)>=50 else [])+(['top10'] if item['current_rank']<=10 else [])+([x for x in item.get('sale_events',[]) if x in ('discount_up','sale_start')])+(['hot'] if item.get('hot_sale') else [])
  if not types: continue
  event=min(types,key=lambda x:priority[x]); event_key=f"{stable_key(item)}:{event}:{item.get('discount_rate')}:{item.get('price')}"
  if event_key in seen: continue
  regular=f"通常 ¥{item['regular_price']:,}\n→ " if item.get('regular_price') else ''
  product=f"\n\n作品ページ👇\n{item['url']}" if item.get('url') else ''
  comment=generate_comment(item,'24h','sale')
  text=f"【FANZA SALE WATCH】\n\n💸 {item.get('discount_rate') or 0}%OFF\n🔥 24時間ランキング #{item['current_rank']}\n\n「{item['title']}」\n\n{regular}¥{item['price']:,}\n\n💬 RankIdleメモ\n{comment}{product}"
  output.append({'key':item['key'],'event_key':event_key,'event_type':event,'title':item['title'],'url':item.get('url',''),'ranking_type':'24h','sale_score':item['sale_score'],'trend_score':item.get('trend_score',0),'current_rank':item['current_rank'],'previous_rank':item.get('previous_rank'),'rank_change':item.get('rank_change',0),'comment':comment,'text':text,'generated_at':now.isoformat()})
 return sorted(output,key=lambda x:(priority[x['event_type']],-x['sale_score']))[:5]
def ranking_dir(ranking_type): return FANZA_DIR/ranking_type
def posts_path(ranking_type):
 # Preserve callers which patch the historical POSTS_PATH test seam.
 return POSTS_PATH.parent/f'fanza_{ranking_type}_candidates.json'
def migrate_legacy_fanza():
 """Copy v0.4 data into 24h storage. The legacy files are deliberately retained."""
 target=ranking_dir('24h'); legacy_current=FANZA_DIR/'current.json'; target_current=target/'current.json'
 if legacy_current.is_file() and not target_current.exists(): atomic_write(target_current,read_json(legacy_current,{}))
 legacy_history=FANZA_DIR/'history'
 if legacy_history.is_dir():
  for source in legacy_history.glob('*.json'):
   destination=target/'history'/source.name
   if not destination.exists(): atomic_write(destination,read_json(source,[]))
def save_history(now,payload,ranking_type='24h'):
 path=ranking_dir(ranking_type)/'history'/f'{now.date().isoformat()}.json'; entries=read_json(path,[])
 signature=[(stable_key(x),x.get('current_rank',x.get('rank'))) for x in payload['items']]
 if not entries or [(stable_key(x),x.get('current_rank',x.get('rank'))) for x in entries[-1]['items']]!=signature: entries.append(payload); atomic_write(path,entries[-4:])
 files=sorted(path.parent.glob('*.json')); [p.unlink() for p in files[:-HISTORY_DAYS]]
def analytics_status(rate,sample_count):
 if sample_count<2:return 'INSUFFICIENT DATA'
 if rate>=80:return 'STABLE'
 if rate>=50:return 'ACTIVE'
 if rate>=20:return 'VOLATILE'
 return 'SPIKE'
def history_snapshots(ranking_type):
 """Return the latest snapshots for one ranking, oldest first."""
 snapshots=[]
 for path in sorted((ranking_dir(ranking_type)/'history').glob('*.json')):
  entries=read_json(path,[])
  if isinstance(entries,list): snapshots.extend(x for x in entries if isinstance(x,dict) and isinstance(x.get('items'),list))
 return snapshots[-ANALYTICS_SNAPSHOTS:]
def generate_analytics(ranking_type,generated_at=None):
 """Build the compact Pages payload without requiring history fetches in browsers."""
 snapshots=history_snapshots(ranking_type); sample_count=len(snapshots); keys=[]; titles={}
 for snapshot in snapshots:
  for item in snapshot['items']:
   key=stable_key(item)
   if key and key not in titles: keys.append(key)
   if key: titles[key]=str(item.get('title',''))
 items=[]
 for key in keys:
  ranks=[]
  for snapshot in snapshots:
   match=next((x for x in snapshot['items'] if stable_key(x)==key),None)
   rank=match.get('current_rank',match.get('rank')) if match else None
   ranks.append(int(rank) if isinstance(rank,int) and not isinstance(rank,bool) and rank>0 else None)
  top10=sum(rank is not None and rank<=10 for rank in ranks)
  rate=round(top10/sample_count*100) if sample_count else 0
  items.append({'key':key,'title':titles[key],'rank_history':ranks,'top10_count':top10,'sample_count':sample_count,'top10_rate':rate,'analytics_status':analytics_status(rate,sample_count)})
 payload={'ranking_type':ranking_type,'generated_at':generated_at or datetime.now(JST).replace(microsecond=0).isoformat(),'snapshot_count':sample_count,'items':items}
 output_dir=ANALYTICS_DIR if FANZA_DIR==DEFAULT_FANZA_DIR else FANZA_DIR.parent/'analytics'
 atomic_write(output_dir/f'fanza_{ranking_type}.json',payload)
 return payload
def weekly_report_dirs():
 """Keep reports beside an injected FANZA directory during isolated runs."""
 if FANZA_DIR==DEFAULT_FANZA_DIR:return REPORT_DIR,PAGES_DIR
 data_dir=FANZA_DIR.parent
 return data_dir/'reports'/'weekly',data_dir/'docs'/'data'/'reports'/'weekly'
def add_cross_signals(items,other_items,ranking_type):
 other={stable_key(x):x for x in other_items if x.get('rank_change',0)>0}; signals=[]
 for item in items:
  match=other.get(stable_key(item))
  if item.get('rank_change',0)>0 and match:
   item['cross_signal']=True; item['trend_score']=min(100,item.get('trend_score',0)+CROSS_TREND_BONUS)
   one=item if ranking_type=='1h' else match; daily=match if ranking_type=='1h' else item
   signals.append({'key':item['key'],'title':item['title'],'url':item.get('url',''),'ranking_type':'cross','trend_score':item['trend_score'],
    'previous_rank':item.get('previous_rank'),'current_rank':item['current_rank'],'rank_change':item['rank_change'],
    'one_hour':{'previous_rank':one.get('previous_rank'),'current_rank':one['current_rank']},
    'twenty_four_hour':{'previous_rank':daily.get('previous_rank'),'current_rank':daily['current_rank']}})
 return signals
def cross_candidate(signal,now):
 one,daily=signal['one_hour'],signal['twenty_four_hour']
 product=f"\n\n作品ページ👇\n{signal['url']}" if signal.get('url') else ''
 comment=generate_comment(signal,'cross','cross')
 return {**signal,'comment':comment,'generated_at':now.isoformat(),'text':f"【FANZA CROSS TREND】\n🔥 1H・24Hともに上昇\n\n「{signal['title']}」\n\n1H: #{one['previous_rank']} → #{one['current_rank']}\n24H: #{daily['previous_rank']} → #{daily['current_rank']}\n\n💬 RankIdleメモ\n{comment}{product}"}
def main():
 now=datetime.now(JST).replace(microsecond=0); stamp=now.isoformat(); mode=determine_mode(); old=normalize_status(read_status()); age_gate=False
 ranking_mode=False; ranking_type='24h'
 migrate_legacy_fanza()
 try:
  raw=fetch_items() if mode=='live' else FanzaPublicProvider().fetch() if mode=='public' else import_items() if mode=='import' else mock_items()
  ranking_type=ranking_type_from_import() if mode=='import' else '24h'
  ranking_mode=mode in ('public','import'); previous=read_json(ranking_dir(ranking_type)/'current.json',{}).get('items',[]) if ranking_mode else []
  bucket=old.get('rankings',{}).get(f'fanza_{ranking_type}',{})
  items=compare_rankings(raw,previous,bucket.get('seen_keys'),bucket.get('streaks')) if ranking_mode else raw
 except FanzaAgeGateError as exc:
  status={**old,'mode':'public','public_watch_status':'age_gate','last_public_watch_error':'FANZA age verification page reached','items_collected':0}
  atomic_write(STATUS_PATH,status); print(f'PUBLIC WATCH AGE GATE: {exc}')
  if not IMPORT_PATH.is_file(): return
  age_gate=True; mode='import'; ranking_mode=True; ranking_type=ranking_type_from_import(); raw=import_items(); bucket=old.get('rankings',{}).get(f'fanza_{ranking_type}',{})
  previous=read_json(ranking_dir(ranking_type)/'current.json',{}).get('items',[]); items=compare_rankings(raw,previous,bucket.get('seen_keys'),bucket.get('streaks'))
 except Exception as exc:
  if mode!='public': raise
  status={**old,'mode':'public','public_watch_status':'error','last_public_watch_error':str(exc),'items_collected':0}
  atomic_write(STATUS_PATH,status); print(f'PUBLIC WATCH ERROR: {exc}'); return
 run_date=stamp[:10]; trends=sum(x.get('trend_score',0)>=20 for x in items) if mode in ('public','import') else 0
 content_key='|'.join(f"{stable_key(x)}:{x.get('current_rank',x.get('rank'))}" for x in items)
 captured=str(import_metadata().get('captured_at','')).strip() if mode=='import' else ''
 update_key=f'{ranking_type}:captured:{captured}' if captured else f'{ranking_type}:content:{content_key}'
 content_update=f'{ranking_type}:content:{content_key}'; processed=old['processed_updates']
 legacy_keys=([f'captured:{captured}'] if captured else [])+[f'content:{content_key}'] if ranking_type=='24h' else []
 duplicate=mode=='import' and (update_key in processed or content_update in processed or any(key in processed for key in legacy_keys))
 if duplicate:
  # A repeated manual import is only a heartbeat. In particular, do not persist the
  # comparison performed above: doing so would advance streaks and could regenerate
  # ranking, cross-trend, sale, achievement, or progression state.
  status={**old,'last_run':stamp,'duplicate_import':True}
  atomic_write(STATUS_PATH,status); print(f'0 件を収集しました ({stamp}, mode={mode}, ranking={ranking_type}, duplicate=true)'); return
 runs=old['total_runs']+(0 if duplicate else 1); total=old['total_items_collected']+(0 if duplicate else len(items)); new_trends=0 if duplicate else trends
 if not duplicate: processed=(processed+[update_key,content_update])[-200:]
 trend_total=old['trend_events']+new_trends; exp=experience(runs,total,trend_total); level,level_exp=level_progress(exp)
 rankings=dict(old.get('rankings',{})); name=f'fanza_{ranking_type}'; prior=dict(rankings.get(name,{}))
 if ranking_mode:
  prior.update(last_run=stamp,items_collected=0 if duplicate else len(items),total_runs=int(prior.get('total_runs',0))+(0 if duplicate else 1),total_items=int(prior.get('total_items',0))+(0 if duplicate else len(items)),trend_events=int(prior.get('trend_events',0))+(0 if duplicate else trends),seen_keys=sorted(set(prior.get('seen_keys',[]))|{x['key'] for x in items}),streaks={x['key']:x['consecutive_appearances'] for x in items})
  rankings[name]=prior
 status={**old,'first_run':old['first_run'] or stamp,'last_run':stamp,'total_runs':runs,'total_items_collected':total,'items_collected':0 if duplicate else len(items),'run_date':run_date,'runs_today':old['runs_today']+(0 if duplicate else 1) if old.get('run_date')==run_date else (0 if duplicate else 1),'mode':mode,'exp':exp,'level':level,'level_exp':level_exp,'exp_to_next_level':100,'trend_events':trend_total,'processed_updates':processed,'duplicate_import':duplicate,'ranking_type':ranking_type,'rankings':rankings}
 latest={'updated_at':stamp,'ranking_type':ranking_type,'items':items}
 if ranking_mode:
  other_type='24h' if ranking_type=='1h' else '1h'; other=read_json(ranking_dir(other_type)/'current.json',{}).get('items',[])
  crosses=add_cross_signals(items,other,ranking_type)
  sale_events=apply_sale_watch(items,previous) if ranking_type=='24h' else []
  payload={'fetched_at':stamp,'ranking_type':ranking_type,'items':items}; atomic_write(ranking_dir(ranking_type)/'current.json',payload); save_history(now,payload,ranking_type)
  generate_analytics(ranking_type,stamp)
  existing=read_json(posts_path(ranking_type),[]); candidates=generate_candidates(items,existing,now,int(os.getenv('POST_COOLDOWN_HOURS','24')),ranking_type)
  candidates.extend(cross_candidate(x,now) for x in crosses)
  if ranking_type=='24h': candidates.extend(sale_candidates(items,candidates,now))
  atomic_write(posts_path(ranking_type),candidates[-200:])
  daily=items if ranking_type=='24h' else other; active=[x for x in daily if x.get('on_sale')]
  sale_seen=set(old.get('sale_seen_events',[])); sale_seen.update(x['key'] for x in sale_events)
  sale_products=set(old.get('sale_products_seen',[])); sale_products.update(stable_key(x) for x in active)
  status['sale_seen_events']=sorted(sale_seen)[-1000:]; status['sale_products_seen']=sorted(sale_products)
  status['sale_achievements']={'sale_hunter_1':len(sale_products)>=10,'sale_hunter_2':len(sale_products)>=100,'bargain_radar':any((x.get('discount_rate') or 0)>=50 for x in active) or old.get('sale_achievements',{}).get('bargain_radar',False),'hot_deal':any(x.get('strong_hot_sale') for x in active) or old.get('sale_achievements',{}).get('hot_deal',False)}
  status['market_signals']={'1h_max_rise':max([x.get('rank_change',0) for x in (items if ranking_type=='1h' else other)]+[0]),'24h_max_rise':max([x.get('rank_change',0) for x in daily]+[0]),'cross_trend':len(crosses),'new_entry':sum(x.get('status') in ('new','reentry') for x in items),'active_sales':len(active),'hot_sales':sum(bool(x.get('hot_sale')) for x in active),'max_discount':max([int(x.get('discount_rate') or 0) for x in active]+[0])}
  watch_fields={'public_watch_status':'ok','last_public_watch_success':stamp,'last_public_watch_error':None} if mode=='public' else {'public_watch_status':'age_gate','last_public_watch_error':'FANZA age verification page reached'} if age_gate else {}
  status.update(**watch_fields,input_source='manual_import' if mode=='import' else 'public_watch')
 atomic_write(LATEST_PATH,latest); atomic_write(STATUS_PATH,status)
 if ranking_mode:
  report_dir,pages_dir=weekly_report_dirs()
  generate_weekly_report(now,FANZA_DIR,report_dir,pages_dir)
 print(f'{len(items)} 件を収集しました ({stamp}, mode={mode}, ranking={ranking_type})')
if __name__=='__main__':main()
