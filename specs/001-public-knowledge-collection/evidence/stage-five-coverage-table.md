# 阶段五逐来源覆盖表（S5-03 / S5-04 / S5-06 报告口径）

生成时间：2026-09-14（Asia/Shanghai），数据根 `data/`，对应第 89 轮（9 来源入口增量复核，0 新增）后的开发状态
（9 个可采集来源待处理与复查队列清零、失败账未关闭 0 项，`crawl plan` 共 0 项）
（含第 68 轮“已完成入口增量核对”修复、游标恢复、第 74 轮附件大小上限的边界拒绝口径，
以及第 83 轮补抓路径与附件下载同口径执行同一上限）。
文档/块计数按每次抓取身份记录：无条件请求支持的站点复查重取同内容时保留每次记录
（不去重、不建版本；T014 机制未接入 collect，同内容组见第 76 轮日志，作 Q05 候选证据）。
生成命令（只读、不联网）：

```
UV_CACHE_DIR=/tmp/uv-cache uv run --locked --no-python-downloads python tools/coverage_table.py \
    --data-dir data --config src/crawler/config/sources.yaml
```

字段来源：`src/crawler/config/sources.yaml`（来源、启用状态与发现方式）、
`data/manifests/discovery_cursors.json`（遍历范围与终止/续接原因；主游标取页数最多者）、
`data/manifests/pending_items.json`（主目标与附件状态）、
`data/manifests/crawl_manifest.jsonl`（raw 留存行数、哈希存在、原件可回指）、
`data/normalized/documents.jsonl`、`data/normalized/blocks.jsonl`（已产出与近端追溯）、
`data/manifests/failed_records.jsonl`（失败历史，追加式、不清零）。
两列附件口径分开记录：**附件队列**取自 `pending_items.json`（当前队列状态：处理/待处理/失败，含补抓回写后的关闭结果）；**附件记录**按 `documents[].attachments[].status` 汇总（生产时点快照：成功/边界拒绝/失败/待处理，与文档、块同一“每次抓取身份”计数约定，不去重）。规则排除与重复是运行级计数（`coverage.attachments.exclusions`/`duplicates`），不逐来源落盘。
字节级原件哈希校验仍由 `crawl check` 完成；本表只作逐来源口径汇总，不替代验收。
`enabled: false` 的 `DEMO` 占位来源不列入（未启用，不参与 18 来源开发范围）。
发现未完成的来源，其“站点总量”记未知；表中计数均为**已发现**范围内的真实账本计数。
`incremental_head_checked` 表示该入口此前已遍历完成、本轮只核对入口页（不重取历史覆盖页）：
IN-02（445 页历史覆盖）与 IN-05（6 页）为列表入口，CN-02 为关键词“印度”检索入口。
| 来源 | 发现方式（主游标入口） | 遍历（游标） | 终止/续接原因 | 主目标 处理/待处理/复查/失败/跳过 | 附件队列 处理/待处理/失败 | 附件记录 成功/边界拒绝/失败/待处理 | raw 行（哈希/可回指） | 文档 | 块 | 失败账 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CN-01 | list `www.mfa.gov.cn/eng/wjbzhd/` | list completed pages=12 targets=0（+2 其它入口） | end_of_pages: 未发现下一页链接（站点/规则终点） | 7/0/0/0/4 | 0/0/0 | 0/0/0/0 | 63（63/63） | 20（原件可回指 20） | 614 | 0 |
| CN-02 | search `treaty.mfa.gov.cn/web/list.jsp?chnltype_c=all&keywo…` | search completed pages=21 targets=209 | incremental_head_checked: 已完成遍历的增量核对 | 129/0/0/0/0 | 10/0/0 | 201/0/0/10 | 419（419/419） | 175（原件可回指 175） | 1179 | 0 |
| CN-03 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| CN-04 | list `www.gov.cn/zhengce/index.htm` | list completed pages=9 targets=146（+1 其它入口） | incremental_head_checked: 已完成遍历的增量核对 | 12/0/0/0/8 | 0/0/0 | 0/0/0/0 | 73（73/73） | 32（原件可回指 32） | 1041 | 2 |
| CN-05 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| CN-06 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| CN-07 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| CN-08 | list `www.news.cn/xinhuashe/` | list completed pages=5 targets=15 | incremental_head_checked: 已完成遍历的增量核对 | 1/0/0/0/2 | 0/0/0 | 0/0/0/0 | 25（25/25） | 6（原件可回指 6） | 42 | 0 |
| IN-01 | list `www.mea.gov.in/` | list completed pages=6 targets=6（+1 其它入口） | incremental_head_checked: 已完成遍历的增量核对 | 2/0/0/0/0 | 10/0/0 | 10/0/0/10 | 56（56/56） | 12（原件可回指 12） | 657 | 0 |
| IN-02 | list `www.mea.gov.in/FrontEnd/FetchTreatyListGenericLates…` | list completed pages=445 targets=4316（+2 其它入口） | incremental_head_checked: 已完成遍历的增量核对 | 4204/0/0/0/0 | 2/0/0 | 4272/0/3/2 | 9055（9055/9055） | 4307（原件可回指 4307） | 17360 | 6 |
| IN-03 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| IN-04 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| IN-05 | list `www.mha.gov.in/en` | list completed pages=6 targets=324 | incremental_head_checked: 已完成遍历的增量核对 | 53/0/0/0/1 | 906/0/0 | 1332/2/0/907 | 2329（2329/2329） | 70（原件可回指 70） | 3015 | 2 |
| IN-06 | list `www.pib.gov.in/indexd.aspx?reg=48&lang=1` | list completed pages=12 targets=180 | incremental_head_checked: 已完成遍历的增量核对 | 23/0/0/0/0 | 0/0/0 | 0/0/0/0 | 80（80/80） | 60（原件可回指 60） | 1530 | 0 |
| IN-07 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| IN-08 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| IN-09 | list | 无游标 | - | 0/0/0/0/0 | 0/0/0 | 0/0/0/0 | 0（0/0） | 0（原件可回指 0） | 0 | 0 |
| IN-10 | list `onlinemaps.surveyofindia.gov.in/` | list completed pages=11 targets=187 | incremental_head_checked: 已完成遍历的增量核对 | 15/0/0/0/2 | 0/0/0 | 0/0/0/0 | 64（64/64） | 46（原件可回指 46） | 1336 | 0 |
| **合计** | | | | 处理 4446 / 待处理 0 | 附件待处理 0 | 5815/2/3/929 | 12164 | 4728 | 26774 | 10 |
