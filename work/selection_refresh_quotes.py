import concurrent.futures,json
from urllib.parse import urlencode
from selection_sources import OUT,get

if __name__=='__main__':
    source=json.loads((OUT/'candidates.json').read_text());groups={}
    for c in source['candidates']:groups.setdefault(c['group'],[]).append(c)
    selected=[c for group in groups.values() for rank,c in enumerate(sorted(group,key=lambda c:-c['cap']),1) if c['cap']>=3e10 or rank<=2]
    secids=[f'{c["quote"]["f13"]}.{c["quote"]["f12"]}' if c['quote'] else '106.SKYD' for c in selected]
    assert all(c['quote'] or c['symbol']=='SKYD' for c in selected)
    jobs=[(i//80,secids[i:i+80]) for i in range(0,len(secids),80)]
    def collect(job):
        i,codes=job
        return get(f'quotes_{i}','https://push2.eastmoney.com/api/qt/ulist.np/get?'+urlencode({'secids':','.join(codes),'fltt':2,'invt':2,'fields':'f2,f3,f12,f13,f14,f20,f115,f124'}),'https://quote.eastmoney.com/')
    results=[]
    for start in range(0,len(jobs),2):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results+=list(pool.map(collect,jobs[start:start+2]))
        if any(r['http']=='429' for r in results):break
    lookup={}
    for r in results:
        for q in (r.get('data',{}).get('data') or {}).get('diff',[]):lookup[q['f12'].replace('_','.') ]={**q,'retrieved_utc':r['retrieved_utc'],'url':r['url']}
    (OUT/'selected_quotes.json').write_text(json.dumps(lookup,ensure_ascii=False,indent=2))
    print('selected',len(selected),'quotes',len(lookup),'missing',sorted({c['symbol'] for c in selected}-lookup.keys()),flush=True)
