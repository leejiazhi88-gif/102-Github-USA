import concurrent.futures,datetime as dt,json,subprocess
from urllib.parse import urlencode
from collect_forecast_repair import ROOT,OUT
def fetch(job):
    i,codes=job;url='https://push2.eastmoney.com/api/qt/ulist.np/get?'+urlencode({'secids':','.join(codes),'fltt':2,'invt':2,'fields':'f2,f12,f13,f14,f115,f124'})
    path=OUT/f'price_batch_{i}.raw'
    p=subprocess.run(['curl','-sS','--max-time','20','-A','Mozilla/5.0','-e','https://quote.eastmoney.com/','-o',str(path),'-w','%{http_code}',url],capture_output=True,text=True)
    result={'url':url,'http':p.stdout.strip(),'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'error':p.stderr.strip()}
    if result['http']=='200':result['data']=json.loads(path.read_text())
    (OUT/f'price_batch_{i}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
def main():
    old=json.loads((ROOT/'selection/selected_quotes.json').read_text());codes=[f'{q["f13"]}.{q["f12"]}' for q in old.values()]
    prices={}
    for start in range(0,len(codes),80):
        r=fetch((start//80,codes[start:start+80]))
        if r['http']=='429':break
        for q in (r.get('data',{}).get('data') or {}).get('diff',[]):
            s=q['f12'].replace('_','.')
            if s not in old or q['f13']!=old[s]['f13']:raise ValueError('Unexpected security')
            prices[s]={'symbol':s,'currency':'USD','price':q['f2'],'quote_epoch':q['f124'],'pe_ttm':q.get('f115'),'source':r['url'],'retrieved_utc':r['retrieved_utc']}
    (OUT/'prices.json').write_text(json.dumps(prices,ensure_ascii=False,indent=2));print('Fresh price coverage',len(prices))
if __name__=='__main__':main()
