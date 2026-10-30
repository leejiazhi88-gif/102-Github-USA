import concurrent.futures,json
from selection_sources import OUT,get
from urllib.parse import urlencode

if __name__=='__main__':
    for start in (2,5,8):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            def fetch_page(page):
                return get(f'em_screen{page}','https://push2.eastmoney.com/api/qt/clist/get?'+urlencode({'pn':page,'pz':100,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f20','fs':'m:105,m:106,m:107','fields':'f2,f3,f12,f13,f14,f20,f115,f124'}),'https://quote.eastmoney.com/')
            runs=list(pool.map(fetch_page,range(start,start+3)))
        if any(r['http']=='429' for r in runs):break
        minimum=min((d['f20'] for r in runs for d in (r.get('data',{}).get('data') or {}).get('diff',[]) if isinstance(d.get('f20'),(int,float))),default=0)
        print('batch minimum USD marketcap',minimum,flush=True)
        if minimum<1.5e10:break
