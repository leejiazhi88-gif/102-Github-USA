import json,re,datetime
from pathlib import Path
from write_feishu import connect,helper,ROOT

OUT=ROOT/'composite/pe_ttm_probe'
bench={'SKHY':{'name':'SK海力士','price':164.7,'eps':6.85,'pe':24.05,'time':'用户截图：10/29 20:16 北京时间'},'TSM':{'name':'台积电','price':439.51,'eps':15.35,'pe':28.64,'time':'用户截图：10/29 20:50 北京时间'},'ASML':{'name':'阿斯麦','price':1662.85,'eps':40.41,'pe':41.15,'time':'用户截图：10/29 20:51 北京时间'}}
header=['美股代码','公司','来源','原字段/指标','PE原值','EPS原值或说明','对应股价USD','价格时点/时段','数据取得时间','截图TTM基准','PE相对截图差异','验证结论','来源链接','后续处理']
rows=[['PE TTM来源实测对照｜2026-10-29｜只取美股证券'],['用户已确认基准为长桥证券App。三张最新截图作为首次验收基准；后续优先长桥官方API，接口数值不按多数票、平均值或最接近截图原则选取。'],header]
em=json.loads((OUT/'em_list_us.json').read_text())
emmap={d['f12']:d for d in em['data']['data']['diff']}
tx=json.loads((OUT/'tencent.json').read_text())
txmap={m.group(1):m.group(2).split('~') for m in re.finditer(r'v_us(\w+)="([^"]*)"',tx['data'])}
for symbol,b in bench.items():
 rows.append([symbol,b['name'],'长桥证券App（用户最新截图）','PE TTM',b['pe'],b['eps'],b['price'],'主报价为10/28收盘；盘前价另列',b['time'],b['pe'],0,'长桥App明确TTM；首次验收基准，非API取得','用户本次提供长桥证券App图片','后续使用长桥官方API，不要求用户反复截图'])
 t=txmap[symbol];pe=float(t[39]);eps=float(t[47])
 rows.append([symbol,b['name'],'腾讯美股接口','fields[39] PE；未明示TTM',pe,eps,float(t[3]),t[30]+' 美东',tx['retrieved_utc'],b['pe'],pe/b['pe']-1,'价格与截图一致，EPS不同；不作为已验证TTM',tx['url'],'从TTM候选中排除未明示口径字段'])
 d=emmap[symbol];pe=d['f115']
 rows.append([symbol,b['name'],'东财美股批量接口','f115：PE TTM',pe,'该次批量响应未请求EPS；不反推后冒充源字段',d['f2'],'2026-10-28 16:00 美东（f124）',em['retrieved_utc'],b['pe'],pe/b['pe']-1,'明确TTM但与截图不同；差异尚未归因',em['url'],'不能仅凭字段名宣称准确；单股接口SKHY空连接，批量接口有值'])
 html=(OUT/f'futunn_{symbol}.html').read_text()
 def get(k):
  m=re.search('"'+k+r'"\s*:\s*"([^"]*)"',html)
  return m.group(1) if m else ''
 pe=float(get('peTtm'));eps=float(get('epsTtm'))
 rows.append([symbol,b['name'],'富途公开美股网页','peTtm / epsTtm',pe,eps,float(get('priceNominal')),'页面主报价：10/28 16:00 美东','2026-10-29 20:55～20:57 北京时间抓取',b['pe'],pe/b['pe']-1,'明确TTM但与截图不同；不能推定与登录App一致',f'https://www.futunn.com/stock/{symbol}-US','平台身份及App/OpenD同源数据待确认'])

rows.append(['SKHY','SK海力士','Finviz公开美股页面','P/E；同时提供EPS (ttm)',10.52,15.40,161.97,'10/29 08:52 美东；盘前价格','2026-10-29 20:52 北京时间抓取',24.05,10.52/24.05-1,'价格时段不同且EPS也不同；不与收盘PE直接比较','https://finviz.com/quote.ashx?t=SKHY','不能用盘前PE填收盘快照'])
rows += [
 ['接口可用性与结论'],
 ['Yahoo quoteSummary','正常cookie/crumb流程HTTP403，已停止；不能记为海力士无数据'],
 ['Yahoo公开页 / StockAnalysis','HTTP403；访问失败与股票字段缺失分开记录'],
 ['新浪美股','SKHY EPS=0、PE=--；未取得有效PE。TSM PE36.53、ASML PE55.39，均未标明TTM'],
 ['根因已确认','原流程优先用了腾讯普通PE字段；并非API都不返回海力士。东财批量接口和富途网页都返回了明确TTM，但未与截图一致。'],
 ['根因尚未确认','各源EPS采用的具体报告期、盈利调整、更新批次及美股每股口径尚未查清；不把汇率、ADR比例、截图过期当成已证实原因。'],
 ['准确性规则','同一软件/同一证券/同一交易时段；明确TTM字段；EPS与PE内部复算；来源间冲突保留，不自动覆盖主表。'],
 ['已确认的同源接口','长桥 QuoteContext.calc_indexes([SKHY.US,TSM.US,ASML.US],[CalcIndex.PeTtmRatio,CalcIndex.LastDone]) 返回 pe_ttm_ratio；static_info返回eps_ttm；quote返回常规报价及独立盘前报价、时间戳。','https://github.com/longbridge/openapi/blob/master/python/pysrc/longbridge/openapi.pyi'],
 ['当前接入状态','长桥只读取数程序已编写，7项口径校验通过；本地缺少账号OpenAPI配置，尚未取得长桥实时响应，不声称已与App完成一致性验收。'],
]
width=len(header);rows=[r+['']*(width-len(r)) for r in rows]
assert all('\n' not in str(v) and '\r' not in str(v) for row in rows for v in row)
token,ss=connect();base=f'sheets/v2/spreadsheets/{ss}'
title='PE_TTM接口实测对照_1029'
sheets=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets']
found=next((s for s in sheets if s['title']==title),None)
if not found:
 helper.request('POST',base+'/sheets_batch_update',token,{'requests':[{'addSheet':{'properties':{'title':title}}}]})
 sheets=helper.request('GET',f'sheets/v3/spreadsheets/{ss}/sheets/query',token)['data']['sheets']
 found=next(s for s in sheets if s['title']==title)
sid=found['sheet_id'];address=f'{sid}!A1:N{len(rows)}'
helper.request('PUT',base+'/values',token,{'valueRange':{'range':address,'values':rows}})
helper.request('PUT',base+'/styles_batch_update',token,{'data':[
 {'ranges':[address],'style':{'foreColor':'#202124'}},
 {'ranges':[f'{sid}!A1:N1',f'{sid}!A3:N3'],'style':{'foreColor':'#FFFFFF','backColor':'#17365D','font':{'bold':True}}},
 {'ranges':[f'{sid}!E{r}:F{r}' for r in range(4,17) if r not in (4,8,12)],'style':{'foreColor':'#C00000'}}]})
for c,w in enumerate([90,100,180,250,100,300,120,290,290,130,160,420,450,420],1):
 helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'COLUMNS','startIndex':c,'endIndex':c},'dimensionProperties':{'fixedSize':w}})
helper.request('PUT',base+'/dimension_range',token,{'dimension':{'sheetId':sid,'majorDimension':'ROWS','startIndex':1,'endIndex':found['grid_properties']['row_count']},'dimensionProperties':{'fixedSize':29}})
got=helper.request('GET',base+'/values/'+address+'?valueRenderOption=UnformattedValue',token)['data']['valueRange']['values']
def norm(v):return ''.join(x.get('text','') for x in v) if isinstance(v,list) else ('' if v is None else v)
for a,b in zip(got,rows):
 a=[norm(v) for v in a]+['']*width
 for x,y in zip(a,b):
  assert abs(x-y)<1e-10 if isinstance(x,(float,int)) and isinstance(y,(float,int)) else x==y,(x,y)
state={'sheet_id':sid,'title':title,'rows':len(rows),'url':f'https://my.feishu.cn/wiki/OCS4wHZRvik8Wckwc1ecHjnhnbI?sheet={sid}','verified':True,'row_height_px':29}
(OUT/'online_comparison.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
print(json.dumps(state,ensure_ascii=False))
