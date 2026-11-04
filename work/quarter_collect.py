"""Fetch quarterly actuals and explicit US-page units; forecasts keep original timestamps."""
import concurrent.futures,datetime as dt,json,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from write_feishu import connect,helper,ROOT
OUT=ROOT/'quarter_extension';OUT.mkdir(exist_ok=True)

def fetch(symbol,kind,force=False):
    path=OUT/f'{symbol}_{kind}.json'
    if path.exists() and not force:return json.loads(path.read_text())
    url=f'https://api.nasdaq.com/api/company/{symbol}/financials?frequency=2' if kind=='quarter' else f'https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/financials'
    raw=OUT/f'{symbol}_{kind}.raw';p=subprocess.run(['curl','-sS','--max-time','20','--connect-timeout','8','-A','Mozilla/5.0','-o',str(raw),'-w','%{http_code}',url],capture_output=True,text=True)
    r={'symbol':symbol,'kind':kind,'url':url,'http':p.stdout.strip(),'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'error':p.stderr.strip()}
    if p.returncode==0 and r['http']=='200':
        try:
            if kind=='page':r['usd_thousands_label']='In USD Thousands' in raw.read_text()
            else:r['data']=json.loads(raw.read_text())
        except ValueError:r['error']='Response parse error'
    path.write_text(json.dumps(r,ensure_ascii=False,indent=2));return r

def main():
    token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
    for name,sid,end in [('selection','1phTpK','BT464'),('main','477joI','DP25')]:
        path=OUT/f'{name}_before.json'
        if not path.exists():path.write_text(json.dumps(helper.request('GET',base+f'/values/{sid}!A1:{end}?valueRenderOption=Formula',token),ensure_ascii=False))
    rows=json.loads((OUT/'selection_before.json').read_text())['data']['valueRange']['values'];symbols=[r[3] for r in rows[1:]]
    old=json.loads((ROOT/'selection/selected_quotes.json').read_text());shares={}
    for start in range(0,len(symbols),80):
        url='https://push2.eastmoney.com/api/qt/ulist.np/get?'+urlencode({'secids':','.join(f'{old[s]["f13"]}.{old[s]["f12"]}' for s in symbols[start:start+80]),'fltt':2,'invt':2,'fields':'f12,f13,f38,f124'})
        path=OUT/f'shares_{start//80}.json'
        if path.exists():r=json.loads(path.read_text())
        else:
            p=subprocess.run(['curl','-sS','--max-time','20','-A','Mozilla/5.0','-e','https://quote.eastmoney.com/',url],capture_output=True,text=True)
            r={'url':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'data':json.loads(p.stdout)};path.write_text(json.dumps(r,ensure_ascii=False,indent=2))
        for q in (r['data'].get('data') or {}).get('diff',[]):
            s=q['f12'].replace('_','.')
            assert s in old and q['f13']==old[s]['f13']
            shares[s]={'symbol':s,'shares':q.get('f38'),'source':url,'field':'f38','retrieved_utc':r['retrieved_utc'],'basis':'current_vendor_us_total_shares_not_forecast_diluted'}
    (OUT/'shares.json').write_text(json.dumps(shares,ensure_ascii=False,indent=2));print('Direct share records',len(shares),flush=True)
    jobs=[(s,k) for s in symbols for k in ('quarter','page')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for start in range(0,len(jobs),16):
            batch=list(pool.map(lambda job:fetch(*job),jobs[start:start+16]))
            print('Completed',start+len(batch),'/',len(jobs),flush=True)
            if any(r['http'] in ('403','429') for r in batch):print('Stopped at access restriction',flush=True);break
if __name__=='__main__':main()
