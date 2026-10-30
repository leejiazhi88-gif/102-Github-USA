"""Fail closed when instrument, currency or earnings denominator is unverified."""
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
BLOCKED = '暂停计算：EPS币种/每股单位/预测股数未核验'
POLICY = '2026-10-29证券与财务口径修正：不再用市值÷股价反推预测股数；EPS须核验币种、每普通股/每ADS、财年和GAAP/调整后口径；预测利润须另有同期间加权平均稀释股数。缺项停止计算，原始值保留。'

def col(j):
    s = ''
    j += 1
    while j:
        j, r = divmod(j-1, 26)
        s = chr(65+r)+s
    return s

def forward_pe(price, eps):
    """Inputs must already be normalized to exactly the same listed security."""
    for name, metric in [('price', price), ('eps', eps)]:
        if not metric.get('verified') or not metric.get('source'):
            raise ValueError(name + ': missing verified provenance')
        if not metric.get('security_id') or not metric.get('currency'):
            raise ValueError(name + ': missing security/currency')
    if price['security_id'] != eps['security_id'] or price['currency'] != eps['currency']:
        raise ValueError('security/currency mismatch; explicit conversion required')
    if not eps.get('period') or eps.get('basis') not in ('GAAP_diluted', 'IFRS_diluted', 'adjusted_diluted'):
        raise ValueError('EPS period or accounting basis missing')
    if eps['value'] <= 0 or price['value'] <= 0:
        raise ValueError('nonpositive PE inputs')
    return price['value'] / eps['value']

def earnings_from_eps(eps, shares):
    if not all(x.get('verified') and x.get('source') for x in (eps, shares)):
        raise ValueError('missing verified provenance')
    if shares.get('basis') != 'forecast_weighted_average_diluted':
        raise ValueError('current shares or market-cap proxy cannot stand in for forecast diluted shares')
    if not eps.get('security_id') or eps.get('security_id') != shares.get('security_id'):
        raise ValueError('per-share security mismatch')
    if not eps.get('period') or eps.get('period') != shares.get('period'):
        raise ValueError('period mismatch')
    if not eps.get('currency') or eps.get('basis') not in ('GAAP_diluted','IFRS_diluted','adjusted_diluted'):
        raise ValueError('currency or EPS basis missing')
    if shares['value'] <= 0:
        raise ValueError('invalid share count')
    return eps['value'] * shares['value']

def profile(symbol):
    return json.loads((ROOT/f'online-test/vibe_{symbol}.json').read_text()).get('profile',{}).get('data') or {}

def apply_policy(payload):
    result = copy.deepcopy(payload)
    changed = set()
    flagged = set()
    audit = []
    foreign = []
    def put(ri, j, v, red=True):
        if result['rows'][ri-1][j] != v:
            result['rows'][ri-1][j] = v
            changed.add((ri,j))
        if red and ri > 1:
            flagged.add(f'{col(j)}{ri}')
    for j,y in [(7,2026),(8,2027),(9,2028)]:
        put(1,j,f'FY{y} PE（仅同口径核验后计算）',False)
    put(1,52,'FY2024归母净利润（亿美元或明确注明原币）',False)
    put(1,84,'预测加权平均稀释股数（亿股；须独立来源）',False)
    for ri,row in enumerate(result['rows'][1:],2):
        symbol = row[3]
        p = profile(symbol)
        location = p.get('country') or '供应商未提供'
        # This is a risk-screening attribute, not proof of legal incorporation.
        cross_market = location != 'United States 美国' or p.get('security_type') != '美股' or row[61] != '美元'
        if cross_market:
            foreign.append(symbol)
        blocked = set()
        for j in [12,13,14,33,34,*range(36,46)]:
            if isinstance(row[j],str) and row[j].startswith('='):
                put(ri,j,BLOCKED)
                blocked.add(j)
        put(ri,84,'未取得同预测期间加权平均稀释股数；禁用市值÷股价替代')
        for j,profit in [(7,12),(8,13),(9,14)]:
            if profit in blocked or cross_market:
                put(ri,j,'暂停计算：证券/币种/盈利口径未通过核验')
        for j,a,b in [(18,11,52),(19,12,11),(20,13,12),(21,14,13)]:
            if a in blocked or b in blocked:
                put(ri,j,'暂停计算：依赖尚未核验的预测利润')
        for j in [54,118]:
            old = str(row[j])
            pieces = [x for x in old.split('\n') if not x.startswith(('预测利润=','非美元财报保留原币；ADR/本股','2026-10-29证券与财务口径修正：'))]
            put(ri,j,'；'.join(pieces+[POLICY]))
        for j in [53,117]:
            old = str(row[j])
            old = old.replace('预测折算以财年结束年份归属，红字；不能解释为公司公布的归母净利润预测。','预测利润折算已停用；保留原始EPS，核验完成前不参与估值。')
            put(ri,j,old.replace('\n','；'))
        security = p.get('security_type') or '待核验'
        identity_status = '供应商分类；尚未完成官方证券映射核验'
        official = ''
        if symbol == 'ASML':
            security = 'NASDAQ记名普通股（registered ASML NASDAQ shares）'
            identity_status = '官网已确认证券类型、ISIN与美元报价；股数与EPS仍待核验'
            official = 'https://www.asml.com/en/investors/shares'
            put(ri,59,f'ASML；{security}；NASDAQ；USD；ISIN USN070592100；荷兰；财报EUR。供应商“美国存托凭证”标签已更正。官网：{official}')
        if cross_market:
            put(ri,6,'暂停计算：公司总市值与TTM利润口径尚未独立核验')
            flagged.update(f'{col(j)}{ri}' for j in (5,80,59))
            note = '跨市场核验：公司所在地/注册地、上市证券、报价币种、财报币种必须分别记录；美元财报不代表美国公司；本地股票与美股历史不得拼接。'
            for j in [54,118]:
                put(ri,j,str(result['rows'][ri-1][j])+'；'+note)
        audit.append([
            symbol, location+'（供应商地区；非注册地已核验结论）', security,
            str(p.get('isin') or '缺失'), 'USD（现有美股报价快照） / '+str(row[61]),
            identity_status,
            '每份美股对应普通股数、比例生效日、拆股及公司行动：待官方证据' if cross_market else '普通股身份仍按供应商记录；预测EPS分母需独立核验',
            '原始EPS保留；接口未明确币种、每ADS/每本股、GAAP/调整后，不进入派生计算',
            '市值保留供应商原值；非独立核验。预测股数禁用市值÷股价；总市值不得用实际存托凭证发行量代替公司总股本',
            official or '现有来源索引见主表DL列；官方映射未完成',
            ('跨市场估值暂停；' if cross_market else '')+'预测利润及其派生PE/同比暂停；实际报表原值与美股行情保留'
        ])
    result['black_cells'] = [c for c in result['black_cells'] if c not in flagged]
    result['red_cells'] = sorted(set(result['red_cells']) | flagged)
    result['stats']['prediction_cells'] = sum(isinstance(r[j],str) and r[j].startswith('=') for r in result['rows'][1:] for j in (12,13,14))
    result['valuation_policy'] = {'version':'2026-10-29-v1','foreign_symbols':foreign,'forecast_proxy_disabled':True,'audit':audit}
    from us_market_policy import apply_us_scope
    result = apply_us_scope(result)
    changed = {(ri,j) for ri,(old,new) in enumerate(zip(payload['rows'],result['rows']),1) for j,(a,b) in enumerate(zip(old,new)) if a != b}
    flagged.update(f'G{ri}' for ri in range(2,len(result['rows'])+1))
    result['black_cells'] = [c for c in result['black_cells'] if c not in flagged]
    result['red_cells'] = sorted(set(result['red_cells']) | flagged)
    return result, sorted(changed), sorted(flagged)
