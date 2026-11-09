"""Patch growth and necessary historical inputs; verify the entire table after writing."""
import json,math
from growth_fields import OUT,ROOT,apply_selection
from quarter_fields import flat
from write_feishu import connect,helper
from publish_selection_sheet import compressed_ranges
from valuation_policy import col
SID='1phTpK';WIDTH=90

def norm(rows):return [([flat(v) for v in r]+['']*WIDTH)[:WIDTH] for r in rows]
def same(a,b):return math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-8) if isinstance(a,(float,int)) and isinstance(b,(float,int)) else a==b

def main():
    data=json.loads((OUT/'records.json').read_text());before=norm(json.loads((OUT/'before.json').read_text())['data']['valueRange']['values'])
    expected,red,black=apply_selection(before,data['records']);assert len(expected)==464
    assert all('\n' not in str(v) and '\r' not in str(v) for row in expected for v in row[20:24]+[row[55]])
    assert all(a==b for old,new in zip(before,expected) for j,(a,b) in enumerate(zip(old,new)) if j not in (13,20,21,22,23,47,52,53,54,55))
    t,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
    def read():return norm(helper.request('GET',base+f'/values/{SID}!A1:CL464?valueRenderOption=Formula',t)['data']['valueRange']['values'])
    live=read();assert live==before,'Online table changed; reconcile before write'
    patches=[]
    for start in range(0,len(expected),70):
        part=expected[start:start+70]
        patches.extend([{'range':f'{SID}!U{start+1}:X{start+len(part)}','values':[r[20:24] for r in part]},{'range':f'{SID}!BD{start+1}:BD{start+len(part)}','values':[[r[55]] for r in part]}])
    for i,(old,new) in enumerate(zip(before,expected),1):
        for j in (13,47,52,53,54):
            if old[j]!=new[j]:patches.append({'range':f'{SID}!{col(j)}{i}:{col(j)}{i}','values':[[new[j]]]})
    batch=[];size=0;completed=0
    for patch in patches+[None]:
        count=len(json.dumps(patch,ensure_ascii=False).encode()) if patch else 0
        if batch and (patch is None or size+count>700000 or len(batch)>=40):
            helper.request('POST',base+'/values_batch_update',t,{'valueRanges':batch})
            completed+=len(batch);print('Wrote patches',completed,'/',len(patches),flush=True);batch=[];size=0
        if patch:batch.append(patch);size+=count
    for cells,color in [(red,'#C00000'),(black,'#202124')]:
        ranges=compressed_ranges([f'{col(j)}{i}' for i,j in cells],SID)
        for start in range(0,len(ranges),100):helper.request('PUT',base+'/styles_batch_update',t,{'data':[{'ranges':ranges[start:start+100],'style':{'foreColor':color}}]})
    helper.request('PUT',base+'/dimension_range',t,{'dimension':{'sheetId':SID,'majorDimension':'ROWS','startIndex':1,'endIndex':600},'dimensionProperties':{'fixedSize':29}})
    got=read();assert len(got)==len(expected)
    for i,(actual,want) in enumerate(zip(got,expected),1):
        for j,(a,b) in enumerate(zip(actual,want)):assert same(a,b),(i,col(j),a,b)
    path=ROOT/'selection/sheet_payload.json';saved=json.loads(path.read_text())
    assert [r[3] for r in saved['rows'][1:]]==[r[3] for r in expected[1:]]
    saved['rows']=expected
    changed={f'{col(j)}{i}' for i in range(2,465) for j in (20,21,22,23)}
    saved['red_cells']=sorted((set(saved.get('red_cells',[]))-changed-{f'{col(j)}{i}' for i,j in black})|{f'{col(j)}{i}' for i,j in red})
    saved['growth_module']={'asof':data['asof'],'range':'U:X','stats':data['stats']};path.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
    report={k:v for k,v in data.items() if k!='records'};report.update(verified=True,stocks=463,range='U:X',notes='BD',outside_growth_and_historical_inputs_unchanged=True,row_height_px=29)
    (OUT/'published.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
