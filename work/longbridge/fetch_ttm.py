"""Read-only, US-listing-only Longbridge PE TTM collector. No trading APIs."""
import argparse
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
KEYS=('LONGBRIDGE_APP_KEY','LONGBRIDGE_APP_SECRET','LONGBRIDGE_ACCESS_TOKEN')

def number(value):
    if value is None:return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def validate(record):
    """Check within-provider consistency without declaring an external benchmark correct."""
    issues=[]
    if not record['symbol'].endswith('.US'):issues.append('非美股代码')
    if record.get('currency')!='USD':issues.append('报价币种非USD或缺失')
    pe=number(record.get('pe_ttm_ratio'));eps=number(record.get('eps_ttm'));price=number(record.get('calc_last_done'))
    if pe is None:issues.append('长桥未返回PE TTM')
    if eps is None:issues.append('长桥未返回EPS TTM')
    if price is None or price<=0:issues.append('同次指标响应缺少有效价格')
    expected=None
    if eps is not None and eps>0 and price is not None and price>0:
        expected=price/eps
        if pe is not None and abs(pe-expected)>max(.02,abs(expected)*.01):issues.append('同源价格÷EPS TTM与PE TTM偏差超过1%；需检查时点/更新批次')
    elif eps is not None and eps<=0:
        issues.append('TTM EPS非正；PE不作为正常正盈利估值')
    qp=number(record.get('regular_last_done'))
    if qp and price and abs(qp-price)>max(.01,price*.001):issues.append('两次请求价格不同；可能在交易中变化，不混用快照')
    return {**record,'calculated_pe_check':expected,'issues':issues,'validation':'同源内部校验通过；仍需首次与App同一时段验收' if not issues else '待核验'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file',type=Path,default=HERE/'.env')
    parser.add_argument('--symbols',nargs='+',default=['SKHY.US','TSM.US','ASML.US'])
    parser.add_argument('--all',action='store_true',help='Read all 24 US listings from the current sheet symbol list')
    parser.add_argument('--output',type=Path,default=HERE/'latest_ttm.json')
    args=parser.parse_args()
    symbols=[s+'.US' for s in json.loads((HERE.parent/'test_symbols.json').read_text())] if args.all else args.symbols
    if any(not s.endswith('.US') for s in symbols):parser.error('Only .US symbols are permitted')
    cfg={k:os.environ.get(k,'') for k in KEYS}
    if args.env_file.exists():
        for line in args.env_file.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                k,v=line.split('=',1)
                if k.strip() in KEYS and not cfg[k.strip()]:cfg[k.strip()]=v.strip().strip('\"\'')
    missing=[k for k,v in cfg.items() if not v]
    if missing:
        print(json.dumps({'status':'needs_account_configuration','missing_variable_names':missing,'network_calls':0},ensure_ascii=False))
        return 2
    from longbridge.openapi import Config,QuoteContext,CalcIndex
    config=Config.from_apikey(cfg[KEYS[0]],cfg[KEYS[1]],cfg[KEYS[2]],enable_print_quote_packages=False)
    ctx=QuoteContext(config)
    started=datetime.now(timezone.utc).isoformat()
    indexes={x.symbol:x for x in ctx.calc_indexes(symbols,[CalcIndex.PeTtmRatio,CalcIndex.LastDone,CalcIndex.TotalMarketValue])}
    statics={x.symbol:x for x in ctx.static_info(symbols)}
    quotes={x.symbol:x for x in ctx.quote(symbols)}
    records=[]
    for symbol in symbols:
        idx,static,quote=indexes.get(symbol),statics.get(symbol),quotes.get(symbol)
        pre=getattr(quote,'pre_market_quote',None)
        record={'symbol':symbol,'provider':'Longbridge official OpenAPI','currency':getattr(static,'currency',None),'pe_ttm_ratio':number(getattr(idx,'pe_ttm_ratio',None)),'eps_ttm':number(getattr(static,'eps_ttm',None)),'calc_last_done':number(getattr(idx,'last_done',None)),'regular_last_done':number(getattr(quote,'last_done',None)),'quote_timestamp':str(getattr(quote,'timestamp','')),'pre_market_price_separate':number(getattr(pre,'last_done',None)),'total_market_value':number(getattr(idx,'total_market_value',None))}
        records.append(validate(record))
    result={'status':'fetched','started_at_utc':started,'finished_at_utc':datetime.now(timezone.utc).isoformat(),'source':'Longbridge official QuoteContext','scope':'US listings only; source PE TTM is never replaced by a calculated estimate','records':records}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'status':'fetched','count':len(records),'with_issues':sum(bool(x['issues']) for x in records),'output':str(args.output)},ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
