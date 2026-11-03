"""Patch existing sheets after a live read, verify every changed cell and unchanged row."""
import copy,json,math,re
from collections import Counter
from write_feishu import connect,helper,ROOT
from forecast_fields import OUT,apply_rows,load_records,reference_pe,number,RULE
from valuation_policy import col

def flat(v):return ''.join(x.get('text','') for x in v) if isinstance(v,list) else '' if v is None else v
def norm(rows,width):return [([flat(v) for v in row]+['']*width)[:width] for row in rows]
def formula(v):return {'type':'formula','text':v} if isinstance(v,str) and v.startswith('=') else v
def equal(a,b):return math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-8) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else a==b

def main():
    records=load_records();assert len(records)==463
    token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
    def read(sid,address,width,render='Formula'):
        return norm(helper.request('GET',f'{base}/values/{sid}!{address}?valueRenderOption={render}',token)['data']['valueRange']['values'],width)
    plans=[];stats={};patches=[];styles=[]
    for name,sid,width,end in [('main','477joI',120,25),('selection','1phTpK',72,464)]:
        before=read(sid,f'A1:{col(width-1)}{end}',width)
        saved=norm(json.loads((OUT/f'{name}_before.json').read_text())['data']['valueRange']['values'],width)
        assert before==saved,f'{name} online edited since initial read; stop and reconcile'
        after,red=apply_rows(before,name,records);count=0;pejs=[7,8,9] if name=='main' else [9,10,11]
        for i,(a,b) in enumerate(zip(before,after),1):
            diffs=[j for j,(x,y) in enumerate(zip(a,b)) if x!=y];count+=len(diffs)
            if not diffs:continue
            start=last=diffs[0]
            for j in diffs[1:]+[None]:
                if j is None or j!=last+1:
                    patches.append({'range':f'{sid}!{col(start)}{i}:{col(last)}{i}','values':[[formula(v) for v in b[start:last+1]]]})
                    if j is None:break
                    start=j
                last=j
        reds=[f'{sid}!{col(j)}{i+1}:{col(j)}{i+1}' for i,j in red]
        for start in range(0,len(reds),100):styles.append({'ranges':reds[start:start+100],'style':{'foreColor':'#C00000'}})
        actuals=[]
        for i,row in enumerate(after[1:],2):
            for year,j in ({2024:52,2025:11,2026:12,2027:13,2028:14} if name=='main' else {2024:52,2025:13,2026:14,2027:15,2028:16}).items():
                if str(year) in records[row[3]]['actuals']:actuals.append(f'{sid}!{col(j)}{i}:{col(j)}{i}')
        if actuals:styles.append({'ranges':actuals,'style':{'foreColor':'#202124'}})
        stats[name]={'changed_cells':count,'forward_pe_numeric':sum(number(r[j]) is not None for r in after[1:] for j in pejs),'new_pe_numeric':sum(number(a[j]) is None and number(b[j]) is not None for a,b in zip(before[1:],after[1:]) for j in pejs),'actual_usd_cells':len(actuals),'stock_count':len(after)-1}
        plans.append((name,sid,width,end,before,after,red))
    metadata=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets'];title='预测字段修复_1103'
    found=next((s for s in metadata if s['title']==title),None)
    if not found:
        helper.request('POST',base+'/sheets_batch_update',token,{'requests':[{'addSheet':{'properties':{'title':title}}}]})
        metadata=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets'];found=next(s for s in metadata if s['title']==title)
    aid=found['sheet_id'];width=23
    for major,key,target in [('ROWS','row_count',500),('COLUMNS','column_count',width)]:
        if found['grid_properties'][key]<target:helper.request('POST',base+'/dimension_range',token,{'dimension':{'sheetId':aid,'majorDimension':major,'length':target-found['grid_properties'][key]}})
    audit=[['预测字段修复与来源核验｜2026-11-03'],['结论','旧版把可获取预测EPS与预测总利润混在一起拦截；现恢复价格/EPS参考PE；预测总净利润仍需独立来源。'],['口径',RULE],['实际利润','本次24家半导体逐股读取Nasdaq财务API与财务页面；只有页面明示In USD Thousands时填美元实际利润；不自行换汇。'],['时间','美股价格和预测抓取时间分别记录；asOf为空表示供应商未披露预测更新时间；获取成功不代表最新财报已被分析师纳入。'],['代码','公司','GICS一级','GICS二级','参考价格USD','价格时间UTC','FY2026 EPS','FY2027 EPS','FY2028 EPS','FY2026参考PE','FY2027参考PE','FY2028参考PE','预测财年及样本数','预测抓取UTC','预测源asOf','FY2025实际利润亿美元','FY2026实际利润亿美元','2027/2026预测EPS增长','2028/2027预测EPS增长','获取/估值状态','预测来源','美元利润来源/单位证据','限制与说明']]
    for row in plans[1][5][1:]:
        symbol=row[3];rec=records[symbol];fs=rec['forecasts'];actual=rec['actuals'];eps=[fs.get(str(y),{}).get('eps') for y in (2026,2027,2028)]
        pes=[reference_pe(rec['price'],fs[str(y)])[0] if str(y) in fs else None for y in (2026,2027,2028)]
        growth=[f'{(b/a-1)*100:.2f}%' if a is not None and a>0 and b is not None else '无同口径相邻预测期' for a,b in zip(eps,eps[1:])]
        actualvalues=[actual.get(str(y),{}).get('net_income_100m_usd','本次未取得/未复测') for y in (2025,2026)]
        audit.append([symbol,row[0],row[1],row[2],rec['price']['price'],rec['price']['quote_utc'],*[e if e is not None else '源未提供' for e in eps],*[round(x,6) if x is not None else '源无该年预测或EPS非正' for x in pes],'；'.join(f'{f["period"]}：{f["estimates"]}家' for f in fs.values()),rec.get('forecast_retrieved_utc') or '未取得','；'.join(str(f['provider_asof']) for f in fs.values()) or '未提供',*actualvalues,*growth,rec['forecast_status'],rec['forecast_url'],'；'.join(dict.fromkeys(x['source']+' ｜ '+x['unit_evidence'] for x in actual.values())) or '未取得本次单位证据','参考PE采用Nasdaq美股EPS的USD/每份解释；接口未明示币种与GAAP调整，红字待核验；EPS增长不是总净利润增长。'])
    audit=[r+['']*(width-len(r)) for r in audit];assert all(len(r)==width for r in audit)
    for offset in range(0,len(audit),70):
        part=audit[offset:offset+70];patches.append({'range':f'{aid}!A{offset+1}:W{offset+len(part)}','values':part})
    assert all('\n' not in str(v) and '\r' not in str(v) for p in patches for r in p['values'] for v in r)
    (OUT/'publish_plan.json').write_text(json.dumps({'patches':patches,'stats':stats,'audit_sheet':aid},ensure_ascii=False,indent=2))
    print('PLAN',json.dumps(stats,ensure_ascii=False),'ranges',len(patches),flush=True)
    for start in range(0,len(patches),45):
        helper.request('POST',base+'/values_batch_update',token,{'valueRanges':patches[start:start+45]})
        if start%450==0:print('published ranges',start+len(patches[start:start+45]),'/',len(patches),flush=True)
    for start in range(0,len(styles),12):helper.request('PUT',base+'/styles_batch_update',token,{'data':styles[start:start+12]})
    helper.request('PUT',base+'/styles_batch_update',token,{'data':[{'ranges':[f'{aid}!A1:W1',f'{aid}!A6:W6'],'style':{'backColor':'#17365D','foreColor':'#FFFFFF','font':{'bold':True}}},{'ranges':[f'{aid}!G7:L{len(audit)}',f'{aid}!R7:S{len(audit)}'],'style':{'foreColor':'#C00000'}}]})
    for a,b,w in [(1,1,90),(2,2,260),(3,4,180),(5,5,130),(6,6,210),(7,12,145),(13,15,280),(16,19,180),(20,20,230),(21,23,420)]:helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':aid,'majorDimension':'COLUMNS','startIndex':a,'endIndex':b},'dimensionProperties':{'fixedSize':w}})
    for sid,stop in [('477joI',2888),('1phTpK',600),(aid,500)]:helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':1,'endIndex':stop},'dimensionProperties':{'fixedSize':29}})
    helper.request('POST',base+'/sheets_batch_update',token,{'requests':[{'updateSheet':{'properties':{'sheetId':aid,'frozenRowCount':6,'frozenColCount':2}}}]})
    for name,sid,width,end,before,after,red in plans:
        got=read(sid,f'A1:{col(width-1)}{end}',width)
        for i,(a,b) in enumerate(zip(got,after),1):
            for j,(x,y) in enumerate(zip(a,b)):
                assert equal(x,y),(name,i,col(j),x,y)
        assert [r[3] for r in got[1:]]==[r[3] for r in before[1:]]
        # Persist overlays for subsequent builds. Do not replace formula strings by calculated values.
        payloadpath=ROOT/('composite/payload.json' if name=='main' else 'selection/sheet_payload.json')
        payload=json.loads(payloadpath.read_text());payload['rows'],rr=apply_rows(payload['rows'],name,records)
        newred={f'{col(j)}{i+1}' for i,j in rr};payload['red_cells']=sorted(set(payload.get('red_cells',[]))|newred)
        if 'black_cells' in payload:payload['black_cells']=[c for c in payload['black_cells'] if c not in newred]
        payloadpath.write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    got=read(aid,f'A1:W{len(audit)}',23)
    assert len(got)==len(audit)
    assert all(equal(x,y) for a,b in zip(got,audit) for x,y in zip(a,b))
    stats.update(audit_sheet=aid,verified=True,audit_url=f'https://my.feishu.cn/wiki/OCS4wHZRvik8Wckwc1ecHjnhnbI?sheet={aid}',stocks_with_forecasts=sum(bool(r['forecasts']) for r in records.values()),stocks_with_fresh_usd_actuals=sum(bool(r['actuals']) for r in records.values()))
    (OUT/'published.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2));print(json.dumps(stats,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
