"""Reorder complete stock rows without changing their values or membership."""
import collections,copy,json,re
from decimal import Decimal
from write_feishu import connect,helper
from selection_sources import OUT
from publish_selection_sheet import norm,compressed_ranges
from valuation_policy import col

def main():
    path=OUT/'sheet_payload.json';p=json.loads(path.read_text());old=copy.deepcopy(p)
    statepath=OUT/'online_state.json';state=json.loads(statepath.read_text());sid=state['sheet_id']
    token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
    def read(a,w):return norm(helper.request('GET',base+f'/values/{sid}!{a}?valueRenderOption=UnformattedValue',token)['data']['valueRange']['values'],w)
    width=len(p["rows"][0]);last_col=col(width-1)
    before=read(f'A1:{last_col}464',width)
    assert before==p['rows'],'Online data changed; reconcile before sorting'
    (OUT/'before_hierarchical_sort.json').write_text(json.dumps(before,ensure_ascii=False))
    sectors=collections.defaultdict(Decimal);groups=collections.defaultdict(Decimal)
    for row in before[1:]:
        cap=Decimal(str(row[5]));sectors[row[1]]+=cap;groups[(row[1],row[2])]+=cap
    ordered=sorted(enumerate(before[1:],2),key=lambda item:(-sectors[item[1][1]],item[1][1],-groups[(item[1][1],item[1][2])],item[1][2],-Decimal(str(item[1][5])),item[1][3]))
    p['rows']=[before[0]]+[row for _,row in ordered]
    new_index={old_i:new_i for new_i,(old_i,row) in enumerate(ordered,2)}
    p['red_cells']=[re.sub(r'\d+$',lambda m:str(new_index[int(m[0])]),cell) for cell in p['red_cells']]
    by_symbol={c['symbol']:c for c in p['selected']};p['selected']=[by_symbol[row[3]] for row in p['rows'][1:]]
    group_order=list(dict.fromkeys((row[1],row[2]) for row in p['rows'][1:]))
    summary_by_group={(r[0],r[1]):r for r in p['summary'][10:]}
    p['summary']=p['summary'][:10]+[summary_by_group[g] for g in group_order]
    p['summary'][8]=['颜色与排序','按本表入选股票市值求和：一级合计降序 → 一级内二级合计降序 → 二级内个股市值降序；每个二级保持原底色；所有行29px','合计以F列Nasdaq市值为准']
    assert {r[3]:r for r in before[1:]}=={r[3]:r for r in p['rows'][1:]}
    main_patches=[]
    for start in range(1,len(p['rows']),70):
        part=p['rows'][start:start+70];main_patches.append({'range':f'{sid}!A{start+1}:{last_col}{start+len(part)}','values':part})
    summary=[r+['']*(11-len(r)) for r in p['summary']]
    patches=main_patches+[{'range':f'{sid}!A468:K502','values':summary}]
    for patch in patches:helper.request('PUT',base+'/values',token,{'valueRange':patch})
    styles=[{'ranges':[f'{sid}!A2:{last_col}464'],'style':{'foreColor':'#202124'}},{'ranges':[f'{sid}!H2:I464'],'style':{'font':{'bold':False}}}]
    for group in group_order:
        indices=[i for i,r in enumerate(p['rows'][1:],2) if (r[1],r[2])==group]
        assert indices==list(range(min(indices),max(indices)+1))
        styles.append({'ranges':[f'{sid}!A{min(indices)}:{last_col}{max(indices)}'],'style':{'backColor':p['colors'][group[1]]}})
        styles.append({'ranges':[f'{sid}!H{min(indices)}:I{min(indices)+1}'],'style':{'font':{'bold':True}}})
    for i,r in enumerate(p['summary'][10:],478):styles.append({'ranges':[f'{sid}!A{i}:K{i}'],'style':{'backColor':p['colors'][r[1]]}})
    helper.request('PUT',base+'/styles_batch_update',token,{'data':styles})
    red=compressed_ranges(p['red_cells'],sid)
    for start in range(0,len(red),100):helper.request('PUT',base+'/styles_batch_update',token,{'data':[{'ranges':red[start:start+100],'style':{'foreColor':'#C00000'}}]})
    helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':1,'endIndex':600},'dimensionProperties':{'fixedSize':29}})
    after=read(f'A1:{last_col}464',width);assert after==p['rows']
    assert read('A468:K502',11)==summary
    assert read(f'A{p["extra_start"]}:E{p["last_row"]}',5)==[r+['']*(5-len(r)) for r in p['extra']]
    sector_order=list(dict.fromkeys(r[1] for r in after[1:]));assert [sectors[g] for g in sector_order]==sorted(sectors.values(),reverse=True)
    for sector in sector_order:
        gs=[g for g in group_order if g[0]==sector];assert [groups[g] for g in gs]==sorted([groups[g] for g in gs],reverse=True)
    for group in group_order:
        caps=[r[5] for r in after[1:] if (r[1],r[2])==group];assert caps==sorted(caps,reverse=True)
    path.write_text(json.dumps(p,ensure_ascii=False,indent=2))
    ranking=[{'sector':s,'cap_100m_usd':float(sectors[s])} for s in sector_order]
    state.update(sort_order='一级入选市值合计降序/一级内二级入选市值合计降序/二级内个股市值降序',sort_verified=True,sector_cap_ranking=ranking)
    statepath.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    print(json.dumps({'verified':True,'stocks':len(after)-1,'sector_order':ranking,'first_groups':group_order[:6],'all_stock_values_unchanged':True,'red_cells_remapped':len(p['red_cells']),'row_height_px':29},ensure_ascii=False))

if __name__=='__main__':main()
