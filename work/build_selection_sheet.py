import collections,datetime as dt,json,math,re
from pathlib import Path
from selection_sources import OUT
from selection_build_candidates import source_rows,clean,GROUPS,CONFIG

REFERENCE='https://my.feishu.cn/wiki/SWDBwMvwuiE5dzkex5rcFbs2n5f?sheet=K3baGL'
def numeric(v):return isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)
def pct(v):return f'{v:.2%}' if numeric(v) else v
def bjt(epoch):return dt.datetime.fromtimestamp(epoch,dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S') if numeric(epoch) else '未提供'
def time_bjt(iso):return dt.datetime.fromisoformat(iso).astimezone(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
def col(j):
    result='';j+=1
    while j:result=chr(65+(j-1)%26)+result;j=(j-1)//26
    return result

def choose(candidates):
    grouped=collections.defaultdict(list)
    for c in candidates:grouped[c['group']].append(c)
    result=[]
    for group in sorted(grouped):
        ordered=sorted(grouped[group],key=lambda c:(-c['cap'],c['symbol']))
        for rank,c in enumerate(ordered,1):
            if c['cap']>=30_000_000_000 or rank<=2:result.append(dict(c,rank=rank,reason='市值≥300亿美元；类目前二' if rank<=2 and c['cap']>=3e10 else '市值≥300亿美元' if c['cap']>=3e10 else '低于300亿美元；二级类目前二补足'))
    return result

def sort_by_group_cap(selected):
    sector_totals=collections.defaultdict(float);group_totals=collections.defaultdict(float)
    for c in selected:
        sector_totals[c['sector']]+=c['cap']
        group_totals[(c['sector'],c['group'])]+=c['cap']
    return sorted(selected,key=lambda c:(-sector_totals[c['sector']],c['sector'],-group_totals[(c['sector'],c['group'])],c['group'],-c['cap'],c['symbol']))

def main():
    candidate=json.loads((OUT/'candidates.json').read_text());selected=sort_by_group_cap(choose(candidate['candidates']))
    quotes=json.loads((OUT/'selected_quotes.json').read_text());refs=source_rows()
    nasdaq=json.loads((OUT/'nasdaq_screen.json').read_text());captured=time_bjt(nasdaq['retrieved_utc'])
    raw_header=json.loads((OUT/'reference_values.json').read_text())['data']['valueRange']['values'][0][:56]
    h=[clean(v) for v in raw_header]
    h[1]='GICS一级';h[2]='GICS二级';h[5]='筛选市值（亿美元；Nasdaq）';h[6]='PE TTM（东财美股原值）'
    for j,year in [(7,2026),(8,2027),(9,2028)]:h[j]=f'FY{year} PE（同口径预测缺失不计算）'
    h[10]='FY2026–2028预测利润增长（不跨口径计算）'
    for j,year in [(11,2025),(12,2026),(13,2027),(14,2028)]:h[j]=f'FY{year}净利润（档案实际值；币种见备注）'
    h[22]='美股行情日期';h[23]='当日涨幅%（东财）'
    for j in range(24,33):h[j]=h[j].replace('（源收盘价）','')+'（参考10/27档案）'
    h[38]='GICS分类依据';h[39]='原参考表入选依据（历史）';h[40]='现价USD（与PE同次）';h[41]='来源与快照说明';h[43]='PE口径与当前质量备注';h[49]='财务币种/日期/采用规则';h[50]='FY2024净利润（档案实际原值）'
    header=h[:7]+['二级市值排名','入选依据（当前）']+h[7:]+['市值抓取时间BJT','PE/现价时间BJT','筛选市值来源','东财美股市值（亿美元；核对）','市值源间差异%','阈值/异常提示','历史涨幅基准日','财务/分部档案日期','参考资料链接','FY2026预测EPS（档案原值）','FY2027预测EPS（档案原值）','FY2028预测EPS（档案原值）','分类与筛选校验','证券范围']
    assert len(header)==72
    semi=json.loads((Path(__file__).parent/'composite/payload.json').read_text())
    semimap={r[3]:r for r in semi['rows'][1:]}
    rows=[header];red=[];metrics=collections.Counter();quality_by_symbol={}
    colors=json.loads((CONFIG/'group_colors.json').read_text());assert len(set(colors.values()))==25
    for ri,c in enumerate(selected,2):
        symbol=c['symbol'];ref=c['reference'];q=quotes[symbol];assert q['f12'].replace('_','.')==symbol and q['f13'] in (105,106,107)
        r=list(ref) if ref else ['未取得参考档案']*56
        r[:7]=[c['name'],c['sector'],c['group_name'],symbol,c['description'],round(c['cap']/1e8,4),q.get('f115') if numeric(q.get('f115')) and q['f115']!=0 else '未返回有效TTM']
        issues=[]
        pe=r[6]
        if not numeric(pe):issues.append('TTM缺失，未以普通PE补数');red.append(f'G{ri}')
        elif pe<0:issues.append('负PE；不按正盈利估值解释');red.append(f'G{ri}')
        else:metrics['positive_ttm']+=1
        ec=q.get('f20');gap=ec/c['cap']-1 if numeric(ec) else None
        cross=numeric(ec) and (ec>=3e10)!=(c['cap']>=3e10)
        if cross:issues.append('两源市值跨越300亿美元门槛；本次按Nasdaq入选，待复核')
        if numeric(gap) and abs(gap)>.05:issues.append('两源市值相差超过5%；时点/股本口径待复核')
        if abs(c['cap']/3e10-1)<.02:issues.append('距门槛不足2%，价格变化可能改变入选')
        if issues and (cross or numeric(gap) and abs(gap)>.05 or abs(c['cap']/3e10-1)<.02):red.extend([f'F{ri}',f'BL{ri}']);metrics['cap_flags']+=1
        # Do not revive the reference workbook's market-cap/price-derived forecast profits.
        for j in (7,8,9,10,12,13,14,19,20,21):r[j]='未取得同口径预测/实际数据；不折算'
        for j in (11,12,13,14):
            year=2025+j-11
            segment=re.search(str(year)+r'：([^；]+)',str(ref[49])) if ref else None
            if ref and numeric(ref[j]) and segment and '实际值' in segment[1]:r[j]=ref[j]
            elif j==11:r[j]='未取得可确认的实际档案值'
        if ref:
            for j in (18,19,20,21):
                previous=r[50] if j==18 else r[j-8]
                current=r[j-7]
                r[j]=pct(ref[j]) if numeric(previous) and numeric(current) and previous>0 and numeric(ref[j]) else '实际/预测口径不齐，不混算'
        for j in range(24,33):r[j]=pct(r[j])
        for j in (15,16,17):r[j]=pct(r[j])
        r[22]=bjt(q.get('f124'))[:10];r[23]=f'{q["f3"]:.2f}%' if numeric(q.get('f3')) else '未取得'
        r[37]=c['group'];r[38]=c['classification'];r[40]=q.get('f2') if numeric(q.get('f2')) else '未取得'
        r[41]=f'市值：Nasdaq美股筛选快照，抓取{captured}北京时间，源asOf为空；价格/PE：东财同次美股报价，时间{bjt(q.get("f124"))}；历史涨幅沿用10/27参考档案；仅取美股证券，不跨市场换算。'
        r[42]=q['url'];r[43]='；'.join(issues) or '源直接返回TTM；不等于独立核算盈利分母。财报窗口可能出现更新批次差。'
        r[49]='财务沿用参考表2026-10-28档案，原表注明亿美元，未逐份重新核验；仅保留明确标记实际值的利润。预测净利润及其PE不采用原表市值÷股价推算股数的方法。原方法记录：'+str(ref[49] if ref else '无档案')
        if symbol in semimap:
            sr=semimap[symbol]
            for a,b in ((11,11),(12,12),(13,13),(14,14),(50,52)):r[a]=sr[b]
            r[49]='半导体汇总已核验的财务档案；'+str(sr[53])+'；保留原币单位，不跨市场换汇；本次未重抓财报。'
        r[55]=str(r[55])+'；本次只沿用参考档案，未重新抓取分部信息。'
        eps=[]
        for year in (2026,2027,2028):
            m=re.search(str(year)+r'：估算EPS=([-+\d.]+)',str(ref[49])) if ref else None
            eps.append(float(m[1]) if m else '参考档案未提供')
        rr=r[:7]+[c['rank'],c['reason']]+r[7:]+[captured,bjt(q.get('f124')),nasdaq['url'],round(ec/1e8,4) if numeric(ec) else '未取得',pct(gap),'；'.join(issues) or '本次检查未触发异常；不是正确性保证','2026-10-27' if ref else '未取得','2026-10-28参考档案；未重抓' if ref else '未取得',REFERENCE,*eps,c['classification']+'；Nasdaq池内按市值降序；同公司已知重复股类只保留一条','仅美股上市证券；无其他国家市场补数']
        rr=[clean(v) for v in rr];assert len(rr)==72
        rows.append(rr)
        # All inherited financial/history figures remain visibly archival and unverified this run.
        for j in [*range(9,24),*range(26,39),52,67,68,69]:
            if numeric(rr[j]) or isinstance(rr[j],str) and (rr[j].endswith('%') or '未取得' in rr[j] or '不混算' in rr[j]):red.append(f'{col(j)}{ri}')
        if '待官方核验' in c['classification']:red.extend([f'B{ri}',f'C{ri}',f'AO{ri}']);metrics['classification_provisional']+=1
        if not ref:metrics['new']+=1
        quality_by_symbol[symbol]=issues
    from forecast_fields import apply_rows
    rows,forecast_red=apply_rows(rows,'selection')
    red.extend(f'{col(j)}{i+1}' for i,j in forecast_red)
    from quarter_fields import extend_selection
    rows,quarter_red=extend_selection(rows)
    red.extend(f'{col(j)}{i}' for i,j in quarter_red)
    from annual_profit_fields import apply_selection
    rows,annual_red,annual_black=apply_selection(rows)
    black_annual={f'{col(j)}{i}' for i,j in annual_black}
    red=[cell for cell in red if cell not in black_annual]
    red.extend(f'{col(j)}{i}' for i,j in annual_red)
    start=len(rows)+4
    summary=[['筛选规则与分类覆盖'],['规则','范围/口径','结果'],['市值门槛','300亿美元 = 30,000,000,000 USD；纳入所有达到门槛且通过证券类型筛选的公司',sum(c['cap']>=3e10 for c in selected)],['类目前二','每个GICS二级按Nasdaq美股市值排序，至少保留前2家；低于门槛也补入',len([c for c in selected if c['cap']<3e10])],['筛选范围',f'Nasdaq返回{candidate["nasdaq_universe_count"]}条证券；排除优先股、票据、权证及已知重复股类；GICS使用参考表及公开映射',len(selected)],['股票去重','例如Alphabet仅保留GOOGL、伯克希尔仅保留BRK.B；ITUB保留其美股发行人代表证券','不将两个股类计作两家公司'],['快照边界','市值来自Nasdaq抓取快照（源asOf未提供），PE/价格来自东财逐股时间戳；本表不是同一毫秒全市场快照',captured],['继承资料','历史涨幅基准10/27；财务与分部来自10/28档案；已撤销不可靠的预测利润折算','继承/未核验字段红字'],['颜色','每个GICS二级一个底色；同类连续排列；类内市值从大到小；所有行29px','25个二级颜色'],['一级','二级','二级代码','入选家数','达门槛家数','补足家数','市值第1名','第1名市值(亿美元)','市值第2名','第2名市值(亿美元)','分类颜色']]
    for g in dict.fromkeys(c['group'] for c in selected):
        cc=[c for c in selected if c['group']==g];assert len(cc)>=2 and [c['rank'] for c in cc[:2]]==[1,2]
        summary.append([*GROUPS[g],g,len(cc),sum(c['cap']>=3e10 for c in cc),sum(c['cap']<3e10 for c in cc),cc[0]['symbol'],round(cc[0]['cap']/1e8,4),cc[1]['symbol'],round(cc[1]['cap']/1e8,4),colors[GROUPS[g][1]]])
    excluded_start=start+len(summary)+3
    removed=[(s,refs[s][0]) for s in refs if s not in {c['symbol'] for c in selected}]
    extra=[['与参考表的变化/边界公司'],['代码','公司','处理','Nasdaq市值(亿美元)','说明']]
    for c in selected:
        if not c['reference']:extra.append([c['symbol'],c['name'],'新增',round(c['cap']/1e8,4),c['reason']])
    cmap={c['symbol']:c for c in candidate['candidates']}
    for s,name in removed:extra.append([s,name,'本次移出',round(cmap[s]['cap']/1e8,4) if s in cmap else '未取得','低于300亿美元且不在本二级前2名' if s in cmap else '当前证券/分类待核验'])
    for c in candidate['candidates']:
        if c['symbol'] in {s for s,_ in removed} or c['cap']>=3e10:continue
        q=c['quote'];ec=q.get('f20')
        if numeric(ec) and ec>=3e10:extra.append([c['symbol'],c['name'],'主源未达门槛，东财达门槛',round(c['cap']/1e8,4),'按固定Nasdaq主源筛选；两源阈值冲突，待复核；东财市值'+str(round(ec/1e8,4))+'亿美元'])
    final_end=excluded_start+len(extra)-1
    assert not candidate['unmapped']
    assert len({c['symbol'] for c in selected})==len(selected)
    assert all(len(r)==len(rows[0]) for r in rows)
    assert all('\n' not in str(v) and '\r' not in str(v) for r in rows+summary+extra for v in r)
    result={'title':'GICS_300亿美元_二级Top2_1029','rows':rows,'selected':[dict((k,v) for k,v in c.items() if k not in ('reference','quote')) for c in selected],'summary_start':start,'summary':summary,'extra_start':excluded_start,'extra':extra,'red_cells':sorted(set(red)),'colors':colors,'last_row':final_end,'metrics':dict(metrics,stocks=len(selected),groups=25,sectors=len({c['sector'] for c in selected}),threshold=sum(c['cap']>=3e10 for c in selected),supplements=sum(c['cap']<3e10 for c in selected),removed=len(removed))}
    (OUT/'sheet_payload.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['metrics'],ensure_ascii=False));print('rows',final_end,'columns',len(header),'red_cells',len(result['red_cells']))

if __name__=='__main__':main()
