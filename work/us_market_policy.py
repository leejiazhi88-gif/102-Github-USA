"""Use the requested US listing only; never supplement from a home-market listing."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).parent
from ttm_source import SCOPE,apply_ttm

def apply_us_scope(payload):
    result=copy.deepcopy(payload)
    result['rows'][0][6]='PE（美股接口原值；供应商未明示TTM）'
    for row in result['rows'][1:]:
        symbol=row[3]
        quote=json.loads((ROOT/f'composite/{symbol}_quote.json').read_text())
        q=quote.get('data') or {}
        pe=q.get('pe')
        row[6]=pe if quote.get('ok') and q.get('currency')=='USD' and isinstance(pe,(int,float)) else '美股接口未取得'
        note=f'取数范围：仅美股{symbol}。PE为该美股报价接口原值，接口未明示TTM，不作为独立核算结果；报价时间{q.get("timestamp","未提供")}。其他市场不补数；本币财报不换汇。'
        for j in (54,118):
            row[j]=note+'；预测EPS保留供应商原值；缺少美股口径预测净利润时标缺失，不以市值÷股价反推股数生成利润。'
        for j in (53,117):
            row[j]=str(row[j]).replace('核验完成前不参与估值','不跨市场换算生成利润或估值')
        for j in [7,8,9,12,13,14,18,19,20,21,33,34,*range(36,46)]:
            if isinstance(row[j],str) and row[j].startswith('暂停计算'):
                row[j]='未取得同口径美股来源数据；不跨市场补算'
        row[84]='美股来源未提供同期间预测加权平均稀释股数'
    vp=result.get('valuation_policy',{})
    for row in vp.get('audit',[]):
        row[5]='按本行美股代码取数；证券身份不与本地上市证券混用'
        if row[0]=='ASML':row[5]='美股NASDAQ记名普通股已由官网确认；仅用美股代码ASML'
        row[6]='不调用其他国家或地区的上市证券；不做本股/美股换算补数'
        row[7]='展示美股代码下的原始EPS预测；未明示币种/分母时注明，不推算总利润'
        row[8]='美股接口市值和PE原值保留并注明来源；不通过其他上市市场推算'
        row[10]='有美股原始值直接展示；缺项标未取得；保留本币报表原值，不换汇'
    result['source_scope']={'market':'US','symbol_source':'main_table_column_D','allow_home_market_fallback':False,'allow_cross_listing_conversion':False,'policy':SCOPE}
    return apply_ttm(result)
