"""Annual growth from explicit same-currency table amounts, with loss-base states."""
import datetime as dt,json,math,re
from collections import Counter
from pathlib import Path
from annual_profit_fields import reported_annual,eastmoney_annual
from forecast_fields import number
from quarter_fields import flat,fiscal_month
ROOT=Path(__file__).parent;OUT=ROOT/'growth_repair';MARKER='【年度同比补齐】'
HEADERS=[f'FY{y}净利润同比（实际/估算参考）' for y in range(2025,2029)]

def table_amount(value):
    n=number(value)
    if n is not None:return n,'USD'
    m=re.fullmatch(r'(-?[\d,.]+)亿(韩国元|新台币|欧元|日元|港元|美元|加元)（未换汇）',str(value))
    if m:return number(m[1]),{'韩国元':'KRW','新台币':'TWD','欧元':'EUR','日元':'JPY','港元':'HKD','美元':'USD','加元':'CAD'}[m[2]]
    return None,None

def growth(current,previous):
    a,b=current.get('amount'),previous.get('amount')
    if a is None or b is None:return {'value':'缺少本年或上年利润','kind':'missing','red':True,'reason':'缺少可解析的年度金额'}
    if not current.get('currency') or current['currency']!=previous.get('currency'):
        return {'value':f'币种不一致：{previous.get("currency")}→{current.get("currency")}','kind':'currency_mismatch','red':True,'reason':'未换汇，不跨币种相除'}
    verified=all(r.get('status')=='actual' for r in (current,previous)) and current.get('basis')==previous.get('basis') and bool(current.get('basis'))
    reason='同口径实际利润同比' if verified else '表内金额变化参考；包含EPS固定股数估算或未复核历史基数，会计调整口径可能不同'
    if b>0:
        ratio=a/b-1
        if a<0:return {'value':f'转亏（利润变化{ratio:.2%}）','kind':'loss_transition','red':not verified,'reason':reason,'ratio':ratio}
        return {'value':f'{ratio:.2%}','kind':'actual_ratio' if verified else 'reference_ratio','red':not verified,'reason':reason,'ratio':ratio}
    if b==0:
        return {'value':'由零转盈' if a>0 else '由零转亏' if a<0 else '持平（均为0）','kind':'zero_base','red':not verified,'reason':reason+'；上年为零，不计算常规百分比'}
    if a>=0:return {'value':'扭亏为盈' if a>0 else '亏损归零','kind':'loss_transition','red':not verified,'reason':reason+'；上年亏损，不计算常规同比'}
    improvement=(a-b)/abs(b)
    label='亏损收窄' if improvement>0 else '亏损扩大' if improvement<0 else '亏损持平'
    return {'value':f'{label}{abs(improvement):.2%}','kind':'loss_change','red':not verified,'reason':reason+'；亏损幅度变化=差额/上年亏损绝对值，不是常规同比'}

def load(path):return json.loads(path.read_text()) if path.exists() else {}
def envelope(symbol,kind):
    for folder in (OUT,ROOT/'opq_repair',ROOT/'forecast_repair'):
        result=load(folder/f'{symbol}_{kind}.json')
        if result:return result
    return {}

def historical_reports(env,symbol,asof):
    result={};duplicates=set()
    for row in ((env.get('data') or {}).get('result') or {}).get('data') or []:
        if row.get('SECURITY_CODE','').replace('_','.')!=symbol or str(row.get('SECUCODE','')).rsplit('.',1)[-1] not in ('N','O','A'):continue
        match=re.fullmatch(r'(2024|2025)/FY',str(row.get('REPORT_TYPE','')))
        if not match or str(row.get('DATE_TYPE_CODE'))!='001' or row.get('CURRENCY_ABBR') not in ('USD','CAD'):continue
        try:start,end,notice=[dt.date.fromisoformat(str(row[k])[:10]) for k in ('START_DATE','REPORT_DATE','NOTICE_DATE')]
        except (KeyError,ValueError):continue
        year=int(match[1]);amount=number(row.get('PARENT_HOLDER_NETPROFIT'))
        if amount is None or max(end,notice)>asof or not 350<=(end-start).days+1<=380:continue
        if end.year!=year and not (end.year==year+1 and end.month==1 and end.day<=7):continue
        if year in result:duplicates.add(year);continue
        result[year]={'value':round(amount/1e8,6),'currency':row['CURRENCY_ABBR'],'basis':'东财归母净利润','period':end.isoformat(),'source':env['url'],'retrieved_utc':env['retrieved_utc']}
    for year in duplicates:result.pop(year,None)
    return result

def build(asof):
    rows=load(OUT/'before.json')['data']['valueRange']['values'];rows=[[flat(v) for v in r] for r in rows]
    annual=load(ROOT/'opq_repair/records.json')['records'];records={};stats=Counter();base_updates=0
    for row in rows[1:]:
        symbol=row[3];month=annual[symbol]['fiscal_month'];month_basis='年度EPS接口财年末月份'
        if month is None:month,month_basis=fiscal_month(envelope(symbol,'forecast'),row)
        actual=reported_annual(envelope(symbol,'annual'),envelope(symbol,'financial_page'),symbol,month,asof)
        for r in actual.values():r['basis']='Nasdaq普通股股东净利润'
        for y,r in eastmoney_annual(envelope(symbol,'em_annual'),symbol,month,asof).items():
            r['basis']='东财归母净利润';actual.setdefault(y,r)
        for year,record in historical_reports(envelope(symbol,'em_annual'),symbol,asof).items():actual.setdefault(year,record)
        periods={};patches={};source_notes=[]
        for year,j in [(2024,52),(2025,13),(2026,14),(2027,15),(2028,16)]:
            amount,currency=table_amount(row[j]);status='archive';basis=None
            source=f'本次读取的在线表{j+1}列；历史原值未独立复核'
            if year<=2025 and year in actual:
                a=actual[year];amount=a['value'];currency=a.get('currency','USD');status='actual';basis=a['basis']
                source=f'{a["source"]}；抓取UTC={a["retrieved_utc"]}；财年期末={a["period"]}'
                if a.get('unit_source'):source+=f'；美元千元单位证据={a["unit_source"]}；单位页面抓取UTC={a["unit_retrieved_utc"]}'
                patches[str(j)]=amount if currency=='USD' else f'{amount}亿加元（未换汇）';patches[str(53 if year==2024 else 47)]=a['period']
                if year==2024:patches['54']=a['source']
                if row[j]!=patches[str(j)]:base_updates+=1
            elif year>=2026:
                a=annual[symbol]['years'][str(year)]
                if amount is not None and number(a['value']) is not None and math.isclose(amount,number(a['value']),abs_tol=1e-8):
                    status=a['status'];basis=('东财归母净利润' if 'datacenter' in a.get('source','') else 'Nasdaq普通股股东净利润') if status=='actual' else '固定当前股数EPS估算'
                    source=f'{a.get("source","")}；抓取UTC={a.get("retrieved_utc","")}；期末={a.get("period","")}；股数/币种假设见AZ年度利润说明'
            if amount is None:status='missing'
            periods[year]={'amount':amount,'currency':currency,'status':status,'basis':basis,'source':source}
            source_notes.append(f'FY{year}={amount} {currency}（{status}）；{source}')
        values=[];results=[]
        for year in range(2025,2029):
            result=growth(periods[year],periods[year-1]);values.append(result['value']);results.append(result);stats[result['kind']]+=1
        note=f'核验日{asof}；U=N/BA-1；V=O/N-1；W=P/O-1；X=Q/P-1；同币种且上年>0时计算。FY按公司财年，财年末月份={month}（{month_basis}）；'+'；'.join(source_notes)+'；'+'；'.join(f'FY{y}：{r["reason"]}' for y,r in zip(range(2025,2029),results))+'；红字为估算/历史未复核或缺项；预测→预测固定股数相同，其变化率等于EPS变化率；实际→预测仅作表内金额变化参考，不代表同GAAP口径增长。未从其他国家上市证券补数，未换汇。'
        records[symbol]={'values':values,'red_offsets':[i for i,r in enumerate(results) if r['red']],'bases':patches,'periods':periods,'note':note.replace('\n','；').replace('\r','')}
    payload={'records':records,'stats':dict(stats),'asof':str(asof),'changed_historical_amounts':base_updates}
    (OUT/'records.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in payload.items() if k!='records'},ensure_ascii=False));return payload

def apply_selection(rows,records=None):
    if records is None:
        cached=load(OUT/'records.json')
        if not cached:return rows,[],[]
        records=cached['records']
    out=[r[:] for r in rows];red=[];black=[];out[0][20:24]=HEADERS
    for i,row in enumerate(out[1:],2):
        rec=records.get(row[3])
        if not rec:continue
        for j,v in rec['bases'].items():row[int(j)]=v
        for j in (13,52):
            if str(j) in rec['bases']:black.append((i,j))
        for year,j in [(2026,14),(2027,15),(2028,16)]:
            amount,currency=table_amount(row[j]);record=rec['periods'][str(year)] if str(year) in rec['periods'] else rec['periods'][year]
            if (amount,currency)!=(record['amount'],record['currency']):raise ValueError(f'{row[3]} FY{year}: annual amounts changed; rebuild growth records')
        row[20:24]=rec['values']
        for offset in range(4):(red if offset in rec['red_offsets'] else black).append((i,20+offset))
        row[55]=MARKER+rec['note']
    return out,red,black
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--as-of',required=True);args=parser.parse_args();build(dt.date.fromisoformat(args.as_of))
