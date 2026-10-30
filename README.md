# 102-Github-USA

美股数据源对比、GICS 股票筛选与飞书在线研究表。当前工作区的后续迭代同步至本仓库。

## 当前规则

- 以 Nasdaq 美股筛选市值为统一筛选依据：至少 300 亿美元；各 GICS 二级补足市值前二。
- 按入选股票的一级市值合计、一级内二级市值合计、二级内个股市值依次降序。
- 东方财富美股明确 TTM 字段作为 PE 主源；腾讯用于行情核对，富途用于交叉检查；长桥官方接口可选，须账号配置。
- 市值、行情、历史与财务快照分别标注时间；旧缓存不标为实时；缺失或冲突不伪造数值。
- 飞书输出：二级分类颜色、29px行高、无手工换行、待核验项红字。

## 代码与本地数据

`work/selection_*.py` 获取候选及行情；`build_selection_sheet.py` 构建筛选表；`publish_selection_sheet.py` 发布并核验；`sort_selection_sheet.py` 保留完整行数据进行三级重排。

`provider_reliability.py`、`ttm_source.py` 实现来源对比和 TTM 选择；`valuation_policy.py` 与 `us_market_policy.py` 保存估值及市场范围约束。`work/longbridge/` 是可选的只读长桥适配器。

`config/` 保存参考项目的公开/主营业务分类映射快照及颜色，不代表官方授权实时 GICS 分类；临时分类继续标记待核验。

当前发布流程是已有工作区的延续，需要本地 `work/selection/`、`work/composite/` 等输入快照。它们不随 Git 发布。新克隆不是一键全量重建工具；应先读取获授权的飞书参考表并取得行情与财务输入。部分归档构建脚本仍依赖此前生成的本地数据。

## 配置与检查

Python 3 标准库及 curl 可运行主要筛选和飞书 API 流程。飞书凭据从环境变量、根目录 `.env` 或忽略的 `work/local_config.json` 指定的文件加载。参考 `.env.example`，切勿提交真实凭据。

```sh
python3 -m unittest discover -s work -p test_selection.py
python3 -m unittest discover -s work -p test_ttm_source.py
python3 -m unittest discover -s work -p test_valuation_policy.py
python3 -m unittest discover -s work/longbridge -p test_fetch_ttm.py
```

普通代码迭代通过 Git 提交与推送同步，业务数据仍交付在线飞书表。每次同步记录在 `CHANGELOG.md`；凭据、Cookie、抓取缓存和第三方依赖目录保留本地。
