import collections,json,math
from write_feishu import ROOT,helper,connect
from quarter_fields import OUT,KEYS,MAIN_COLUMNS,extend_selection,flat
from valuation_policy import col
from publish_selection_sheet import compressed_ranges

def norm(rows,width):return [([flat(v) for v in r]+['']*width)[:width] for r in rows]
def eq(a,b):return math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-8) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else a==b
def main():
    p=json.loads((OUT/'payload.json').read_text());token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
    def read(sid,address,width):return norm(helper.request('GET',base+f'/values/{sid}!{address}?valueRenderOption=Formula',token)['data']['valueRange']['values'],width)
    sel=read('1phTpK','A1:BT464',72);old=norm(json.loads((OUT/'selection_before.json').read_text())['data']['valueRange']['values'],72);assert sel==old,'Live base changed; reconcile'
    mainrows=read('477joI','A1:DP25',120);oldmain=norm(json.loads((OUT/'main_before.json').read_text())['data']['valueRange']['values'],120);assert mainrows==oldmain,'Main changed; reconcile'
    extended,red=extend_selection(sel,p);metadata=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets'];sheet=next(s for s in metadata if s['sheet_id']=='1phTpK')
    n=sheet['grid_properties']['column_count']
    if n<90:helper.request('POST',base+'/dimension_range',token,{'dimension':{'sheetId':'1phTpK','majorDimension':'COLUMNS','length':90-n}})
    tail=read('1phTpK','BU1:CL464',18)
    assert all(v=='' for r in tail for v in r),'New column area occupied; inspect before overwriting'
    patches=[]
    for start in range(0,len(extended),65):
        part=[row[72:] for row in extended[start:start+65]];patches.append({'range':f'1phTpK!BU{start+1}:CL{start+len(part)}','values':part})
    main_after=[r[:] for r in mainrows];main_red=[];main_black=[]
    for j,head in zip(MAIN_COLUMNS,p['headers'][:13]):main_after[0][j]=head
    for i,row in enumerate(main_after[1:],1):
        rec=p['records'][row[3]]
        for offset,j in enumerate(MAIN_COLUMNS):
            if KEYS[offset]=='locked_Q3':continue
            r=rec['quarters'][KEYS[offset]]
            row[j]=rec['values'][offset]
            (main_black if r['status']=='actual' else main_red).append(f'{col(j)}{i+1}')
        row[83]=rec['values'][14]
        row[118]=str(row[118]).split('【季度模块】')[0]+'；【季度模块】'+'；'.join(str(x) for x in rec['values'][13:])
    for i,(before,after) in enumerate(zip(mainrows,main_after),1):
        for j,(a,b) in enumerate(zip(before,after)):
            if a!=b:patches.append({'range':f'477joI!{col(j)}{i}:{col(j)}{i}','values':[[b]]})
    assert all('\n' not in str(v) and '\r' not in str(v) for part in patches for r in part['values'] for v in r)
    for start in range(0,len(patches),40):helper.request('POST',base+'/values_batch_update',token,{'valueRanges':patches[start:start+40]})
    payload_path=ROOT/'selection/sheet_payload.json';saved=json.loads(payload_path.read_text());colors=saved['colors']
    styles=[{'ranges':['1phTpK!BU1:CL1'],'style':{'backColor':'#17365D','foreColor':'#FFFFFF','font':{'bold':True}}},{'ranges':['1phTpK!BU2:CL464'],'style':{'foreColor':'#202124'}}]
    groups=collections.defaultdict(list)
    for i,row in enumerate(sel[1:],2):groups[row[2]].append(i)
    for name,indices in groups.items():styles.append({'ranges':[f'1phTpK!BU{min(indices)}:CL{max(indices)}'],'style':{'backColor':colors[name]}})
    helper.request('PUT',base+'/styles_batch_update',token,{'data':styles})
    red_cells=[f'{col(j)}{i}' for i,j in red]
    ranges=compressed_ranges(red_cells,'1phTpK')+compressed_ranges(main_red,'477joI')
    for start in range(0,len(ranges),100):helper.request('PUT',base+'/styles_batch_update',token,{'data':[{'ranges':ranges[start:start+100],'style':{'foreColor':'#C00000'}}]})
    if main_black:helper.request('PUT',base+'/styles_batch_update',token,{'data':[{'ranges':compressed_ranges(main_black,'477joI'),'style':{'foreColor':'#202124'}}]})
    for a,b,w in [(73,85,225),(86,87,460),(88,88,330),(89,90,500)]:helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':'1phTpK','majorDimension':'COLUMNS','startIndex':a,'endIndex':b},'dimensionProperties':{'fixedSize':w}})
    for sid,count in [('1phTpK',600),('477joI',2888)]:helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':1,'endIndex':count},'dimensionProperties':{'fixedSize':29}})
    got=read('1phTpK','A1:CL464',90)
    assert len(got)==len(extended)
    for i,(a,b) in enumerate(zip(got,extended),1):
        for j,(x,y) in enumerate(zip(a,b)):assert eq(x,y),('selection',i,col(j),x,y)
    gotmain=read('477joI','A1:DP25',120)
    for i,(a,b) in enumerate(zip(gotmain,main_after),1):
        for j,(x,y) in enumerate(zip(a,b)):assert eq(x,y),('main',i,col(j),x,y)
    saved['rows']=extended;saved['red_cells']=sorted(set(saved.get('red_cells',[]))|set(red_cells));saved['quarter_module']={'range':'BU:CL','stats':p['stats'],'stocks':463};payload_path.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
    mainpath=ROOT/'composite/payload.json';msaved=json.loads(mainpath.read_text())
    for i,(a,b) in enumerate(zip(mainrows,main_after)):
        for j,(x,y) in enumerate(zip(a,b)):
            if x!=y:msaved['rows'][i][j]=y
    msaved['red_cells']=sorted((set(msaved.get('red_cells',[]))|set(main_red))-set(main_black));msaved['black_cells']=sorted((set(msaved.get('black_cells',[]))|set(main_black))-set(main_red));mainpath.write_text(json.dumps(msaved,ensure_ascii=False,indent=2))
    statepath=ROOT/'selection/online_state.json';state=json.loads(statepath.read_text());state.update(columns=90,quarter_module_verified=True,quarter_range='BU:CL',quarter_stats=p['stats']);statepath.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    result={'verified':True,'stocks':463,'range':'BU:CL','profit_range':'BU:CG','stats':p['stats'],'base_columns_unchanged':True,'row_height_px':29,'main_quarters_patched':len(main_red)+len(main_black),'url':'https://my.feishu.cn/wiki/OCS4wHZRvik8Wckwc1ecHjnhnbI?sheet=1phTpK'}
    (OUT/'published.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
