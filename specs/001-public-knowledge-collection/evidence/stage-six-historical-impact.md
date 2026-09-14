# 阶段六历史数据只读影响评估（2026-09-14）

本记录对应 [阶段六](../stage-six.md)“共用状态契约与历史数据处理”：对现有开发数据根 `data/`
（账本 12164 行、文档 4728 份、块 26774 个、失败账 10 行、待处理项 5392 条、原件 11838 个）做**只读**
影响评估，列出受影响身份与修复选项。本轮不重写、不迁移、不清理任何输入，也不从日志猜造缺失原件。

只读命令与哈希对照见 [只读校验日志](logs/stage-six-readonly-check.txt)：
`crawl check --json` → `ok=true`（六项成果齐全，schema 0 错，追溯 4728/4728 与 26774/26774 均 100%，
reconcile 无矛盾、未关闭失败 4）；`crawl plan --json` → `refetch` 4 项；`data/` 下非 raw 的 23 个文件
在检查前后 sha256 汇总一致（`8e3a170d1a14…`），证明“检查只读、不重建损坏文件”。

## 1. 归档身份重复（R3 相关）

- `CN-01_20260911_0001` 出现 3 次：两次同 URL（`mfa.gov.cn/eng/`，同 sha256）与一次
  `cs.mfa.gov.cn/`；`IN-01_20260911_0001` 出现 3 次：3 个 URL、3 个 sha256。
- 6 条账本行引用的原件全部存在，且逐字节 sha256 与账本一致（不同字节已按 `-<sha8>` 另存为
  `index-4946403b.html`、`index-12396444.html`、`index-baef8ecc.html`）；本次重复**没有丢字节**。
- `documents.jsonl` 中这两个 `doc_id` 同样各 3 行，与账本行一一对应；按身份索引的下游消费者会歧义。
- 选项：A 保留现状并在交付说明标注（默认，不改写历史）；B 预览式迁移，为重复的后续行分配可区分身份
  （先出报告、备份、幂等、可重复执行）；C 重采同页——不解决历史身份重复，不推荐。本轮未执行任何迁移。

## 2. 旧失败账与恢复关联（R5 相关）

- 10 行失败账**全部**缺少 `doc_id`；6 行缺 `scope_start_date`。
- `crawl check` 判 4 项未关闭：IN-05 1 项、IN-02 3 项（均为 PDF）。原因是旧 `resolved` 行写的是
  `scope_start_date=None`，与新身份口径 `(url, stage, scope_start_date, doc_id)` 不匹配；新代码不再
  仅按 URL 关闭，因此旧“已恢复”结论不能自动关闭旧账。
- 这 4 个 URL 均在 2026-09-14 07:52 有原件归档且 sha 一致（`raw/…/attachment/*.pdf`）：物理恢复已完成，
  只是账本身份不闭合。
- 选项：A 保持未关闭（默认；`crawl plan` 显示 `refetch`，不会误伤真实失败）；B 有范围线上
  `crawl resume`（4 个任务，按新口径追加 `resolved` 行后闭合；需按 DEV-012 登记一次预算）；C 预览迁移
  依据证据补写身份字段（未做）。本轮未执行线上补抓与迁移。

## 3. 旧发现游标（R1/R4 相关）

- 15 个游标中 12 个是 `completed` + 历史 `incremental_head_checked` note（note 被旧写法递归嵌套，
  最多 22 层），另 2 个 `completed`（`end_of_pages`、`pagination_control_missing`），
  1 个 `active`（`IN-02|list|2026-09-06|…FetchTreatyListGenericLatest?page=2&PageSize=10&sortBy=sortby`，
  旧 note `max_items_reached`，`next_url=page=3`）。
- 全部 15 行都缺 `last_commit_page`/`last_commit_digest`/`pass_pages`/`coverage_rounds` 新字段。
  12 个历史快检标记按 R1 失效：下次该入口运行会重新从入口遍历核实，并在 note 前缀记录
  “历史快检标记已按 R1 失效并重新核实”；新字段缺失按 0 处理，旧 note 不作为覆盖证据。
- 唯一 `active` 游标没有 R4 提交标记。离线核对其页原件
  `raw/IN-02/2026-09-13/discovery/FetchTreatyListGenericLatest-cda6735d`（2026-09-13 23:03 归档）中的
  10 个 `TreatyDetail` 目标：全部已登记为 `processed` 待处理项 → **未观察到漏目标**；page 3 及以后由
  `page=1` 入口的历史遍历覆盖（该入口游标记 445 页）。
- 选项：A 下次正常运行（默认；R4 的重放与幂等已保证续接安全）；B 对 IN-02 做有界重跑核对——本轮未执行
  线上运行。

## 4. 旧待处理项与正文待续（R2 相关）

- 5392 条待处理项（4463 目标 / 929 附件）全部是 R2 之前的旧格式：没有 `continuation` 字段。旧数据不会
  被误读成“有待续”，也不会被误读成可续作。
- 39 份 `parse_status=partial` 文档：33 份能找到同 URL 的 `processed` 待处理行（当时以“部分成功”结束，
  无待续引用）；其余 6 份是入口/列表页（`mea.gov.in`、`pib.gov.in`、`treaty.mfa.gov.cn` 等），
  与待处理行的 URL 归一化不一致，未匹配。
- 影响：这些历史 partial 若确有未取正文部分，无法从状态恢复，只能在新窗口按预算复核重取；系统不会自动
  补全，也不会伪造 part。
- 选项：A 保留 partial 现状并如实报告（默认）；B 未来对具体来源 refresh 重取（另行登记线上预算）；
  C 从 raw 猜造缺失部分——禁止。本轮未执行。

## 5. 文档附件状态与实物不一致（阶段五遗留）

- `documents.jsonl` 中 929 个附件状态仍为 `pending`；对应待处理行：928 个 `processed`（`raw_path`
  存在且被账本引用）、1 个 `skipped`（IN-05 `HMkheloIndia_08062022.pdf`，robots.txt 获取失败保守拒绝，
  无原件）。
- 实物与原件在 raw/账本/待处理行一侧完整；附件续传只更新队列与账本，未回写文档行的
  `attachments[].status`，因此文档行的 `pending` 落后于实物状态。
- 选项：A 保留并在交付说明标注（默认）；B 预览式迁移，按待处理行与 raw/sha 校验把状态更新为
  `downloaded`/`skipped`（幂等、备份、可回滚）；C 重规范化这些文档（会追加文档行，需另定版本策略，且会
  扩大本轮范围）。本轮未执行迁移。

## 6. 损坏状态文件

- 本轮未发现损坏：`pending_items.json`（5392 条）与 `discovery_cursors.json`（15 条）可解析、结构合法，
  reconcile `problems=[]`；失败账 10 行全部可解析。
- R6 之后若出现截断 JSON、`items` 类型错误或非法条目，`crawl check` 会失败并给出文件与原因，且**不**
  覆盖或重建原文件；合法缺失（初始状态）与合法空状态仍按零记录。

## 汇总：受影响身份与建议

| 项 | 受影响量 | 建议 | 是否阻塞本阶段交付 |
| --- | --- | --- | --- |
| 归档身份重复（R3） | 2 个身份 / 6 行账本 / 6 行文档 | 保留并标注；需要时再做预览式重编号迁移 | 否（原件完整） |
| 旧失败账身份缺失（R5） | 10 行缺 `doc_id`；4 项未关闭 | 保持未关闭；需要时 4 任务有界 resume | 否 |
| 旧游标（R1/R4） | 15 个游标（12 个旧快检标记） | 下次正常运行即按新语义重新核实 | 否 |
| 旧待续缺失（R2） | 5392 条待处理项无 continuation；39 份 partial | 保留；需要时按来源新窗口复核 | 否 |
| 文档附件状态滞后 | 929 个附件（928 已下载，1 skipped） | 保留并标注；需要时预览式状态回写 | 否 |
| 损坏状态文件 | 0 | 出现时按 R6 失败并保留原件 | 否 |

所有迁移选项都要求“先报告、再备份、幂等、可重复执行”，并且只从既有原件与账本取值；本轮未执行任何迁移，
`data/` 保持只读前后字节一致。
