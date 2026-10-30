import collections,json,re,sys
from write_feishu import connect,helper
from selection_sources import OUT
from build_selection_sheet import col,REFERENCE

def flat(v):return ''.join(x.get('text','') for x in v) if isinstance(v,list) else '' if v is None else v
def norm(rows,width):return [([flat(x) for x in r]+['']*width)[:width] for r in rows]
def compressed_ranges(cells,sid):
    grouped=collections.defaultdict(list)
    for cell in cells:
        m=re.fullmatch(r'([A-Z]+)(\d+)',cell);grouped[m[1]].append(int(m[2]))
    result=[]
    for c,indices in grouped.items():
        indices=sorted(set(indices));start=last=indices[0]
        for i in indices[1:]:
            if i!=last+1:result.append(f'{sid}!{c}{start}:{c}{last}');start=i
            last=i
        result.append(f'{sid}!{c}{start}:{c}{last}')
    return result

def main():
    p=json.loads((OUT/'sheet_payload.json').read_text());token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}';statefile=OUT/'online_state.json'
    sheets=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets']
    if statefile.exists():
        state=json.loads(statefile.read_text());sid=state['sheet_id'];assert any(x['sheet_id']==sid and x['title']==p['title'] for x in sheets)
    else:
        assert not any(x['title']==p['title'] for x in sheets),'Title already exists; do not overwrite another sheet'
        helper.request('POST',base+'/sheets_batch_update',token,{'requests':[{'addSheet':{'properties':{'title':p['title']}}}]})
        sheets=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets'];sid=next(x['sheet_id'] for x in sheets if x['title']==p['title'])
        state={'sheet_id':sid,'title':p['title'],'stage':'created'};statefile.write_text(json.dumps(state,ensure_ascii=False))
    # Set dimensions before writing any formulas/values to avoid reference shifting.
    current=next(s for s in sheets if s['sheet_id']==sid)['grid_properties']
    for major,key,target in [('ROWS','row_count',600),('COLUMNS','column_count',72)]:
        if current[key]<target:helper.request('POST',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':major,'length':target-current[key]}})
    helper.request('POST',base+'/sheets_batch_update',token,{'requests':[{'updateSheet':{'properties':{'sheetId':sid,'frozenRowCount':1,'frozenColCount':4}}}]})
    patches=[]
    for start in range(0,len(p['rows']),70):
        part=p['rows'][start:start+70];patches.append({'range':f'{sid}!A{start+1}:BT{start+len(part)}','values':part})
    for name,start in [('summary',p['summary_start']),('extra',p['extra_start'])]:
        width=max(map(len,p[name]));patches.append({'range':f'{sid}!A{start}:{col(width-1)}{start+len(p[name])-1}','values':[r+['']*(width-len(r)) for r in p[name]]})
    if '--resume-format' not in sys.argv:
        for patch in patches:
            helper.request('PUT',base+'/values',token,{'valueRange':patch});print('wrote',patch['range'],flush=True)
    end=len(p['rows']);styles=[{'ranges':[f'{sid}!A1:BT{p["last_row"]}'],'style':{'foreColor':'#202124','vAlign':0,'hAlign':0}}]
    groups=collections.defaultdict(list)
    for i,c in enumerate(p['selected'],2):groups[c['group_name']].append(i)
    for group,indices in groups.items():
        assert indices==list(range(min(indices),max(indices)+1))
        styles.append({'ranges':[f'{sid}!A{min(indices)}:BT{max(indices)}'],'style':{'backColor':p['colors'][group]}})
    styles.append({'ranges':[f'{sid}!A1:BT1',f'{sid}!A{p["summary_start"]}:K{p["summary_start"]+1}',f'{sid}!A{p["summary_start"]+9}:K{p["summary_start"]+9}',f'{sid}!A{p["extra_start"]}:K{p["extra_start"]+1}'],'style':{'foreColor':'#FFFFFF','backColor':'#17365D','font':{'bold':True}}})
    for offset,row in enumerate(p['summary'][10:],p['summary_start']+10):styles.append({'ranges':[f'{sid}!A{offset}:K{offset}'],'style':{'backColor':row[10]}})
    helper.request('PUT',base+'/styles_batch_update',token,{'data':styles})
    red=compressed_ranges(p['red_cells'],sid)
    for offset in range(0,len(red),100):helper.request('PUT',base+'/styles_batch_update',token,{'data':[{'ranges':red[offset:offset+100],'style':{'foreColor':'#C00000'}}]})
    for group in groups:
        indices=groups[group]
        top=min(indices)
        helper.request('PUT',base+'/styles_batch_update',token,{'data':[{'ranges':[f'{sid}!H{top}:I{top+1}'],'style':{'font':{'bold':True}}}]})
    widths=[165]*72
    for j,w in {0:270,1:120,2:220,3:90,4:360,5:170,6:150,7:115,8:270,12:300,24:140,35:410,36:410,37:410,38:410,39:125,40:255,41:220,43:460,44:360,45:430,46:360,51:520,55:400,56:360,57:420,58:200,59:200,60:370,63:420,64:160,65:260,66:400,70:410,71:260}.items():widths[j]=w
    for i,w in enumerate(widths,1):helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'COLUMNS','startIndex':i,'endIndex':i},'dimensionProperties':{'fixedSize':w}})
    helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':1,'endIndex':600},'dimensionProperties':{'fixedSize':29}})
    print('formatting complete; verifying all written ranges',flush=True)
    for patch in patches:
        got=helper.request('GET',base+'/values/'+patch['range']+'?valueRenderOption=UnformattedValue',token)['data']['valueRange']['values'];width=len(patch['values'][0])
        assert norm(got,width)==patch['values'],patch['range']
    meta=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets'];grid=next(s['grid_properties'] for s in meta if s['sheet_id']==sid)
    assert grid['frozen_column_count']==4 and grid['frozen_row_count']==1
    # Confirm the reference data was not changed while creating the new sheet.
    reference=helper.request('GET','sheets/v2/spreadsheets/FGgWsfYBJhwJActVv0tcmF0WnOc/values/K3baGL!A1:BT500?valueRenderOption=UnformattedValue',token)['data']['valueRange']['values']
    saved=json.loads((OUT/'reference_values.json').read_text())['data']['valueRange']['values'];assert norm(reference,72)==norm(saved,72)
    state.update(stage='verified',url=f'https://my.feishu.cn/wiki/OCS4wHZRvik8Wckwc1ecHjnhnbI?sheet={sid}',metrics=p['metrics'],row_height_px=29,last_row=p['last_row'],columns=72,all_written_cells_readback_verified=True,reference_unchanged=True,group_colors=p['colors'])
    statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2));print(json.dumps(state,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
