import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('feishu_helper', ROOT/'feishu_client.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

def connect():
    cfg = {}
    local_path=ROOT/'local_config.json'
    local=json.loads(local_path.read_text()) if local_path.exists() else {}
    env_path=Path(os.environ.get('FEISHU_ENV_FILE',local.get('feishu_env_file',str(ROOT.parent/'.env'))))
    for line in (env_path.read_text().splitlines() if env_path.exists() else []):
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            cfg[k.strip()] = v.strip().strip('\"\'')
    for key in ('FEISHU_APP_ID','FEISHU_APP_SECRET'):
        cfg[key]=os.environ.get(key,cfg.get(key,''))
        if not cfg[key]:raise ValueError('Missing configuration: '+key)
    token = helper.request('POST', 'auth/v3/tenant_access_token/internal', body={'app_id': cfg['FEISHU_APP_ID'], 'app_secret': cfg['FEISHU_APP_SECRET']})['tenant_access_token']
    node = helper.request('GET', 'wiki/v2/spaces/get_node?token=OCS4wHZRvik8Wckwc1ecHjnhnbI', token)['data']['node']
    assert node['obj_type'] == 'sheet'
    return token, node['obj_token']

def main():
    token, ss = connect()
    if '--publish' in sys.argv:
        publish(token, ss)
        return
    meta = helper.request('GET', f'sheets/v3/spreadsheets/{ss}/sheets/query', token)
    (ROOT/'feishu_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta['data'], ensure_ascii=False))
    for sheet in meta['data']['sheets']:
        if sheet['title'] == 'AI整理' or sheet['sheet_id'] == 'EOZj3I':
            sid = sheet['sheet_id']
            data = helper.request('GET', f'sheets/v2/spreadsheets/{ss}/values/{sid}!A1:Z60', token)
            (ROOT/f'before_{sid}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(sid, json.dumps(data['data'], ensure_ascii=False))

def publish(token, ss):
    sid = 'EOZj3I'
    base = f'sheets/v2/spreadsheets/{ss}'
    rows = json.loads((ROOT/'analysis_rows.json').read_text())
    rows = [r + ['']*(10-len(r)) for r in rows]
    assert len(rows) == 30 and all(len(r) == 10 for r in rows)
    address = f'{sid}!A1:J30'
    existing = helper.request('GET', f'{base}/values/{address}', token)['data']['valueRange']['values']
    cell_text = lambda v: ''.join(x.get('text','') for x in v) if isinstance(v,list) else (v if v is not None else '')
    normalize = lambda rs: [[cell_text(v) for v in (r+['']*10)[:10]] for r in rs]
    if '--resume-format' not in sys.argv:
        assert not any(v not in (None, '') for r in existing for v in r), 'Target is no longer blank; stop to avoid overwriting changes.'
        helper.request('PUT', f'{base}/values', token, {'valueRange': {'range': address, 'values': rows}})
        print('Wrote 10 project rows and selection guidance.', flush=True)
    else:
        assert normalize(existing) == rows, 'Existing content differs; stop.'
    got = helper.request('GET', f'{base}/values/{address}', token)['data']['valueRange']['values']
    assert normalize(got) == rows, 'Read-back mismatch'
    (ROOT/'after_values.json').write_text(json.dumps(got, ensure_ascii=False, indent=2))
    print('Verified all 300 cells by API read-back.', flush=True)
    styles = [
        {'ranges':[address], 'style':{'wordWrap': True}},
        {'ranges':[f'{sid}!A1:J1',f'{sid}!A5:J5',f'{sid}!A17:J17',f'{sid}!A24:J24'], 'style':{'backColor':'#17365D','foreColor':'#FFFFFF','font':{'bold':True}}},
        {'ranges':[f'{sid}!A2:J3'], 'style':{'backColor':'#EAF2F8'}},
        {'ranges':[f'{sid}!A{r}:J{r}' for r in [7,9,13,15]], 'style':{'backColor':'#F2F6FA'}},
        {'ranges':[f'{sid}!A11:J11'], 'style':{'backColor':'#FFF2CC'}},
        {'ranges':[f'{sid}!A18:B22',f'{sid}!A25:B30'], 'style':{'font':{'bold':True},'backColor':'#EAF2F8'}},
    ]
    if '--resume-dimensions' not in sys.argv:
        helper.request('PUT', f'{base}/styles_batch_update', token, {'data':styles})
        for a in ['A1:J1','A2:J2','A3:J3','A17:J17','A24:J24'] + [x for r in list(range(18,23))+list(range(25,31)) for x in [f'A{r}:B{r}',f'C{r}:J{r}']]:
            helper.request('POST', f'{base}/merge_cells', token, {'range':f'{sid}!{a}', 'mergeType':'MERGE_ALL'})
    for i, width in enumerate([55,235,150,210,340,310,330,450,300,365]):
        helper.request('PUT', f'{base}/dimension_range', token, {'dimension':{'sheetId':sid,'majorDimension':'COLUMNS','startIndex':i+1,'endIndex':i+2},'dimensionProperties':{'fixedSize':width}})
    for start,end,height in [(0,1,36),(1,3,42),(4,5,36),(5,15,172),(16,17,32),(17,22,48),(23,24,32),(24,30,48)]:
        helper.request('PUT', f'{base}/dimension_range', token, {'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':start+1,'endIndex':end+1},'dimensionProperties':{'fixedSize':height}})
    helper.request('POST', f'{base}/sheets_batch_update', token, {'requests':[{'updateSheet':{'properties':{'sheetId':sid,'gridProperties':{'frozenRowCount':5}}}}]})
    final = helper.request('GET', f'{base}/values/{address}', token)['data']['valueRange']['values']
    assert normalize(final) == rows, 'Final values changed after formatting'
    original = helper.request('GET', f'{base}/values/5ded4b!A1:U35', token)['data']['valueRange']['values']
    saved = json.loads((ROOT/'original.json').read_text())['data']['valueRange']['values']
    assert original == saved, 'Original sheet differs'
    print('Formatting complete; final values verified; original records unchanged.', flush=True)

if __name__ == '__main__':
    main()
