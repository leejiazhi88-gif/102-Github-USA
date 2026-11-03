"""Read Nasdaq US-symbol forecasts; distinguish HTTP failures from missing fields."""
import concurrent.futures,datetime as dt,json,re,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).parent;OUT=ROOT/'forecast_repair';OUT.mkdir(exist_ok=True)
def fetch(symbol,kind):
    path=OUT/f'{symbol}_{kind}.json'
    if path.exists() and '--refresh' not in sys.argv:
        cached=json.loads(path.read_text())
        if 'ok' in cached:return cached
    api={'forecast':f'https://api.nasdaq.com/api/analyst/{symbol}/earnings-forecast','annual':f'https://api.nasdaq.com/api/company/{symbol}/financials?frequency=1','financial_page':f'https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/financials'}
    url=api[kind];raw=OUT/f'{symbol}_{kind}.raw';start=time.monotonic()
    p=subprocess.run(['curl','-sS','--max-time','20','--connect-timeout','8','-A','Mozilla/5.0','-o',str(raw),'-w','%{http_code}',url],capture_output=True,text=True)
    result={'symbol':symbol,'kind':kind,'url':url,'http':p.stdout.strip(),'error':p.stderr.strip(),'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'seconds':round(time.monotonic()-start,2)}
    if result['http']=='200' and p.returncode==0:
        try:
            if kind=='financial_page':result['usd_thousands_label']=bool(re.search(r'In\s+USD\s+Thousands',raw.read_text()))
            else:
                data=json.loads(raw.read_text());result['data']=data
                if (data.get('data') or {}).get('symbol','').upper().replace('/','.')!=symbol.upper():result['error']='missing or mismatched response symbol'
        except (ValueError,TypeError):result['error']='invalid response'
    result['ok']=result['http']=='200' and not result['error']
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
def main():
    main_symbols=json.loads((ROOT/'test_symbols.json').read_text())
    rows=json.loads((OUT/'selection_before.json').read_text())['data']['valueRange']['values']
    symbols=list(dict.fromkeys(main_symbols+[r[3] for r in rows[1:]]))
    jobs=[(s,'forecast') for s in symbols]+[(s,k) for s in main_symbols for k in ('annual','financial_page')]
    total=0;ok=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        # Only submit small batches so rate limits halt all remaining requests.
        for offset in range(0,len(jobs),12):
            batch=list(pool.map(lambda a:fetch(*a),jobs[offset:offset+12]));total+=len(batch);ok+=sum(x['ok'] for x in batch)
            print(json.dumps({'completed':total,'total':len(jobs),'successful':ok,'last':jobs[min(offset+11,len(jobs)-1)]}),flush=True)
            if any(x['http'] in ('403','429') for x in batch):print('Stopped: access restriction or rate limit',flush=True);break
            if len(batch)>=6 and all(not x['ok'] for x in batch):print('Stopped: repeated provider failures',flush=True);break
if __name__=='__main__':main()
