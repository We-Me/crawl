# 证据：T019 采集验收、schema/追溯校验与 CFG-01—CFG-09

日期：2026-09-11。目标平台：当前 Linux。对应需求：NFR-001、NFR-002、NFR-004；完成标准
“所有入选采集需求有真实验收证据；未决阈值不得自动判通过”。

## 实现

- `src/crawler/validate/schema.py`：标准库实现评审契约实际使用的 JSON Schema 子集
  （type/枚举/const/pattern/format/数值与长度边界/items/required/minProperties/
  additionalProperties/allOf/anyOf/if-then-else），按 `contracts/*.schema.json` 校验
  `crawl_manifest.jsonl`、`documents.jsonl`（含逐条附件）、`blocks.jsonl`、
  `failed_records.jsonl`；JSONL 语法错误与编码错误定位到行号，不静默跳过。
- `src/crawler/validate/traceability.py`：端到端追溯校验——文档经 crawl_ids 指向账本、
  经 raw_path 定位原件并核对 sha256；块引用存在的文档；悬挂块、越界路径、哈希不一致逐条
  列出。追溯率分母为交付文件全部记录（partial 不免除），分母为零报告 N/A。
- `src/crawler/validate/acceptance.py`：登记 acceptance.md 全部 37 项用例的可执行状态
  （implemented / blocked / not_selected）与阻塞 Q 项；`build_acceptance_report` 强制
  blocked 用例不得记为 passed，未执行用例保持 not_run。
- `tests/acceptance/`：AT-001—AT-024 采集用例的夹具级验收（25 项，AT 子句逐条核对后补强）与
  CFG-01—CFG-09 环境用例（9 项），全部使用仓库固定样本与本地回环夹具站点，不请求真实站点。
- 契约一致性修复：校验发现实现与已评审数据模型不一致——`parse_status` 使用了
  `complete`（契约为 `ok/partial/failed`）、附件状态使用了 `ok`（契约为 `downloaded/failed`）。
  已按 `data-model.md` 与 `contracts/document.schema.json`、`contracts/attachment.schema.json`
  修正实现与既有用例，新交付数据通过全量 contract 校验。

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 310 passed（2026-09-11T19:42 记录为 292；此后真实页面缺陷修复 +2、T026 适配规则 +15、配置/契约漂移校验 +1，见 logs/t019-pytest.txt）
# （其中 tests/acceptance/ 38 项：AT 用例 27 + 报告一致性 2 + CFG 用例 9；
#            tests/test_robots.py 12 项：FR-001 robots 规则执行，见 logs/t004-robots.txt）
python3 tools/verify_sdd_documents.py
# PASS
```

验收报告（机器可读）：[logs/t019-acceptance-report.json](logs/t019-acceptance-report.json) ——
`passed 22`、`blocked 2`（AT-014 近似阈值/合并处置、AT-024 质量阈值，均取决于 Q11）、
`not_applicable 13`（AT-025—AT-037 领域/来源任务未选中）。测试输出见
[logs/t019-pytest.txt](logs/t019-pytest.txt)、CFG 逐项结果见 [logs/t019-cfg.txt](logs/t019-cfg.txt)、
契约与追溯校验见 [logs/t019-schema-check.txt](logs/t019-schema-check.txt)。
报告写盘时 `executed_at` 取实际执行时间（最近一次重生成 2026-09-11T20:25:08+08:00（T026 适配规则机制后），summary 未变；与
[logs/t019-pytest.txt](logs/t019-pytest.txt) 记录一致），只有测试内部断言
使用固定时刻以免输出漂移；重生成命令见 [logs/t019-pytest.txt](logs/t019-pytest.txt)。

关键用例：

| 用例组 | 结果 |
| --- | --- |
| AT-001—AT-005 | 域外链接与域外重定向逐跳拒绝；受限目标（robots 拒绝路径、登录页/验证码页）不请求且逐项记录原因，robots Allow 最长匹配仍放行；来源配置隔离且非法配置报错（含只改一项、重载后另一来源保持原值）；发现方式含 list/search/sitemap/api/attachment；触发词与补漏词均只影响发现且逐条留痕（补漏词能找到已知材料），标签命中不生成已确认分类；展开正文完整且 noscript 不入正文；AT-005 另覆盖三页正文分页与接口正文（合并顺序、部分页码、账本 discovery_method、部分获取失败保留已取内容并标 partial） |
| AT-006—AT-010 | 两附件一成功一失败且母页保留关系；正文与附件内容重复时附件身份（raw_path/sha256/crawl_id）与母页关系仍保留；各已启用类型（html/pdf/docx/xlsx/csv）逐字节归档且不伪装成已解析文档；原件哈希逐条一致；账本字段、重定向双 URL、搜索 keyword 保留；文档契约通过（含 PDF 经补抓重解析生成 document 并逐字段校验+追溯 100%）；块 order 连续、id 唯一；元数据来源与未知值可区分（有规范化日期必有 raw_date，缺失登记 metadata_missing） |
| AT-011—AT-013 | 文本 PDF 页码/表格、扫描件 OCR 方法与置信度、模糊日期不编造、raw_date 有依据、正文保真；AT-013 另覆盖 zh/en/hi 三语原文逐字保留、800 段超长段落不截断、无标记天城文识别为 hi；AT-012 另覆盖分页 JSON（分页字段与列表项各自保留为 record 块，语义不被推断） |
| AT-015—AT-017 | 版本链与下线历史保留；304 不产生虚假文档；AT-016 另按 news/law/statistics 三类资料端到端复核（新增新闻才产生文档且旧条目只留一份、未改法规 documents=0、新年份统计才更新）；失败账只追加、补抓重解析成功且历史失败保留；“下载成功但解析失败”仍保留原件与账本行（失败记录与 crawl_id、sha256 对应） |
| AT-018—AT-020 | 日志与 metrics 对账一致、请求数≠文档数；交付检查直接遍历数据根，logs/ 等六项成果不因摘要漏列而缺项；交付包无 RAG 派生成果 |
| AT-021—AT-022 | 文档/块追溯率 100%，悬挂块检出，空集 N/A；语法、类型、必填、引用错误按文件与行定位 |
| AT-023 | 速率与并发分别建模（metrics 记录来源速率、来源声明的并发上限与生效并发=1，不互相换算）；429 重试 3 次后成功；临时 500 退避后成功；读取超时退避重试成功、连接超时耗尽按 retryable 上报；永久 404 不重试且不进入退避；请求计数覆盖重试；未显式传入 FetchLimits 时速率/超时/重试上限按来源配置生效（显式值优先） |
| AT-014 / AT-024 | blocked：近似阈值、合并处置与质量样本/分母阈值待 Q11 评审，报告不得显示 passed |
| CFG-01—CFG-09 | 全部 PASS：默认根、进程变量优先、cwd 无关、生产校验、目录/权限校验、工程外绝对根、搬迁后相对路径与哈希不变、越界/符号链接拒绝、工程外导入；交付态 wheel 另做普通安装行为复核，并在 AT 子句补强后按同流程复验（64 条目 wheel、199 条目 sdist、构建后端来自登记镜像、CFG-09 行为逐条一致），见 [logs/t019-installed-wheel.txt](logs/t019-installed-wheel.txt) |

CFG-09 补充复核（2026-09-11）：T003 时期的 CFG-09 只验证了当时仅含 settings 的 wheel。T019 收口时
按当前源码离线构建交付态 wheel（61 个包文件，含 `crawler/config/sources.yaml`），在全新 venv 普通安装后
验证：工程外导入正常；无源码工程根时未配置或相对数据根明确报错、显式绝对路径在开发与生产模式均可用；
随包默认 `sources.yaml` 可加载。原始输出见 [logs/t019-installed-wheel.txt](logs/t019-installed-wheel.txt)。

契约示例交叉核对（2026-09-11）：同一套 `validate_delivery`/`trace_delivery` 对评审阶段手工维护的虚构
示例交付包 `specs/001-public-knowledge-collection/examples/data` 也返回 `ok=true`（documents 2/2、
blocks 3/3 全部可追溯、零 schema 错误），说明契约示例与实现一致；输出见
[logs/t019-schema-check.txt](logs/t019-schema-check.txt)。

## 交付态依赖来源与干净复现

T010—T013 加入 PDF/OCR/Office 运行依赖后，T003 时期的锁文件来源证据不再代表交付态，故在 T019
收口时重做一次 DEV-009 复现核查：当前 `uv.lock` 的 40 个 registry 包与 202 条制品 URL 全部指向
登记清华镜像（无 git/path/URL 依赖）；在只含交付文件的干净副本（`/tmp/crawl-repro-1620`，排除
`.venv`、`.git`、`data`）中用空缓存 `/tmp/crawl-repro-cache` 执行
`uv sync --locked --no-python-downloads` 成功，下载日志出现 112 条清华索引 URL、0 次 pypi.org，
解释器为 uv 管理的 3.9.25；随后在同一副本运行 `uv run --locked --no-python-downloads pytest -q`
得 262 passed。原始输出见 [logs/t019-lock-provenance.txt](logs/t019-lock-provenance.txt)。

## 限制与待办

- 全部验收在固定夹具样本上执行，不构成真实来源验收：真实来源、站点规则与时间范围仍待
  Q12/Q13，因此 acceptance.md 的业务用例状态保持 NOT RUN，本证据只记录工程级结果。
- Q11 未决：近似重复阈值、正文完整性/OCR 准确率样本集与分母没有默认值；AT-014、AT-024
  在报告中固定为 blocked。
- Q15 未决：日志轮转与保留期；本轮不引入日志框架。
- 旧式 DOC/XLS 仍无本机 LibreOffice，转换路线只有注入式验证（见 T010—T013 证据）。
- 未提交 git；`data/`、`.venv`、真实 `.env` 未被任务写入交付记录。
