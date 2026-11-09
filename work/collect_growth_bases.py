"""Fetch only missing historical annual bases, reusing dated US-source records."""
import argparse,concurrent.futures,datetime as dt,json,shutil
from urllib.parse import urlencode
from pathlib import Path
import collect_forecast_repair as provider
from quarter_fields import flat
from forecast_fields import number
ROOT=Path(__file__).parent;OUT=ROOT/'growth_repair';OUT.mkdir(exist_ok=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--as-of',required=True);parser.add_argument('--refresh',action='store_true');args=parser.parse_args();asof=dt.date.fromisoformat(args.as_of)
    snapshot=OUT/'before.json'
    if not snapshot.exists() or args.refresh:
        from write_feishu import connect,helper
        token,ss=connect();response=helper.request('GET',f'sheets/v2/spreadsheets/{ss}/values/1phTpK!A1:CL464?valueRenderOption=Formula',token)
        snapshot.write_text(json.dumps(response,ensure_ascii=False))
    rows=json.loads(snapshot.read_text())['data']['valueRange']['values']
    rows=[[flat(v) for v in r] for r in rows]
    symbols=[r[3] for r in rows[1:] if number(r[13]) is None or number(r[52]) is None]
    provider.OUT=OUT;jobs=[]
    for symbol in symbols:
        for kind in ('annual','financial_page'):
            current=ROOT/'opq_repair'/f'{symbol}_{kind}.json';target=OUT/f'{symbol}_{kind}.json'
            if current.exists() and not target.exists():shutil.copyfile(current,target)
            jobs.append((symbol,kind))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for start in range(0,len(jobs),12):
            batch=list(pool.map(lambda x:provider.fetch(*x),jobs[start:start+12]))
            print('Checked',min(start+12,len(jobs)),'/',len(jobs),flush=True)
            if any(r['http'] in ('403','429') for r in batch):raise RuntimeError('Provider access restriction; stopped')
    from growth_fields import build
    from collect_annual_profit import json_source
    records=build(asof)['records']
    for symbol,record in records.items():
        if not any(record['periods'][year]['amount'] is None for year in (2024,2025)):continue
        url='https://datacenter-web.eastmoney.com/api/data/v1/get?'+urlencode({'reportName':'RPT_USF10_FN_GMAININDICATOR','columns':'ALL','filter':f'(SECURITY_CODE="{symbol.replace(".","_")}")','pageSize':100,'pageNumber':1,'sortColumns':'REPORT_DATE','sortTypes':-1,'source':'WEB','client':'WEB'})
        json_source(url,OUT/f'{symbol}_em_annual.json')
    build(asof)
if __name__=='__main__':main()
