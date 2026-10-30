"""Selected PE TTM source. No silent switch of accounting methodology."""
import datetime as dt
import json
from pathlib import Path
from provider_reliability import fetch,OUT,MARKETS,BENCH

CACHE=OUT/'selected.json'
SCOPE='PE TTM主源选定东方财富美股批量f115；富途公开页交叉检查，腾讯普通PE不作TTM替代。仅取本行美股证券，不跨上市市场补数。G列为独立盘中快照，时间及冲突见BC/DO和PE对照页；不与其他列旧快照混算。失败保留原时间缓存并标明。长桥接入不作为前置条件。'

def select(runs):
    em={};futu={}
    for r in runs:
        if not r['ok']:continue
        target=em if r['provider']=='eastmoney' else futu if r['provider']=='futu' else None
        if target is not None:
            for d in r['records']:target[d['symbol']]=d
    records=[]
    for symbol in MARKETS:
        d=dict(em.get(symbol,{'symbol':symbol,'pe_ttm':None}))
        issues=[];f=futu.get(symbol)
        if d.get('pe_ttm') is None:issues.append('主源未取得有效TTM；不拿普通PE替代')
        elif d['pe_ttm']<0:issues.append('主源返回负PE；不按正盈利估值解释')
        if symbol in BENCH:issues.append('此前同收盘价TTM与长桥截图不一致，盈利口径差异仍未解决；当前盘中值不直接与旧截图比较')
        if f and d.get('pe_ttm') and f.get('pe_ttm') and d.get('price') and f.get('price'):
            # Compare implied earnings only as a diagnostic; never publish this as source EPS.
            a=d['price']/d['pe_ttm'];b=f['price']/f['pe_ttm']
            d['implied_earnings_gap_to_futu']=abs(a-b)/max(abs(b),1e-12)
            if d['implied_earnings_gap_to_futu']>.01:issues.append('按各自价格/PE诊断的盈利分母与富途偏差超过1%；非供应商EPS字段，待核验')
        d['issues']=issues;records.append(d)
    return {'provider':'eastmoney','metric':'PE TTM','field':'f115','fetch_status':'fresh_request','selected_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'policy':SCOPE,'records':records}

def read_selected():
    if not CACHE.exists():return {'fetch_status':'missing','records':[]}
    return json.loads(CACHE.read_text())

def quote_time(record):
    epoch=record.get('quote_epoch')
    return dt.datetime.fromtimestamp(epoch,dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S 北京时间') if epoch else '行情时间未提供'

def apply_ttm(payload):
    selected=read_selected();lookup={r['symbol']:r for r in selected['records']}
    payload['rows'][0][6]='PE TTM（东财美股快照；时点见BC）'
    for row in payload['rows'][1:]:
        r=lookup.get(row[3],{});row[6]=r.get('pe_ttm') if r.get('pe_ttm') is not None else '美股TTM未取得'
        note=f'仅美股{row[3]}；PE TTM来源东方财富f115；行情时间{quote_time(r)}；抓取UTC {r.get("retrieved_utc","未取得")}；状态{selected["fetch_status"]}；G列独立快照，不与其他列旧价格/市值混算；'
        note+='；'.join(r.get('issues',[])) or '供应商原始TTM，未独立审计盈利分母；'
        for j in (54,118):row[j]=note+'；预测EPS保留原值；不跨市场补数，不以市值÷股价反推股数生成利润。'
    payload['ttm_source']=selected
    payload.setdefault('source_scope',{})['policy']=SCOPE
    # Keep future full publications consistent with the targeted online patch.
    if 'black_cells' in payload:
        g_cells={f'G{i}' for i in range(2,len(payload['rows'])+1)}
        payload['black_cells']=[a for a in payload['black_cells'] if a not in g_cells]
        payload['black_cells'] += [f'G{i}' for i,row in enumerate(payload['rows'][1:],2) if row[3] in lookup and lookup[row[3]].get('pe_ttm') is not None and not lookup[row[3]].get('issues')]
    return payload

def refresh():
    OUT.mkdir(parents=True,exist_ok=True)
    result=fetch('eastmoney','refresh')
    if result['ok']:
        old=read_selected();oldmap={r['symbol']:r for r in old['records']}
        snapshot=select([result])
        for i,r in enumerate(snapshot['records']):
            if r.get('pe_ttm') is None and r['symbol'] in oldmap:
                snapshot['records'][i]={**oldmap[r['symbol']],'issues':oldmap[r['symbol']].get('issues',[])+['本次缺项；保留旧快照原时间']}
        snapshot['fetch_status']='partial_cache' if any('本次缺项' in str(r['issues']) for r in snapshot['records']) else 'fresh_request'
    else:
        snapshot=read_selected();snapshot['fetch_status']='request_failed_using_last_success';snapshot['last_error']=result['error'] or result['http']
    CACHE.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    return snapshot

if __name__=='__main__':
    snapshot=refresh()
    print(json.dumps({'status':snapshot['fetch_status'],'records':len(snapshot['records'])}))
