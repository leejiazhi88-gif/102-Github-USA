"""Collect US annual EPS and reported financials for the O:Q repair."""
import argparse,concurrent.futures,datetime as dt,json,sys,subprocess
from pathlib import Path
from urllib.parse import urlencode
import collect_forecast_repair as collector
from forecast_fields import annual_forecasts
from quarter_fields import fiscal_month,flat
ROOT=Path(__file__).parent;OUT=ROOT/'opq_repair';OUT.mkdir(exist_ok=True)
collector.OUT=OUT

def batches(jobs):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for start in range(0,len(jobs),16):
            results=list(pool.map(lambda a:collector.fetch(*a),jobs[start:start+16]))
            print('Fetched',min(start+16,len(jobs)),'/',len(jobs),flush=True)
            if any(r['http'] in ('403','429') for r in results):raise RuntimeError('Provider access restriction; stopped')
    retry=[]
    for s,k in jobs:
        r=json.loads((OUT/f'{s}_{k}.json').read_text())
        if r.get('http')=='000' or str(r.get('http')).startswith('5'):retry.append((s,k))
    if retry:
        already_refresh='--refresh' in sys.argv
        if not already_refresh:sys.argv.append('--refresh')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for r in pool.map(lambda a:collector.fetch(*a),retry):print('Retry',r['symbol'],r['kind'],r['http'],flush=True)
        if not already_refresh:sys.argv.remove('--refresh')

def json_source(url,path):
    if path.exists() and '--refresh' not in sys.argv:return json.loads(path.read_text())
    proc=subprocess.run(['curl','-sS','--max-time','20','-A','Mozilla/5.0','-e','https://quote.eastmoney.com/',url],capture_output=True,text=True,check=True)
    env={'url':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'data':json.loads(proc.stdout)}
    path.write_text(json.dumps(env,ensure_ascii=False,indent=2));return env

def secondary_us_sources(rows,shares,asof):
    from annual_profit_fields import reported_annual,fiscal_end
    for row in rows[1:]:
        symbol=row[3]
        if symbol not in shares:
            code=symbol.replace('.','_')
            url='https://push2.eastmoney.com/api/qt/ulist.np/get?'+urlencode({'secids':','.join(f'{m}.{code}' for m in (105,106,107)),'fltt':2,'invt':2,'fields':'f12,f13,f14,f38,f124'})
            env=json_source(url,OUT/f'{symbol}_us_lookup.json');items=(env['data'].get('data') or {}).get('diff') or []
            matches=[q for q in items if q.get('f12')==code and q.get('f13') in (105,106,107)]
            if len(matches)==1:
                q=matches[0];shares[symbol]={'symbol':symbol,'shares':q.get('f38'),'source':env['url'],'retrieved_utc':env['retrieved_utc'],'resolved_market_id':q['f13'],'resolution_note':f'旧市场代码未返回；美股市场重新核对为{q["f13"]}.{code}，名称{q.get("f14","")}'}
        forecast=json.loads((OUT/f'{symbol}_forecast.json').read_text());forecasts,_=annual_forecasts(forecast,symbol);month,_=fiscal_month(forecast,row)
        if 2026 in forecasts or not month or fiscal_end(2026,month)>asof:continue
        def load(kind):
            path=OUT/f'{symbol}_{kind}.json';return json.loads(path.read_text()) if path.exists() else {}
        if 2026 in reported_annual(load('annual'),load('financial_page'),symbol,month,asof):continue
        url='https://datacenter-web.eastmoney.com/api/data/v1/get?'+urlencode({'reportName':'RPT_USF10_FN_GMAININDICATOR','columns':'ALL','filter':f'(SECURITY_CODE="{symbol.replace(".","_")}")','pageSize':100,'pageNumber':1,'sortColumns':'REPORT_DATE','sortTypes':-1,'source':'WEB','client':'WEB'})
        env=json_source(url,OUT/f'{symbol}_em_annual.json')
        print('US financial fallback',symbol,len((env['data'].get('result') or {}).get('data') or []),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true');parser.add_argument('--as-of',default=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat())
    args=parser.parse_args();asof=dt.date.fromisoformat(args.as_of)
    snapshot=OUT/'1phTpK_before.json'
    if not snapshot.exists() or '--refresh' in sys.argv:
        from write_feishu import connect,helper
        token,ss=connect()
        response=helper.request('GET',f'sheets/v2/spreadsheets/{ss}/values/1phTpK!A1:CL464?valueRenderOption=Formula',token)
        snapshot.write_text(json.dumps(response,ensure_ascii=False))
    rows=json.loads(snapshot.read_text())['data']['valueRange']['values']
    rows=[[flat(v) for v in r] for r in rows];symbols=[r[3] for r in rows[1:]]
    batches([(s,'forecast') for s in symbols])
    jobs=[]
    for row in rows[1:]:
        s=row[3];env=json.loads((OUT/f'{s}_forecast.json').read_text());month,_=fiscal_month(env,row)
        # Check FY2026 statements when the fiscal-end month has arrived.
        if month is None or dt.date(2026,month,1)<=asof:
            jobs.extend([(s,'annual'),(s,'financial_page')])
    batches(jobs)
    old=json.loads((ROOT/'selection/selected_quotes.json').read_text());shares={}
    for start in range(0,len(symbols),80):
        import subprocess
        url='https://push2.eastmoney.com/api/qt/ulist.np/get?'+urlencode({'secids':','.join(f'{old[s]["f13"]}.{old[s]["f12"]}' for s in symbols[start:start+80]),'fltt':2,'invt':2,'fields':'f12,f13,f38,f124'})
        path=OUT/f'shares_batch_{start//80}.json'
        if path.exists() and '--refresh' not in sys.argv:env=json.loads(path.read_text())
        else:
            proc=subprocess.run(['curl','-sS','--max-time','20','-A','Mozilla/5.0','-e','https://quote.eastmoney.com/',url],capture_output=True,text=True,check=True)
            env={'source':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'data':json.loads(proc.stdout)};path.write_text(json.dumps(env,ensure_ascii=False))
        for q in (env['data'].get('data') or {}).get('diff',[]):
            s=q['f12'].replace('_','.')
            assert s in old and q['f13']==old[s]['f13']
            shares[s]={'symbol':s,'shares':q.get('f38'),'source':url,'retrieved_utc':env['retrieved_utc']}
    secondary_us_sources(rows,shares,asof)
    (OUT/'shares.json').write_text(json.dumps(shares,ensure_ascii=False,indent=2));print('Direct share coverage',len(shares),flush=True)
    # One public fallback per missing-symbol case; stop at any access restriction.
    for symbol in symbols:
        forecasts,state=annual_forecasts(json.loads((OUT/f'{symbol}_forecast.json').read_text()),symbol)
        if forecasts:continue
        slug=symbol.lower().replace('.','-');path=OUT/f'{slug}_secondary.json'
        if path.exists():continue
        url=f'https://stockanalysis.com/stocks/{slug}/forecast/'
        proc=subprocess.run(['curl','-L','-sS','--max-time','20','-A','Mozilla/5.0','-o',str(OUT/f'{slug}_secondary.html'),'-w','%{http_code}',url],capture_output=True,text=True)
        result={'symbol':symbol,'url':url,'http':proc.stdout.strip(),'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
        path.write_text(json.dumps(result,ensure_ascii=False))
        if result['http'] in ('403','429'):break
if __name__=='__main__':main()
