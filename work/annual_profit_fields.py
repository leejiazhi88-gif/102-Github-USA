"""Reported annual income or a visibly conditional fixed-share EPS scenario."""
import argparse,calendar,datetime as dt,json
from collections import Counter
from pathlib import Path
from forecast_fields import annual_forecasts,number
from quarter_fields import fiscal_month,flat
ROOT=Path(__file__).parent;OUT=ROOT/'opq_repair';YEARS=(2026,2027,2028)
MARKER='【年度利润补齐】'

def fiscal_end(year,month):
    return dt.date(year,month,calendar.monthrange(year,month)[1]) if month else None

def reported_annual(env,page,symbol,month,asof):
    if not env.get('ok') or not page.get('ok') or not page.get('usd_thousands_label') or not month:return {}
    data=(env.get('data') or {}).get('data') or {}
    if data.get('symbol','').upper().replace('/','.')!=symbol.upper():return {}
    table=data.get('incomeStatementTable') or {};headers=table.get('headers') or {}
    if 'quarter' in str(headers.get('value1','')).lower() or 'frequency=1' not in env.get('url',''):return {}
    row=next((r for r in table.get('rows') or [] if r.get('value1')=='Net Income Applicable to Common Shareholders'),{})
    result={};duplicates=set()
    for key,date_text in headers.items():
        try:end=dt.datetime.strptime(date_text,'%m/%d/%Y').date()
        except (TypeError,ValueError):continue
        adjusted=end
        if end.month!=month and end.day<=7:adjusted=end-dt.timedelta(days=end.day)
        amount=number(row.get(key))
        if adjusted.month!=month or end>asof or amount is None:continue
        year=adjusted.year
        if year in result:duplicates.add(year);continue
        result[year]={'status':'actual','value':round(amount/100000,6),'period':end.isoformat(),'source':env['url'],'retrieved_utc':env['retrieved_utc'],'unit_source':page['url'],'unit_retrieved_utc':page['retrieved_utc']}
    for year in duplicates:result.pop(year,None)
    return result

def eastmoney_annual(env,symbol,month,asof):
    """US issuer annual parent income; reject quarterly/YTD and foreign currencies."""
    result={};duplicates=set()
    for row in ((env.get('data') or {}).get('result') or {}).get('data') or []:
        if row.get('SECURITY_CODE','').replace('_','.')!=symbol or str(row.get('SECUCODE','')).rsplit('.',1)[-1] not in ('N','O','A'):continue
        if str(row.get('DATE_TYPE_CODE'))!='001' or row.get('CURRENCY_ABBR')!='USD':continue
        try:start,end,notice=[dt.date.fromisoformat(str(row[k])[:10]) for k in ('START_DATE','REPORT_DATE','NOTICE_DATE')]
        except (KeyError,ValueError):continue
        amount=number(row.get('PARENT_HOLDER_NETPROFIT'));adjusted=end
        if end.month!=month and end.day<=7:adjusted=end-dt.timedelta(days=end.day)
        if end>asof or notice>asof or not 350<=(end-start).days+1<=380 or adjusted.month!=month or amount is None:continue
        year=adjusted.year
        if year in result:duplicates.add(year);continue
        result[year]={'status':'actual','value':round(amount/1e8,6),'period':end.isoformat(),'source':env['url'],'retrieved_utc':env['retrieved_utc'],'reason':f'东财美股年度归母净利润PARENT_HOLDER_NETPROFIT={amount}美元/1亿；年报区间{start}至{end}，公告{notice}，币种USD；非单季或累计九个月'}
    for y in duplicates:result.pop(y,None)
    return result

def estimate(forecast,shares,symbol):
    if not shares:return None,'未取得接口直接股数'
    if forecast.get('symbol')!=symbol or shares.get('symbol')!=symbol:return None,'证券代码不对应'
    if forecast.get('currency') not in (None,'','USD'):return None,'EPS币种明确非美元，不相乘'
    if shares.get('per_share_basis_mismatch'):return None,'已知EPS与股数每份单位不匹配'
    eps=number(forecast.get('eps'));count=number(shares.get('shares'))
    if eps is None:return None,'源年度EPS缺失'
    if count is None or count<=0:return None,'未取得有效接口直接股数'
    if not forecast.get('source') or not shares.get('source'):return None,'缺少来源'
    return round(eps*count/1e8,6),'固定当前股数估算；EPS按同美股每份USD解释，币种/ADR每份/GAAP调整口径未独立核验'

def apply_selection(rows,records=None):
    if records is None:
        path=OUT/'records.json'
        if not path.exists():return rows,[],[]
        records=json.loads(path.read_text())['records']
    rows=[r[:] for r in rows];red=[];black=[]
    for year,j in zip(YEARS,(14,15,16)):rows[0][j]=f'FY{year}净利润（实际/固定股数估算；亿美元）'
    for i,row in enumerate(rows[1:],2):
        rec=records.get(row[3])
        if not rec:continue
        for year,j in zip(YEARS,(14,15,16)):
            r=rec['years'][str(year)];row[j]=r['value']
            (black if r['status']=='actual' else red).append((i,j))
        row[51]=str(row[51]).split(MARKER)[0].rstrip('；')+'；'+MARKER+rec['note']
    return rows,red,black

def build(asof):
    def load(path):return json.loads(path.read_text()) if path.exists() else {}
    rows=load(OUT/'1phTpK_before.json')['data']['valueRange']['values'];rows=[[flat(v) for v in r] for r in rows]
    shares=load(OUT/'shares.json');old=load(ROOT/'forecast_repair/records.json');records={};stats=Counter();reasons=Counter()
    for row in rows[1:]:
        symbol=row[3];env=load(OUT/f'{symbol}_forecast.json');forecasts,state=annual_forecasts(env,symbol);month,basis=fiscal_month(env,row)
        actual=reported_annual(load(OUT/f'{symbol}_annual.json'),load(OUT/f'{symbol}_financial_page.json'),symbol,month,asof)
        for year,record in eastmoney_annual(load(OUT/f'{symbol}_em_annual.json'),symbol,month,asof).items():actual.setdefault(year,record)
        years={};notes=[];share=shares.get(symbol,{})
        for year in YEARS:
            if year in actual:r=actual[year]
            elif str(year) in old.get(symbol,{}).get('actuals',{}) and fiscal_end(year,month) and fiscal_end(year,month)<=asof:
                a=old[symbol]['actuals'][str(year)]
                r={'status':'archived_actual','value':round(a['net_income_100m_usd'],6),'period':a['period'],'source':a['source'],'retrieved_utc':a['retrieved_utc'],'reason':'此前有来源的实际档案；本次未重新取得'}
            elif year in forecasts:
                f=forecasts[year];value,reason=estimate(f,share,symbol)
                r={'status':'estimate' if value is not None else 'missing','value':value if value is not None else '未补齐：'+reason,'period':f['period'],'reason':reason,'eps':f['eps'],'estimates':f['estimates'],'source':f['source'],'retrieved_utc':f['retrieved_utc']}
            else:
                reason='源未覆盖该财年EPS/实际年报' if state=='available' else '年度预测源状态：'+state
                r={'status':'missing','value':'未补齐：'+reason,'reason':reason,'source':env.get('url',''),'retrieved_utc':env.get('retrieved_utc','')}
            years[str(year)]=r;stats[r['status']]+=1
            if r['status']=='missing':reasons[r['reason']]+=1
            notes.append(f'FY{year}：'+{'actual':'实际','archived_actual':'实际档案待复核','estimate':'固定股数估算','missing':'缺项'}[r['status']]+f'；期末={r.get("period","未提供")}；值={r["value"]}；EPS={r.get("eps","不适用")}；样本={r.get("estimates","不适用")}；{r.get("reason","")}；来源={r.get("source","")}；抓取UTC={r.get("retrieved_utc","")}'+(f'；美元千元单位证据={r["unit_source"]}；单位页面抓取UTC={r["unit_retrieved_utc"]}' if 'unit_source' in r else ''))
        secondary=load(OUT/f"{symbol.lower().replace('.', '-')}_secondary.json")
        note=f'本次核验日{asof}；财年末月份={month}（{basis}）；'+'；'.join(notes)+f'；直接股数f38={share.get("shares","缺失")}；股数抓取UTC={share.get("retrieved_utc","缺失")}；股数来源={share.get("source","缺失")}；估算=年度EPS×接口直接当前股数/1亿，未用市值反推。当前股数不变，不等于未来稀释股数或直接利润共识；预测红字。源无预测asOf，抓取成功不保证已反映最新财报。OPQ本次独立更新，PE、增长率、其他EPS列和季度仍保留其原快照。'
        em=load(OUT/f'{symbol}_em_annual.json')
        if em:note+=f'；东财美股财务复核来源={em["url"]}；抓取UTC={em["retrieved_utc"]}；返回财报记录数={len(((em.get("data") or {}).get("result") or {}).get("data") or [])}'
        if share.get('resolution_note'):note+='；美股市场代码校正：'+share['resolution_note']
        if secondary:note+=f'；备用公开页={secondary["url"]}；HTTP {secondary["http"]}；抓取UTC={secondary["retrieved_utc"]}；访问限制未绕过，未作为数字来源'
        records[symbol]={'years':years,'note':note.replace('\r','').replace('\n','；'),'forecast_status':state,'fiscal_month':month}
    out={'records':records,'stats':dict(stats),'missing_reasons':dict(reasons),'asof':str(asof)}
    (OUT/'records.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='records'},ensure_ascii=False));return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--as-of',required=True);args=p.parse_args();build(dt.date.fromisoformat(args.as_of))
