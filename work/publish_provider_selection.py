"""Patch selected PE and append provider comparison to the existing online sheet."""
import copy
import datetime as dt
import json
from statistics import median
from write_feishu import connect,helper,ROOT
from valuation_policy import col
from ttm_source import apply_ttm,read_selected,quote_time,SCOPE,OUT

def flat(v):
    return ''.join(s.get('text','') for s in v) if isinstance(v,list) else '' if v is None else v

def main():
    runs=json.loads((OUT/'runs.json').read_text());selected=read_selected()
    main_id='477joI';audit_id='Y64Xm'
    old=json.loads((ROOT/'composite/payload.json').read_text());new=apply_ttm(copy.deepcopy(old))
    latest={p:{} for p in ('eastmoney','tencent','futu')}
    for run in runs:
        for r in run['records']:latest[run['provider']][r['symbol']]=r
    token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
    def read(sid,address):
        return helper.request('GET',f'{base}/values/{sid}!{address}?valueRenderOption=Formula',token)['data']['valueRange'].get('values',[])
    before=read(main_id,'A1:DP25')
    assert [flat(row[3]) for row in before[1:]]==[r['symbol'] for r in selected['records']]
    (OUT/'main_before.json').write_text(json.dumps(before,ensure_ascii=False))
    changes={}
    for ri,row in enumerate(new['rows'],1):
        for j in ([6] if ri==1 else [6,54,118]):changes[f'{col(j)}{ri}']=row[j]
    changes['A29']=SCOPE
    changes['C2884']='PE TTM主源为东方财富美股批量f115；G列为独立快照；普通PE仅留对照'
    changes['C2888']='24只美股的TTM主源已选定东方财富；保留时点与冲突，失败用明确标注的旧缓存'
    patches=[{'range':f'{main_id}!{a}:{a}','values':[[v]]} for a,v in changes.items()]

    rows=[['大公司数据源选择与24只美股覆盖实测'],
          ['结论','主源：东方财富美股批量PE TTM f115；富途公开页用于交叉检查，腾讯用于行情核对；长桥官方API为可选接入，不阻塞当前取数。'],
          ['能力边界','本次两轮批量与网页复测只能证明当前可用，不等于长期SLA。未建立定时任务；已保存可重复运行的取数程序、原始响应和失败缓存规则。'],
          ['价格时段','本次已进入10/29美股盘中；本区按各源时间逐项记录；上方10/28收盘基准继续保留。新盘中PE不直接计算相对旧截图差异。'],
          ['来源','入口类型','请求成功/总数','覆盖股票数','有效TTM数','响应耗时中位数秒','本次费用/门槛','TTM字段','稳定性判断','用途','未解决问题','数据时效','入口','官方API状态']]
    for provider,label,kind,field,role,url in [
        ('eastmoney','东方财富','公开网页使用的批量JSON接口','f115','选定主源','https://quote.eastmoney.com/'),
        ('tencent','腾讯','公开美股批量报价接口','fields[39]普通PE，未明示TTM','行情核对；不填TTM','https://qt.gtimg.cn/'),
        ('futu','富途','公开美股网页内嵌结构化数据','peTtm / epsTtm','交叉检查，不静默替代主源','https://www.futunn.com/')]:
        rr=[r for r in runs if r['provider']==provider];records=list(latest[provider].values())
        rows.append([label,kind,f'{sum(r["ok"] for r in rr)}/{len(rr)}',len(records),sum(r.get('pe_ttm') is not None for r in records),round(median(r['seconds'] for r in rr),3),'本次公开读取无需付费或登录；不代表商业授权',field,'本次全部成功；长期稳定性未验证',role,'各源盈利分母存在差异；腾讯还缺少TTM字段语义' if provider=='tencent' else '明确TTM仍不保证与长桥App相同','本次有10/29盘中快照；逐股见下表',url,'网页入口无已核验SLA；不是有合同保障的OpenAPI' if provider!='futu' else '本次为公开网页；官方OpenD未连接，不能把网页成功率当OpenD实测'])
    rows.append(['长桥','官方OpenAPI','未发出鉴权行情请求','未实测','未实测','','需要账号配置；行情权益与费用未核验','pe_ttm_ratio / eps_ttm','官方SDK签名已查；可用率未知','可选接入；不是前置条件','不能以用户截图证明API可用或App/API一致','未取得API快照','https://github.com/longbridge/openapi','缺少本地账号配置；不能据此宣称不稳定'])
    rows += [['自动处理规则','仅使用美股代码；不跨市场；保留源字段、报价时间和抓取时间；失败保留最后成功值及原时间，不标为实时；0/缺失不冒充有效PE，负PE单独提示。'],
             ['红字规则','已知长桥截图冲突、负PE，或各自价格/PE推得的盈利分母偏差超过1%时标红。1%只是质量检查阈值，不是准确性保证。推得分母只用于诊断，不冒充供应商EPS。'],
             ['刷新规则','选定东方财富为固定主源；富途和腾讯仅核对，失败不静默换PE供应商，避免口径跳变。缓存有原始时间；无缓存就标未取得。'],
             ['美股代码','主源','主源PE TTM','主源价格USD','主源报价时间BJT','主源抓取UTC','富途PE TTM','富途EPS TTM','富途价格USD','富途报价时间BJT','腾讯普通PE（非TTM）','质量检查/红字原因','主源原始入口','富途入口']]
    detail_start=28+len(rows)
    red_rows=[]
    for d in selected['records']:
        s=d['symbol'];f=latest['futu'].get(s,{});t=latest['tencent'].get(s,{})
        rows.append([s,'东方财富 f115',d.get('pe_ttm','未取得'),d.get('price',''),quote_time(d),d.get('retrieved_utc',''),f.get('pe_ttm','未取得'),f.get('eps_ttm','未取得'),f.get('price',''),quote_time(f),t.get('generic_pe','未取得'),'；'.join(d['issues']) or '本次检查未触发红字；不是盈利分母独立审计',d.get('url',''),f.get('url','')])
        if d['issues']:red_rows.append(28+len(rows)-1)
    rows=[r+['']*(14-len(r)) for r in rows]
    end=27+len(rows)
    patches += [
        {'range':f'{audit_id}!A28:N{end}','values':rows},
        {'range':f'{audit_id}!A2:A2','values':[['基准截图来自长桥App；当前按用户要求选择可稳定调用的供应商，主源为东方财富美股TTM。长桥官方API为可选项；具体实测与选择见第28行起。']]},
        *[{'range':f'{audit_id}!N{r}:N{r}','values':[['保留长桥App收盘验收基准；可选接入官方API，不要求反复截图']]} for r in (4,8,12)]
    ]
    assert all('\n' not in str(v) and '\r' not in str(v) for p in patches for r in p['values'] for v in r)
    for off in range(0,len(patches),45):helper.request('POST',base+'/values_batch_update',token,{'valueRanges':patches[off:off+45]})
    red_main=[f'{main_id}!G{i}:G{i}' for i,d in enumerate(selected['records'],2) if d['issues']]
    styles=[{'ranges':[f'{main_id}!G2:G25',f'{audit_id}!A28:N{end}'],'style':{'foreColor':'#202124'}},
            {'ranges':[f'{audit_id}!A28:N28',f'{audit_id}!A32:N32',f'{audit_id}!A{detail_start-1}:N{detail_start-1}'],'style':{'foreColor':'#FFFFFF','backColor':'#17365D','font':{'bold':True}}}]
    if red_main:styles.append({'ranges':red_main,'style':{'foreColor':'#C00000'}})
    if red_rows:styles.append({'ranges':[f'{audit_id}!C{i}:C{i}' for i in red_rows]+[f'{audit_id}!L{i}:L{i}' for i in red_rows],'style':{'foreColor':'#C00000'}})
    helper.request('PUT',base+'/styles_batch_update',token,{'data':styles})
    for sid,stop in ((main_id,2888),(audit_id,200)):
        helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':1,'endIndex':stop},'dimensionProperties':{'fixedSize':29}})
    after=read(main_id,'A1:DP25')
    for i,(a,b) in enumerate(zip(before,after),1):
        for j in range(120):
            addr=f'{col(j)}{i}';expected=changes.get(addr,flat(a[j]) if j<len(a) else '')
            actual=flat(b[j]) if j<len(b) else ''
            assert actual==expected,(addr,actual,expected)
    # Verify every patch, not only that the write returned success.
    for p in patches:
        sid,address=p['range'].split('!');got=read(sid,address)
        for i,row in enumerate(p['values']):
            actual=[flat(x) for x in got[i]] if i<len(got) else []
            assert (actual+['']*len(row))[:len(row)]==row,p['range']
    (ROOT/'composite/payload.json').write_text(json.dumps(new,ensure_ascii=False,indent=2))
    state={'main_sheet':main_id,'comparison_sheet':audit_id,'main_stocks':24,'red_flags':len(red_main),'comparison_range':f'A28:N{end}','main_other_cells_unchanged':True,'all_patches_readback_verified':True,'row_height_px':29,'newlines_in_writes':0,'selected_provider':'东方财富美股批量f115','quote_time_example':quote_time(selected['records'][0])}
    (OUT/'published.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
    print(json.dumps(state,ensure_ascii=False))

if __name__=='__main__':main()
