"""Quarterly actuals and explicit fixed-current-share scenario, never annual / 4."""
import calendar,datetime as dt,json,math
from collections import Counter
from pathlib import Path
from forecast_fields import number
ROOT=Path(__file__).parent;OUT=ROOT/'quarter_extension'
PERIODS=[(y,q) for y in (2026,2027,2028) for q in (1,2,3,4)]
KEYS=[f'FY{y}Q{q}' for y,q in PERIODS];KEYS.insert(2,'locked_Q3')
HEADERS=[f'{k}利润（实际/固定股数估算；亿美元或注明原币）' if k!='locked_Q3' else '原表Q3锁定基础（仅保留，不参与计算）' for k in KEYS]
HEADERS+=['季度财年/实际与估算标识','季度预测EPS原值及期末','固定股数假设（接口原值）','季度取数时间与来源','季度口径/缺项说明']
MAIN_COLUMNS=[33,34,35,*range(36,46)]
AS_OF=dt.date(2026,11,4)

def flat(v):return ''.join(x.get('text','') for x in v) if isinstance(v,list) else '' if v is None else v
def fiscal_month(envelope,row):
    data=(envelope.get('data') or {}).get('data') or {}
    months=[]
    for r in (data.get('yearlyForecast') or {}).get('rows') or []:
        try:months.append(dt.datetime.strptime(r['fiscalEnd'],'%b %Y').month)
        except (ValueError,KeyError):pass
    if months:
        if len(set(months))!=1:return None,'年度预测财年末月份不一致，须逐期核验'
        return months[0],'Nasdaq年度预测期末月份'
    for value in row[47:51]:
        for fmt in ('%Y-%m-%d','%b %Y'):
            try:
                date=dt.datetime.strptime(str(value),fmt)
                if fmt=='%Y-%m-%d' and date.day<=7:date-=dt.timedelta(days=date.day)
                return date.month,'参考表已注明的财年期末；本次未独立核验'
            except ValueError:pass
    return None,'缺少财年末月份'

def quarter_key(date,fy_month,monthly=False):
    """Account for fiscal years ending in early next month (52/53-week calendars)."""
    if fy_month is None:return None
    normalized=date
    if (fy_month-date.month)%3 and not monthly and date.day<=7:normalized=date-dt.timedelta(days=date.day)
    if (fy_month-normalized.month)%3:return None
    fy=normalized.year+(normalized.month>fy_month)
    q=4-((fy_month-normalized.month)%12)//3
    return f'FY{fy}Q{q}'

def actual_quarters(envelope,page,symbol,fy_month):
    if envelope.get('http') not in (None,'200'):return {},'季度财务请求未成功：HTTP '+str(envelope.get('http'))
    if not page.get('usd_thousands_label'):return {},'未取得该股美元千元页面单位证据'
    data=(envelope.get('data') or {}).get('data') or {}
    if data.get('symbol','').upper().replace('/','.')!=symbol.upper():return {},'季度财务API未返回该证券数据'
    table=data.get('incomeStatementTable') or {}
    if 'quarter' not in str((table.get('headers') or {}).get('value1','')).lower():return {},'源未标明单季表'
    source_row=next((r for r in table.get('rows',[]) if r.get('value1')=='Net Income Applicable to Common Shareholders'),None)
    if not source_row:return {},'源单季普通股股东净利润缺失'
    result={};ambiguous=set()
    for column,period in (table.get('headers') or {}).items():
        if column=='value1':continue
        try:date=dt.datetime.strptime(period,'%m/%d/%Y').date()
        except (ValueError,TypeError):continue
        key=quarter_key(date,fy_month);value=number(source_row.get(column))
        if not key or value is None or date>AS_OF:continue
        if key in result:ambiguous.add(key);continue
        result[key]={'value':round(value/100000,6),'status':'actual','period':date.isoformat(),'source':envelope['url'],'retrieved_utc':envelope['retrieved_utc'],'unit':'亿美元','unit_source':page['url']}
    for key in ambiguous:result.pop(key,None)
    return result,'同股Nasdaq单季普通股股东净利润；页面单位USD Thousands'

def quarter_forecasts(envelope,symbol,fy_month,shares):
    data=(envelope.get('data') or {}).get('data') or {}
    if data.get('symbol','').upper().replace('/','.')!=symbol.upper():return {}
    result={};count=number(shares.get('shares'));currency=data.get('currency');duplicates=set()
    for row in (data.get('quarterlyForecast') or {}).get('rows') or []:
        try:date=dt.datetime.strptime(row['fiscalEnd'],'%b %Y').date()
        except (ValueError,KeyError):continue
        key=quarter_key(date,fy_month,monthly=True);eps=number(row.get('consensusEPSForecast'))
        if not key or eps is None:continue
        if key in result:duplicates.add(key);continue
        status='estimate' if count is not None and count>0 and shares.get('symbol')==symbol and currency in (None,'','USD') else 'eps_only'
        value=round(eps*count/1e8,6) if status=='estimate' else f'预测EPS {eps}；股数/币种未对应'
        result[key]={'value':value,'status':status,'eps':eps,'period':row['fiscalEnd'],'estimates':row.get('noOfEstimates'),'source':envelope['url'],'retrieved_utc':envelope['retrieved_utc'],'shares':count,'basis':'EPS按美股每份USD与同代码f38股数解释；当前股数不变，非预测稀释股数；调整口径未明示'}
    for key in duplicates:result.pop(key,None)
    return result

def archived_main_value(key,value,fy_month):
    """An old numeric cell is not evidence of a reported actual, especially in future quarters."""
    if fy_month is None:return None
    year=int(key[2:6]);quarter=int(key[-1])
    month_index=year*12+fy_month-1-(4-quarter)*3
    end_year,end_month=month_index//12,month_index%12+1
    end=dt.date(end_year,end_month,calendar.monthrange(end_year,end_month)[1])
    if end>AS_OF or not (number(value) is not None or '未换汇' in str(value)):return None
    return {'value':value,'status':'unverified_archive','period':key,'source':'综合投研汇总原表存档；本次未独立复核','retrieved_utc':'2026-10-29档案'}

def build():
    rows=json.loads((OUT/'selection_before.json').read_text())['data']['valueRange']['values'];rows=[[flat(v) for v in r] for r in rows]
    main=json.loads((OUT/'main_before.json').read_text())['data']['valueRange']['values'];main={flat(r[3]):[flat(v) for v in r] for r in main[1:]}
    shares=json.loads((OUT/'shares.json').read_text());records={};stats=Counter()
    for row in rows[1:]:
        symbol=row[3]
        def load(path):return json.loads(path.read_text()) if path.exists() else {}
        forecast=load(ROOT/'forecast_repair'/f'{symbol}_forecast.json');month,month_basis=fiscal_month(forecast,row)
        actual,actual_note=actual_quarters(load(OUT/f'{symbol}_quarter.json'),load(OUT/f'{symbol}_page.json'),symbol,month)
        archived,_=actual_quarters(load(OUT/f'{symbol}_archive.json'),load(OUT/f'{symbol}_page.json'),symbol,month)
        for key,record in archived.items():
            if key not in actual:actual[key]={**record,'status':'archived_actual'}
        forecasts=quarter_forecasts(forecast,symbol,month,shares.get(symbol,{}));records_by_key={}
        for key in KEYS:
            if key=='locked_Q3':
                records_by_key[key]={'value':main[symbol][35] if symbol in main else '无原表锁定值','status':'locked','period':'原表存档，不参与计算'};continue
            if key in actual:record=actual[key]
            elif key in forecasts:record=forecasts[key]
            elif symbol in main and (old_record:=archived_main_value(key,main[symbol][MAIN_COLUMNS[KEYS.index(key)]],month)):
                record=old_record
            else:record={'value':'源未覆盖该季度','status':'missing','period':key}
            records_by_key[key]=record;stats[record['status']]+=1
        periods='；'.join(f'{k}：{r["period"]} '+{'actual':'实际USD','archived_actual':'实际档案','unverified_archive':'原表存档待核验','estimate':'固定股数估算','eps_only':'仅EPS','locked':'锁定存档','missing':'未覆盖'}[r['status']] for k,r in records_by_key.items())
        eps_text='；'.join(f'{k} / {r["period"]}：EPS {r["eps"]}，{r["estimates"]}家' for k,r in forecasts.items()) or '源未提供可归属财季的EPS预测'
        share=shares.get(symbol,{});share_text=f'东财美股f38={share.get("shares","缺失")}股；抓取UTC {share.get("retrieved_utc","缺失")}；假设当前股数不变，非未来加权稀释股数'
        sources='；'.join(dict.fromkeys(r.get('source','')+' '+r.get('retrieved_utc','') for r in [*records_by_key.values()] if r.get('source')))
        sources+='；股数源：'+share.get('source','未取得')
        note=f'财年末月份={month}（{month_basis}）；{actual_note}；预测=同美股代码EPS×接口直接股数/1亿，不以市值÷股价反推。EPS币种/ADR每份与股数单位、GAAP调整未独立核验，估算红字；不等于直接净利润共识。预测保留11/03抓取快照时间，源未提供asOf；实际与预测可能不同更新批次。原表无独立来源的历史值仅标存档待核验，不视为本次取得实际值。不得按年度/4填季度；锁定Q3仅存档。'
        values=[records_by_key[k]['value'] for k in KEYS]+[periods,eps_text,share_text,sources,note]
        values=[str(v).replace('\r','').replace('\n','；') if isinstance(v,str) else v for v in values]
        records[symbol]={'values':values,'quarters':records_by_key,'fy_month':month,'red_offsets':[i for i,k in enumerate(KEYS) if records_by_key[k]['status']!='actual']}
    data={'headers':HEADERS,'records':records,'stats':dict(stats),'stock_count':len(records),'new_columns':len(HEADERS)}
    (OUT/'payload.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in data.items() if k not in ('records','headers')},ensure_ascii=False))
    return data

def extend_selection(rows,payload=None):
    if payload is None:
        path=OUT/'payload.json'
        if not path.exists():return rows,[]
        payload=json.loads(path.read_text())
    extended=[rows[0][:72]+payload['headers']];red=[]
    for i,row in enumerate(rows[1:],2):
        rec=payload['records'][row[3]];extended.append(row[:72]+rec['values']);red.extend((i,72+j) for j in rec['red_offsets'])
    return extended,red

def apply_main(rows):
    path=OUT/'payload.json'
    if not path.exists():return rows,[],[]
    payload=json.loads(path.read_text());out=[r[:] for r in rows];red=[];black=[]
    for offset,j in enumerate(MAIN_COLUMNS):out[0][j]=HEADERS[offset]
    for i,row in enumerate(out[1:],2):
        rec=payload['records'].get(row[3])
        if not rec:continue
        for offset,j in enumerate(MAIN_COLUMNS):
            if KEYS[offset]=='locked_Q3':continue
            r=rec['quarters'][KEYS[offset]]
            row[j]=rec['values'][offset]
            (black if r['status']=='actual' else red).append((i,j))
        row[83]=rec['values'][14]
        row[118]=str(row[118]).split('【季度模块】')[0]+'；【季度模块】'+'；'.join(str(x) for x in rec['values'][13:])
    return out,red,black

if __name__=='__main__':build()
