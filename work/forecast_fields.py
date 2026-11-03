"""Separate provider EPS reference valuation from total-net-income estimation."""
import calendar,datetime as dt,json,math,re
from pathlib import Path
ROOT=Path(__file__).parent;OUT=ROOT/'forecast_repair'
RULE='远期参考PE直接以同一美股证券价格÷Nasdaq年度预测EPS计算，不依赖预测股数或总利润；EPS接口未明示币种/GAAP调整口径，按美股每份USD解释仅作红字参考，不标已独立核验。财年按源fiscalEnd的结束年份。'

def number(x):
    if isinstance(x,bool):return None
    if isinstance(x,str):x=x.replace('$','').replace(',','').strip()
    try:v=float(x)
    except (ValueError,TypeError):return None
    return v if math.isfinite(v) else None

def annual_forecasts(envelope,symbol):
    if not envelope:return {},'not_requested'
    if not envelope.get('ok'):
        response=envelope.get('data') or {};provider_status=response.get('status') or {}
        messages=provider_status.get('bCodeMessage') or []
        if any('Symbol not exists' in str(m.get('errorMessage','')) for m in messages):return {},'provider_symbol_unavailable'
        if envelope.get('http')=='200' and provider_status.get('rCode')==200 and response.get('data') is None:return {},'provider_empty_data'
        return {},'request_failed'
    data=(envelope.get('data') or {}).get('data') or {}
    if data.get('symbol','').upper().replace('/','.')!=symbol.upper():return {},'security_mismatch'
    table=data.get('yearlyForecast') or {};result={};duplicates=set()
    for raw in table.get('rows') or []:
        try:end=dt.datetime.strptime(raw.get('fiscalEnd',''),'%b %Y')
        except ValueError:continue
        year=end.year
        if year in result:duplicates.add(year);continue
        value=number(raw.get('consensusEPSForecast'))
        result[year]={'year':year,'period':raw['fiscalEnd'],'eps':value,'low':number(raw.get('lowEPSForecast')),'high':number(raw.get('highEPSForecast')),'estimates':number(raw.get('noOfEstimates')),'source':envelope['url'],'retrieved_utc':envelope['retrieved_utc'],'provider_asof':table.get('asOf'),'symbol':symbol,'currency':data.get('currency'),'basis':data.get('epsBasis') or 'provider_unspecified'}
    for year in duplicates:result.pop(year,None)
    return result,'duplicate_year' if duplicates else 'available' if result else 'provider_no_annual_rows'

def reference_pe(price,eps):
    """Explicitly conditional output; does not weaken verified forward_pe()."""
    if price.get('symbol')!=eps.get('symbol'):return None,'security_mismatch'
    if price.get('currency')!='USD' or eps.get('currency') not in (None,'','USD'):return None,'currency_mismatch'
    if not price.get('source') or not eps.get('source') or not eps.get('period'):return None,'provenance_missing'
    p=number(price.get('price'));e=number(eps.get('eps'))
    if p is None or p<=0:return None,'price_missing'
    if e is None:return None,'eps_missing'
    if e<=0:return None,'nonpositive_eps'
    return p/e,'reference_estimate_not_independently_verified'

def usd_actuals(envelope,page,symbol,asof):
    if not envelope or not envelope.get('ok') or not page or not page.get('ok') or not page.get('usd_thousands_label'):return {}
    data=(envelope.get('data') or {}).get('data') or {}
    if data.get('symbol','').upper()!=symbol.upper():return {}
    table=data.get('incomeStatementTable') or {}
    row=next((r for r in table.get('rows',[]) if r.get('value1')=='Net Income Applicable to Common Shareholders'),None)
    if row is None:return {}
    result={}
    for key,rawdate in (table.get('headers') or {}).items():
        if key=='value1':continue
        try:end=dt.datetime.strptime(rawdate,'%m/%d/%Y').date()
        except (ValueError,TypeError):continue
        value=number(row.get(key))
        if end>asof or value is None:continue
        result[end.year]={'year':end.year,'period':end.isoformat(),'net_income_100m_usd':value/100000,'source':envelope['url'],'unit_evidence':page['url'],'retrieved_utc':envelope['retrieved_utc']}
    return result

def load_records():
    path=OUT/'records.json';return json.loads(path.read_text()) if path.exists() else {}

def apply_rows(rows,layout,records=None):
    """Patch only supported fields; preserve stock order, quote snapshots and inputs."""
    records=load_records() if records is None else records
    if not records:return rows,[]
    out=[list(r) for r in rows];red=[]
    main=layout=='main';pe_indices=[7,8,9] if main else [9,10,11];eps_indices=[85,86,87] if main else [67,68,69]
    for y,j,e in zip((2026,2027,2028),pe_indices,eps_indices):
        out[0][j]=f'FY{y} PE（预测EPS参考；实际另注）';out[0][e]=f'FY{y}预测EPS（Nasdaq原值；日期见备注）'
    actualcols={2024:52,2025:11,2026:12,2027:13,2028:14} if main else {2024:52,2025:13,2026:14,2027:15,2028:16}
    for y,j in actualcols.items():out[0][j]=f'FY{y}净利润（实际值；亿美元或明确原币）'
    for i,row in enumerate(out[1:],1):
        symbol=row[3];rec=records.get(symbol)
        if not rec:continue
        forecasts=rec['forecasts'];actual=rec.get('actuals',{});notes=[]
        for y,j,e in zip((2026,2027,2028),pe_indices,eps_indices):
            f=forecasts.get(str(y))
            if f:
                row[e]=f['eps'] if f['eps'] is not None else '源预测EPS缺失'
                pe,status=reference_pe(rec['price'],f)
                row[j]=round(pe,6) if pe is not None else '预测EPS≤0，不适用' if status=='nonpositive_eps' else f'未计算：{status}'
                red.extend([(i,j),(i,e)])
                notes.append(f'FY{y}源期末{f["period"]}；EPS {f["eps"]}；{f["estimates"]}家')
            elif isinstance(row[j],str) and ('未取得' in row[j] or '未计算' in row[j] or '暂停' in row[j]):
                if str(y) in actual and actual[str(y)]['net_income_100m_usd']>0 and number(row[5]):
                    row[j]=round(number(row[5])/actual[str(y)]['net_income_100m_usd'],6)
                    notes.append(f'FY{y}已出实际年报；PE=本表市值÷该年实际利润，非未来预测');red.append((i,j))
                else:row[j]='源未提供该财年预测；非请求失败' if rec['forecast_status']=='available' else '预测源状态：'+rec['forecast_status']
            if not f and number(row[j]) is not None:notes.append(f'FY{y}保留实际年报市盈率，非未来预测')
        for year,j in actualcols.items():
            if str(year) in actual:
                row[j]=round(actual[str(year)]['net_income_100m_usd'],6)
                notes.append(f'FY{year}实际：{actual[str(year)]["period"]}，Nasdaq美元千元原值/100000')
            elif year>=2026 and isinstance(row[j],str) and ('未取得' in row[j] or '不折算' in row[j]):
                row[j]='有预测EPS，无直接预测净利润' if str(year) in forecasts else '该财年利润未提供'
        # Actual growth is available without inventing total forecast earnings.
        for year,j in zip((2025,2026,2027,2028),[18,19,20,21] if main else [20,21,22,23]):
            a=actual.get(str(year));b=actual.get(str(year-1))
            if a and b and b['net_income_100m_usd']>0:
                row[j]=f'{(a["net_income_100m_usd"]/b["net_income_100m_usd"]-1)*100:.2f}%'
        price=rec['price'];note=f'【预测数据修复】{RULE}参考价格={price.get("price")} USD，价格时间UTC={price.get("quote_utc","未提供")}；预测抓取UTC={rec.get("forecast_retrieved_utc","未取得")}；源预测asOf未提供，不宣称已按最新财报更新；'+'；'.join(notes)
        note+='；价格源：'+str(price.get('source','未提供'))+'；预测源：'+rec['forecast_url']
        if actual:note+='；实际利润源：'+next(iter(actual.values()))['source']+'；页面单位In USD Thousands；没有自行换汇'
        if main:
            row[82]='；'.join(f'{f["period"]}: EPS {f["eps"]} [{f["low"]}～{f["high"]}]；{f["estimates"]}家' for f in forecasts.values()) or rec['forecast_status']
            for j in (54,118):row[j]=str(row[j]).split('【预测数据修复】')[0]+'；'+note
            row[117]=note
        else:
            row[45]=note;row[51]=note
    return out,red

def build_records():
    prices=json.loads((OUT/'prices.json').read_text());records={}
    for symbol,price in prices.items():
        def load(kind):
            p=OUT/f'{symbol}_{kind}.json';return json.loads(p.read_text()) if p.exists() else None
        forecast=load('forecast');fs,status=annual_forecasts(forecast,symbol)
        actual=usd_actuals(load('annual'),load('financial_page'),symbol,dt.date(2026,11,3))
        price['quote_utc']=dt.datetime.fromtimestamp(price['quote_epoch'],dt.timezone.utc).isoformat() if number(price.get('quote_epoch')) else '未提供'
        records[symbol]={'symbol':symbol,'price':price,'forecasts':{str(k):v for k,v in fs.items()},'forecast_status':status,'forecast_url':f'https://api.nasdaq.com/api/analyst/{symbol}/earnings-forecast','forecast_retrieved_utc':(forecast or {}).get('retrieved_utc'),'actuals':{str(k):v for k,v in actual.items()}}
    (OUT/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));return records

if __name__=='__main__':
    r=build_records();print('records',len(r),'annual forecasts',sum(bool(x['forecasts']) for x in r.values()),'USD actuals',sum(bool(x['actuals']) for x in r.values()))
