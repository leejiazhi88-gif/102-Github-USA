import collections,csv,json,re
from pathlib import Path
from selection_sources import OUT

CONFIG=Path(__file__).resolve().parent.parent/'config'
mapping=json.loads((CONFIG/'gics_mapping.json').read_text())
GROUPS=mapping['groups'];SP=mapping['sp'];MANUAL=mapping['manual']
def getgroup(x):
    sub=x['GICS Sub-Industry']
    if sub in mapping['subgroups']:return mapping['subgroups'][sub]
    return {'Energy':'1010','Materials':'1510','Industrials':'2010','Consumer Discretionary':None,'Consumer Staples':'3020','Health Care':'3520','Financials':'4020','Information Technology':'4510','Communication Services':'5020','Utilities':'5510','Real Estate':'6010'}[x['GICS Sector']]
MANUAL.update({'CLS':'4520','CRDO':'4530','FWONA':'5020','GMAB':'3520','KOF':'3020','PUK':'4030','TECK':'1510'})

def clean(v):
    if isinstance(v,list):v=''.join(x.get('text','') for x in v)
    return re.sub(r'[\r\n]+','；',v) if isinstance(v,str) else '' if v is None else v

def source_rows():
    raw=json.loads((OUT/'reference_values.json').read_text())['data']['valueRange']['values']
    return {r[3]:[clean(v) for v in r[:56]] for r in raw[1:] if len(r)>38 and isinstance(r[3],str) and r[3]}

def eligible(symbol,name):
    if symbol in {'BRK.A','GOOG','BBDO','GOOGM','GOOGN','PBR.A','HEI.A','FOX','FWONK','LBRDK'}:return False
    if re.search(r'warrant|notes due|debenture|tangible equity unit|corporate units|ZONES|mandatory convertible|perpetual.*preferred|series.*preferred',name,re.I):return False
    if re.search(r'preferred',name,re.I) and symbol!='ITUB':return False
    return True

def main():
    reference=source_rows();nasdaq=json.loads((OUT/'nasdaq_screen.json').read_text())['data']['data']['rows']
    em={}
    for path in sorted(OUT.glob('em_screen[0-9]*.json'),key=lambda p:int(re.search(r'(\d+)\.json$',p.name)[1])):
        run=json.loads(path.read_text())
        for d in (run.get('data',{}).get('data') or {}).get('diff',[]):
            if d.get('f13') not in (105,106,107):raise ValueError('Non-US listing')
            em[d['f12'].replace('_','.') ]={**d,'retrieved_utc':run['retrieved_utc'],'url':run['url']}
    candidates=[];unmapped=[];missing=[];excluded=[]
    for n in nasdaq:
        symbol=n['symbol'].replace('/','.');ncap=float(n.get('marketCap') or 0)
        if not eligible(symbol,n['name']):
            if ncap>=3e10:excluded.append((symbol,n['name'],ncap))
            continue
        gx=SP.get(symbol);ref=reference.get(symbol)
        g=str(ref[37]) if ref else getgroup(gx) if gx else MANUAL.get(symbol)
        q=em.get(symbol);cap=ncap
        if not q and (ncap>=3e10 or symbol in reference):missing.append((symbol,ncap,g,n['name']))
        if cap<=0:continue
        if not g:
            if cap>=3e10 or ncap>=3e10:unmapped.append((symbol,n['name'],cap,n['industry'],n['sector']))
            continue
        candidates.append({'symbol':symbol,'name':ref[0] if ref else n['name'],'description':ref[4] if ref else 'Nasdaq行业：'+n['industry'],'group':g,'sector':GROUPS[g][0],'group_name':GROUPS[g][1],'classification':ref[38] if ref else '公开GICS映射（参考档案）' if gx else '按主营业务映射GICS，待官方核验','cap':cap,'nasdaq_cap':ncap,'quote':q or {},'reference':ref,'name_en':n['name'],'nasdaq_price':n['lastsale'],'nasdaq_pct':n['pctchange']})
    result={'candidates':candidates,'unmapped':unmapped,'missing_quotes':missing,'excluded_large_securities':excluded,'nasdaq_universe_count':len(nasdaq),'em_unique_count':len(em),'group_definitions':GROUPS}
    (OUT/'candidates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('candidates','group_definitions')},ensure_ascii=False,indent=2))
    print('candidate_count',len(candidates),'groups',len(set(c['group'] for c in candidates)))

if __name__=='__main__':main()
