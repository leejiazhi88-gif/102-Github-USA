import json,subprocess,datetime,time
from pathlib import Path
from urllib.parse import urlencode

OUT=Path(__file__).parent/'selection'
def get(name,url,referer='https://www.nasdaq.com/'):
    start=time.monotonic();path=OUT/(name+'.raw')
    p=subprocess.run(['curl','-sS','--max-time','45','--connect-timeout','12','-A','Mozilla/5.0','-e',referer,'-o',str(path),'-w','%{http_code}',url],capture_output=True)
    record={'url':url,'http':p.stdout.decode().strip(),'error':p.stderr.decode().strip(),'seconds':round(time.monotonic()-start,3),'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if p.returncode==0 and record['http']=='200':
        try:record['data']=json.loads(path.read_bytes())
        except ValueError:record['error']='Response is not JSON'
    (OUT/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(name,record['http'],record['error'],flush=True)
    return record

if __name__=='__main__':
    import concurrent.futures
    jobs=[('nasdaq_screen','https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0&download=true','https://www.nasdaq.com/'),('em_screen1','https://push2.eastmoney.com/api/qt/clist/get?'+urlencode({'pn':1,'pz':100,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f20','fs':'m:105,m:106,m:107','fields':'f2,f3,f12,f13,f14,f20,f115,f124'}),'https://quote.eastmoney.com/')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for r in pool.map(lambda a:get(*a),jobs):
            d=r.get('data',{}).get('data') or {};print('shape',list(d)[:12],len(d.get('rows',d.get('diff',[]))),flush=True)
