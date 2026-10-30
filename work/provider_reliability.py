"""Bounded US-only provider probe; raw results kept for reproducibility."""
import concurrent.futures
import datetime as dt
import json
import math
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'composite/provider_reliability'
MARKETS={s:(106 if s in {'TSM','ASX','UMC','STM'} else 105) for s in json.loads((ROOT/'test_symbols.json').read_text())}
BENCH={'SKHY':24.05,'TSM':28.64,'ASML':41.15}

def num(value):
    if isinstance(value,bool):return None
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def parse_em(data):
    if data.get('rc')!=0:raise ValueError('Eastmoney application error')
    records=[]
    for d in (data.get('data') or {}).get('diff',[]):
        symbol=d.get('f12')
        if symbol not in MARKETS or d.get('f13')!=MARKETS[symbol]:raise ValueError('US identity mismatch')
        pe=num(d.get('f115'))
        records.append({'symbol':symbol,'provider':'东方财富','pe_ttm':pe if pe!=0 else None,'price':num(d.get('f2')),'quote_epoch':num(d.get('f124')),'currency':'USD','raw_field':'f115','eps_ttm':None})
    if len({r['symbol'] for r in records})!=len(records):raise ValueError('Duplicate symbol')
    return records

def parse_futu(text,symbol):
    marker='window.__INITIAL_STATE__='
    pos=text.find(marker)
    if pos<0:raise ValueError('Futu page state missing')
    state,_=json.JSONDecoder().raw_decode(text[pos+len(marker):])
    d=state['stock_info']
    if d.get('stockCode')!=symbol or d.get('marketLabel')!='US':raise ValueError('Futu US identity mismatch')
    pe=num(d.get('peTtm'));epoch=num(d.get('exchangeDataTimeMs'))
    return [{'symbol':symbol,'provider':'富途公开页','pe_ttm':pe if pe!=0 else None,'eps_ttm':num(d.get('epsTtm')),'price':num(d.get('priceNominal')),'quote_epoch':epoch/1000 if epoch else None,'currency':'USD','raw_field':'peTtm / epsTtm','premarket_separate':d.get('before_open_stock_info'),'page_market_status':d.get('market_status_text')}]

def parse_tencent(text):
    records=[]
    for symbol,raw in re.findall(r'v_us(\w+)="([^"]*)"',text):
        f=raw.split('~')
        if symbol not in MARKETS or len(f)<48:continue
        if f[35]!='USD':raise ValueError('Non-USD quote')
        records.append({'symbol':symbol,'provider':'腾讯','generic_pe':num(f[39]),'pe_ttm':None,'eps_generic':num(f[47]),'price':num(f[3]),'quote_time_et':f[30],'currency':f[35],'raw_field':'fields[39]，未明示TTM'})
    return records

def fetch(provider,round_no,symbol=None):
    key=f'{provider}_{symbol or "batch"}_{round_no}'
    if provider=='eastmoney':
        url='https://push2.eastmoney.com/api/qt/ulist.np/get?'+urlencode({'secids':','.join(f'{m}.{s}' for s,m in MARKETS.items()),'fltt':2,'invt':2,'fields':'f2,f12,f13,f14,f115,f124'})
        referer='https://quote.eastmoney.com/'
    elif provider=='tencent':url='https://qt.gtimg.cn/q='+','.join('us'+s for s in MARKETS);referer='https://gu.qq.com/'
    else:url=f'https://www.futunn.com/stock/{symbol}-US';referer='https://www.futunn.com/'
    raw=OUT/(key+'.raw');started=time.monotonic()
    p=subprocess.run(['curl','-sS','--max-time','25','--connect-timeout','10','-A','Mozilla/5.0','-e',referer,'-o',str(raw),'-w','%{http_code}',url],capture_output=True)
    result={'provider':provider,'round':round_no,'symbol':symbol,'url':url,'http':p.stdout.decode().strip(),'curl_exit':p.returncode,'seconds':round(time.monotonic()-started,3),'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'error':p.stderr.decode().strip(),'records':[]}
    if p.returncode==0 and result['http']=='200':
        try:
            text=raw.read_bytes().decode('gb18030' if provider=='tencent' else 'utf-8',errors='replace')
            records=parse_em(json.loads(text)) if provider=='eastmoney' else parse_tencent(text) if provider=='tencent' else parse_futu(text,symbol)
            result['records']=[dict(r,retrieved_utc=result['retrieved_utc'],url=url) for r in records]
        except (ValueError,KeyError,TypeError) as e:result['error']=str(e)
    result['ok']=bool(result['records']) and not result['error']
    (OUT/(key+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[];blocked=set()
    # First pass checks full coverage; second checks repeated batch and three difficult listings.
    for round_no in (1,2):
        tasks=[('eastmoney',None),('tencent',None)]+[('futu',s) for s in (MARKETS if round_no==1 else BENCH)]
        # Small sequential groups ensure a 429 stops further calls to that provider.
        for start in range(0,len(tasks),3):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures=[pool.submit(fetch,p,round_no,s) for p,s in tasks[start:start+3] if p not in blocked]
                for future in futures:
                    r=future.result();results.append(r)
                    if r['http']=='429':blocked.add(r['provider'])
                    print(json.dumps({k:r[k] for k in ('provider','round','symbol','http','ok','seconds','error')}),flush=True)
    (OUT/'runs.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    for provider in ('eastmoney','tencent','futu'):
        runs=[r for r in results if r['provider']==provider]
        print(provider, 'success',sum(r['ok'] for r in runs),'/',len(runs),'symbols',len({d['symbol'] for r in runs for d in r['records']}),flush=True)

if __name__=='__main__':main()
