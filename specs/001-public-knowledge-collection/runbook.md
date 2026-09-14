# Linux 运行说明（正式 CLI）

## 当前原型使用与收尾边界（2026-09-14）

阶段七原型已按 [阶段七](stage-seven.md) 完成：后审查三个代码缺口（附件与正文恢复隔离、`resolve` 队列联动、空值身份选中）修复并验证（实现提交 `e4e5c39`，见 [原型收尾证据](evidence/stage-seven-prototype.md)）；原采集 CLI 与前轮验证成果保留。已满足退出条件，本轮开发结束，转入实际问题驱动维护。

现在的行为：附件补抓只处置附件自身，仍待续母页保持 pending 与续作位置；`resolve` 按完整身份同步队列（同对象仍有其他开放阶段时保持 failed 并明确报告；`manual_review` 不自动补抓）；同 URL 多身份可用显式空字符串选中（`--doc-id ''`）。`failures --summary --source` 的队列/partial 数量仍为全数据根口径，不作为单来源完整性证据。

网站/代理/许可及缺失原件、partial 数据由维护人员按 [人工补齐清单](manual-follow-up.md) 后续处理；本轮不主动线上排障或重抓，不等待外部条件恢复才交付原型。

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。T012 已完成；T019/T026/T027 的全业务验收记录与阶段七基础软件交付分别判断。旧缺组件/权限记录不再作为当前阻塞。

版本：0.1.0｜日期：2026-09-11｜状态：本阶段交付的运行手册。原始阶段二命令在 Linux 环境执行；本轮按源码更正安装与配置传递说明，未重新执行全部示例。阶段三新增运行预算、CN-08 正文选择器与随包契约，命令与退出码已按下述实际实现更新。历史原始输出见
[证据日志](evidence/logs/t027-cli.txt)；命令只包装既有采集管线，不改变来源边界、robots、限速或质量阈值。

正式入口是已安装的控制台命令 `crawl`（源码 `src/crawler/cli.py`，等价入口 `python -m crawler`）。
`tools/realsite_smoke.py` 是开发核验工具，不是业务入口，不写入运行流程。

## 1. 适用范围与当前状态

已交付：来源配置校验、按来源采集、失败补抓、交付校验四类命令；单元与端到端夹具闭环见
[NEXT-01 证据](evidence/T027-cli-runbook.md)。阶段三补充：collect/resume 的统一请求预算、
运行截止时间与停止报告（[NEXT-06 证据](evidence/next06-budget.md)），CN-08 正文边界修复
（[NEXT-07 证据](evidence/next07-cn08-body.md)），随包契约与源码外普通安装
（[NEXT-08 证据](evidence/next08-packaged-contracts.md)）。阶段七补充错误处置命令面：失败账查询
`crawl failures` 与人工处置 `crawl resolve`（[阶段七证据](evidence/stage-seven-delivery.md)）。

未交付：真实来源启用名单与时间范围（Q12/Q13 未决）、后台调度/守护进程、并发采集；
随包来源注册表只有默认禁用的 DEMO 示例；CN-08 的正文选择器只记录在试点配置里，不改正式启用状态。
使用 `--config` 指向的站点配置仍是候选配置，不等于该站已获准正式接入。

## 2. 环境要求

| 项 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Linux（x86_64 已验证） | 证据日志记录 `uname` |
| Python | CPython 3.9.25，由 uv 管理 | `.python-version` 固定；不由系统 Python 替代 |
| uv | 0.11.28（已验证；更高稳定版应同时复核） | uv 自身安装来源不属于 PyPI 镜像 |
| 网络 | 首次安装需可访问登记的清华镜像 | 镜像配置见 [uv 模板说明](uv-template.md)；失败先排查，禁止回退官方 PyPI |
| LibreOffice | 仅在需要解析旧式 `.doc`/`.xls` 时必需：`soffice` 或 `libreoffice` 在 PATH 上（已在 Ubuntu 24.04 用 24.2.7.2 420(Build:2) 验证） | 由发行版包管理器安装（`libreoffice-writer`/`libreoffice-calc`）；不是 Python 依赖，不走 PyPI 镜像，也不写入 `pyproject.toml`。仅解析现代 `.docx`/`.xlsx` 时不需要 |

解释器与系统组件来源单独核验（DEV-009）：`uv python install` 使用 uv 的解释器源，与 Python 包镜像不是同一件事。

组件可用性检查（只确认发现，不触发转换；生产/服务环境同样用运行爬虫的用户执行）：

```bash
command -v soffice libreoffice          # 期望至少一个非空
soffice --version                       # 期望 24.2.7.2 420(Build:2) 或兼容版本
uv run --locked --no-python-downloads python -c \
  "from crawler.parser.legacy_parser import find_soffice; p=find_soffice(); print(p); assert p, 'LibreOffice not found in runtime PATH'"
```

注意：上面只证明二进制存在。受限沙箱（AppArmor/seccomp）里 `soffice --version` 正常，
但完整初始化会失败（`soffice.bin` 自我重启两次后静默 `exit 1`），因此真实旧格式转换与
`tests/test_legacy_office_real.py` 的 5 项组件用例必须在**目标 Linux 的正常 shell** 运行
（2026-09-13 已在本机正常 shell 复跑通过：`13 passed in 4.63s`）：

```bash
uv run --locked --no-python-downloads pytest tests/test_legacy_office_real.py -q   # 期望 13 passed
```

缺组件或转换失败时 `parse_legacy` 抛 `LegacyFormatError`，失败进 `failed_records.jsonl` 的
`parse` 阶段，不返回空文档、不静默降级；补装或提供可用转换器后用 `crawl resume` 重解析
已归档原件（0 次下载）。若无法安装系统组件，可由运维提供满足既有 `parse_legacy(converter=...)`
函数接口的转换器并经 `CrawlPipeline(legacy_converter=...)` 注入，替换前需记录选型与针对验证；
当前没有对应的 CLI 开关，也没有 `CRAWL_*` 转换器路径配置项。

## 3. 安装

从交付副本（含 `pyproject.toml`、`uv.lock`、`.python-version`、`src/`、`tests/`、`specs/`）开始：

```bash
uv python install 3.9.25                    # 仅缺少已固定解释器时；先确认解释器获取方式
# 保留仓库 .python-version，不执行 uv python pin 3.9 改写固定补丁版本
uv sync --locked --no-python-downloads        # 复现锁定依赖并安装 crawl 命令
test -e .env || cp .env.example .env          # 只复制样例，不覆盖已有 .env
uv run --locked --no-python-downloads crawl --help
```

首次生成的 `uv.lock` 只用于新工程；已有锁文件时 `uv sync --locked` 不重新解析依赖。
安装后 `crawl` 位于项目虚拟环境（`uv run` 会自动使用），无需激活 `.venv`。

## 4. 配置

| 变量 | 取值 | 规则 |
| --- | --- | --- |
| `CRAWL_ENV` | `development`（默认）或 `production` | 其他值、显式空值报配置错误 |
| `CRAWL_DATA_DIR` | 开发：默认工程根 `data/`；生产：必须显式绝对路径 | 显式空值报错；相对路径按工程根解析；生产缺路径或非绝对路径启动即失败，不静默回退 |

优先级：进程环境变量 > uv 显式加载的 `.env` > 应用默认值。开发用 `--env-file .env` 加载本机配置：

```bash
uv run --locked --no-python-downloads --env-file .env crawl sources
```

来源注册表：默认读取随包的 `src/crawler/config/sources.yaml`（18 个开发来源 + 禁用 DEMO）；采集其他来源时用 `--config PATH` 指定 YAML。
字段语义与访问边界见 [来源适配输入](source-adapters.md)，配置在加载期校验（域、路径、速率、超时、选择器正则）。

`--url URL`（可重复）按操作者指定的页面/附件直接采集（账本 `discovery_method=manual`），用于已核验
具体地址的补取或按站适配时的离线分析；仍受访问边界、robots、`--start-date` 与请求预算约束。
只给 `--url` 时不隐式跑来源入口（不会把“取一页”扩大成一次栏目采集）；越界 URL 只记跳过、不请求。

`adapter.discovery` 声明该来源已实现/已核验的发现方式（`list`/`search`/`sitemap`/`api`）。未声明的方式在
常规运行中记为 `not_implemented` 且不发请求；命令行显式给出 `--entry-url`/`--keyword`/`--sitemap`/`--api` 时
按用户明确意图运行通用实现，但结果注明“来源未声明该发现方式，未计入已实现”，供有限核验与逐站适配收口。
逐站实现状态见 [十八来源状态](evidence/t026-eighteen-sources.md)。

## 5. 命令与退出码

退出码：`0` 成功；`1` 运行完成但仍有失败或交付校验不通过；`2` 配置、参数或环境错误；
`3` 运行因请求预算或截止时间提前停止（未完成，已归档成果保留）。

```bash
crawl sources [--config PATH] [--json]          # 校验来源配置并列出来源
crawl collect --source ID [--config PATH]       # 指定来源采集
    [--entry-url URL ...] [--keyword WORD ...] [--sitemap URL ...] [--api URL ...]
    [--url URL ...] [--max-items N] [--max-pages N] [--discover-only]
    [--no-attachments] [--start-date YYYY-MM-DD]
    [--max-requests N] [--deadline-seconds S] [--json]
crawl plan [--source ID] [--config PATH] [--ready-only] [--json]    # 补抓计划（只读）
crawl resume --source ID [--config PATH] [--max-tasks N]            # 执行补抓
    [--respect-backoff] [--max-attempts N] [--base-delay-seconds S] [--max-delay-seconds S]
    [--max-requests N] [--deadline-seconds S] [--json]
crawl failures [--source ID] [--url URL] [--stage STAGE]            # 失败账查询（只读）
    [--scope-start-date YYYY-MM-DD] [--doc-id ID]
    [--all] [--summary] [--limit N] [--json]
crawl resolve --url URL --action ACTION [--source ID]               # 人工处置（追加处置行）
    [--stage STAGE] [--scope-start-date YYYY-MM-DD] [--doc-id ID]
    [--crawl-id ID] [--note TEXT] [--json]
crawl check [--require-nonempty] [--json]       # 交付校验（六项成果、schema、追溯、队列对账）
```

失败账查询与人工处置（阶段七，S7-02）：

- `crawl failures` 默认只列**未关闭**失败（`record_only`/`retry_later`/`manual_review`），`--all` 输出全部
  历史与处置行；每行带身份（来源 / 原运行范围 / 母文档 / `crawl_id`）与阶段、错误类型、动作、说明、
  `next=`（下一动作）与 `raw=`（已归档原件，若有），并统计未关闭数与动作分布。处置结果用
  `crawl failures --url URL --all` 按 URL 查询；同一 URL 存在多条身份时，用
  `--scope-start-date`/`--doc-id` 定位到单条身份（这两项也可用于 `crawl resolve`）。
- `crawl resolve` 按**显式身份**追加一行处置：`recovered`（已恢复）、`skip`（确认跳过）、
  `manual_review`（保持未关闭、等待人工）。记录里带值的身份维度必须显式给出；写不全时以退出码 2
  拒绝并列出该 URL 的现有身份与可复制命令（宁可不动，不按 URL 全局关闭）。处置只追加，不删除或
  改写历史失败行。
- `crawl resolve` 追加处置行后按**同一身份**协调队列（P7-02）：`skip → skipped`、`recovered →
  processed`；同对象仍有其他未关闭阶段时队列保持现状并报告 `kept_open` 阶段（不误关未完成对象）；
  对象仍有正文待续（continuation）时 `recovered` 只关闭本次失败、对象保持 pending 继续续作；
  队列回写失败以退出码 2 明确报告，处置行保留，修复后重复执行同一命令即可（幂等）。
- 身份字段为空的记录用**显式空字符串**选中（P7-03），例如同 URL 同时有带/不带 `doc_id` 的记录时：

  ```bash
  crawl failures --url URL --doc-id ''                                  # 只看没有 doc_id 的身份
  crawl resolve --url URL --action skip --source ID --stage fetch \
      --scope-start-date '' --doc-id ''                                 # 只处置该空值身份
  ```

  未显式给空值时（参数缺省）表示“未指定”；存在多条身份会以退出码 2 拒绝，不会猜测。报错信息里
  每个身份都附一条可直接复制的 `crawl resolve` 命令。
- `crawl failures --summary` 输出一次**有界错误摘要**：开放失败、人工处理、受限跳过、待处理队列与
  partial 文档的数量和样例身份；摘要注明聚合口径（事件 = 失败账行数；身份 = 来源 + URL + 阶段 + 范围 +
  母文档；对象 = 身份去掉阶段），并区分事件数与对象数。只读、按需运行，无常驻监控。
- `manual_review` 不等于 `recovered`：它保持未关闭并在 `failures`/`plan`/`check` 与失败计数中可见，
  `plan` 把它标为人工任务且不自动补抓，直到按同一身份再次处置。
- 不支持的续接（如母页返回非 HTML）按人工处置路径处理：先归档原件并记录失败，`plan` 给出人工任务，
  不重复拉取或重解析同一响应，也不伪造正文完成。
- `crawl check` 的对账块除未关闭失败数外给出 `open_failures_by_stage`（按阶段区分），用于确认分阶段
  身份没有被跨阶段行误关闭。

补抓默认立即执行计划中的任务；加 `--respect-backoff` 只处理退避已到的任务，其余记入 `待人工`/`退避等待`。

`--max-items`/`--max-tasks` 是结果数量限制，**不限制请求数或运行时间**。`--max-pages` 覆盖来源适配
配置里的每入口页数上限（仅本次运行生效）；`--discover-only` 只遍历发现入口并把目标入队、不处理正文
（分页覆盖用，发现阶段不受 `--max-items` 限制，仍受 `--max-pages`/预算/截止与 robots 限速约束；
报告 `coverage.processing.mode=discovery_only`，不要与“零结果”混读）。collect 与 resume 的运行预算参数：

已遍历完成（游标 `completed`）的入口，下次运行从入口开始新一轮覆盖（R1，2026-09-14）：“整页都已知即完成”
的推断已取消——已登记目标按更新策略进入 refresh 复查（条件请求，可得 304），新链接照常登记；覆盖受每轮
页数上限与预算约束，未到终点时游标保持 `active` 并从续接页继续，直到走到站点/规则终点才把
`coverage_rounds` 加一。`pass_pages`/`coverage_rounds` 是覆盖口径，`pages_fetched` 只是累计请求数，两者
不能混读。历史游标 note 里的 `incremental_head_checked` 是已失效标记：下次运行会重新从入口遍历核实并在
note 前缀记录“历史快检标记已按 R1 失效并重新核实”。需要完整重遍历时显式给 `--max-pages`（含
`--discover-only --max-pages N`）。

| 参数 | 含义 | 省略时 |
| --- | --- | --- |
| `--max-requests N` | 本次运行最多发出的 HTTP 请求数；robots.txt、重定向每跳、重试、发现页、正文分页、正文接口与附件都在发送前扣减同一预算 | 不限制请求数（输出会提示未设置预算） |
| `--deadline-seconds S` | 本次运行的墙上时限（秒，单调时钟）；到时不发新请求 | 不限制运行时间 |

预算语义（[NEXT-06](evidence/next06-budget.md)）：

- 达到请求上限或截止时间：立即停止，不再发请求，也**不缩短网站要求的等待**；限速或 `Retry-After`
  要求的等待超过剩余时间时同样停止，已归档原件/账本/文档/块保留；分页或附件阶段停止时父文档先落盘（`parse_status=partial`）。
- 停止时输出 `stop.reason`、实际请求数、用时与未处理完的目标数（`stop.unprocessed`），
  `logs/metrics.json` 记 `status=partial`/`stopped` 与 `budget` 明细，退出码为 `3`。
- 预算停止不是网站失败：失败账不追加记录，已归档原件/账本/文档/块保留，`logs/metrics.json` 记
  `status=partial|stopped` 与 `stop.unprocessed`（待处理项合计，含附件）。预算停止的进度不会丢：
  未尝试的目标与附件进入 `manifests/pending_items.json`，未翻到的发现页位置进入
  `manifests/discovery_cursors.json`，下一轮同命令推进到未完成部分；`crawl plan` / `crawl resume`
  仍只处理失败账中**未解决**的失败任务（每个任务保留其 `scope_start_date` 原运行范围）。
- 预算按一次运行生效：每次 collect/resume 以本次传入的预算为准；未传预算的运行不受上一轮
  已耗尽/遗留预算约束。
- 守规线上试点按 DEV-012 取最严格预算：一个来源、`--max-requests 10`（robots、重定向、重试均计入）、
  `--deadline-seconds 300`，并发 1 与来源限速照旧生效。

### raw 完整性覆盖与多轮续接（阶段五 S5-01—S5-06）

- **发现响应也归档**：列表/搜索页、sitemap、发现接口的成功响应先落原件、写账本，再解析，
  保存在 `raw/<source_id>/<YYYY-MM-DD>/discovery/`；解析失败保留原件并写失败账。
  发现页不产出 normalized 文档，但计入 `counters.resources` 与账本行数。
- **遍历终止原因**：每个入口记录 `stop`（`end_of_pages`/`pagination_control_missing`/`max_pages_reached`/
  `max_items_reached`/`request_failed`/`budget_stop`/`loop_detected`/`access_denied`/`selector_miss`/
  `sitemap_index_not_expanded`/`date_scoped_query`/`parse_error`，以及阶段六的 `commit_failed`（目标入队失败，
  游标不推进）/`cursor_save_failed`（目标已入队、游标未推进，重启重放）/`entry_busy`（同一入口已有并发运行）
  与是否 `complete`；每行的 `round_pages`/`coverage_rounds` 是本轮覆盖范围与已完成覆盖轮次。
  截断或失败时发现状态为 `partial`/`parse_error`，不冒充 `ok`/`zero_results`。
- **附件闭环**：文档 `attachments[].status` 为 `downloaded`/`failed`/`boundary_rejected`（robots 与
  已声明大小上限等确定性边界，进 skipped、不写失败账、不重试）/`pending`（预算停止，登记待处理，
  下一轮续传）。规则排除（扩展名不在正文附件声明、适配附件规则不匹配）只计数不下载，见
  `coverage.attachments.exclusions`。
- **覆盖报告**：collect 输出新增 `覆盖：主目标 …；附件 …` 一行，`--json` 与 `logs/metrics.json`
  含同口径 `coverage`（targets/attachments/discovery/queue/pending_total）。`unprocessed=0`
  只说明待处理队列已清空；发现被截断时窗口总量是未知，不能读成全站完成。
- **多轮推进**：同一数据根、同一来源重复 collect，先补从未尝试的 pending 项，再复查 refresh 项
  （已成功目标重新发现后按条件请求核对，可得 304），`--max-items` 限制每轮处理数量。
- **提交顺序与正文待续（阶段六 R1—R6）**：发现目标先持久化入队、再推进分页游标（崩溃后同页重放幂等，
  不会漏目标；同入口并发运行被 `entry_busy` 拒绝）；正文分页耗尽预算或正文请求失败时主目标保持待续
  （`pending_items.json` 的 `continuation`），母页 304 只说明母响应未变、不取消未完成正文，续作完成产出
  `<母doc_id>-R<n>` 新文档身份并保留旧 partial 与原件；归档编号/原件/账本在同一跨进程事务锁内；
  `crawl check` 对损坏状态文件失败退出而不重建。证据：[R1—R6](evidence/stage-six-r1-r6.md)、
  [历史数据只读评估](evidence/stage-six-historical-impact.md)。
- **按站分页规则**：`adapter.pagination_selector` 现在同时作用于发现遍历与正文分页——配置后只跟随该
  控件，控件不存在即视为该来源终点（不再用 rel=next/“下一页”文本启发式）。若站点控件省略入口参数
  （如 IN-02 只带 `page=N`，缺 `PageSize/sortBy` 返回空壳），配置
  `adapter.pagination_merge_entry_params: true`（须与 `pagination_selector` 同时出现）：下一页 URL 由
  入口派生，路径与入口参数沿用入口、控件显式参数覆盖；离线核对见
  `evidence/logs/stage-five-round42-offline-pagination.txt`。
- **结构不完整的列表页**：通用范围（main/article/body）取不到目标而文档整体有链接时，发现按整文档兜底
  并在发现结果 `note` 显式记录（如 CN-04 `/zhengce/index.htm` 双 `<html>`）；这不是静默回退。
- **附件读取中断**：流式读取超时/连接重置按 `FetchError` 记为附件 `failed` 并写失败账，不再中断整次运行；
  未尝试的附件仍记 `pending` 续传。
- **附件大小上限**：超过声明上限（`Downloader` 默认 64 MiB）的附件按
  `boundary_rejected:size_limit_exceeded:<bytes>` 跳过（内联下载、待处理续传与补抓路径一致）：
  不写失败账、不进重试、不留待处理项。目标获取路径直达非 HTML 原件（补抓、手动 URL、页面跳转）
  时按同一上限边读边判，`crawl resume` 对边界拒绝按 `skip` 关闭失败记录；HTML 页面不受附件上限约束
  （第 83 轮修复，见[第 83 轮日志](evidence/logs/stage-five-round83-recovery.txt)）。
  离线核对 `tests/test_attachment_coverage.py`、`tests/test_fetch.py`、`tests/test_recovery.py`。

### 运行时起始日期（`--start-date`）

`--start-date YYYY-MM-DD` 是**内容发布日期**的包含式下界，抓取时间不参与判定；省略时不设日期范围。

- 判定发生在原件与账本落盘之后、产出文档之前：范围内（`in_window`，含等于下界的当天）或
  发布日期未知（`date_unknown`，保留候选并记原因）才产文档；早于下界（`before_start_date`）
  只保留原件与账本、不产出文档，运行汇总单列 `out_of_window`。
- 附件继承母页采集上下文；站点支持日期查询时，搜索模板里的 `{start_date}`/`{end_date}`/`{year}`/`{month}`
  由本参数填充（未给起始日时含日期占位符的模板记为未实现，不静默改用无日期模板）。
- 运行输出新增 `运行范围：起始日 …`、`发现 <stage> 策略=… 状态=… 目标=N` 与逐目标日期判定；
  `logs/metrics.json` 增加 `scope`、`discovery`、`date_decisions`，恢复任务保留原运行范围
  （`crawl plan`/`crawl resume` 显示 `scope_start_dates`，待人工行标注原起始日）。
- 开发验证请显式选择近期窗口（例如运行日前 7 天）并记录实际日期；该窗口不是业务默认，也
  不代表无预算回溯历史。

### 离线复算已归档原件（不发网络）

`tools/offline_replay.py`（开发工具）用**当前**发现规则与分块实现对 `data/raw/` 中的真实原件复算，
输出每份原件的标题、块数/块类型、发布日期、日期判定与发现目标；只读数据根，不写交付目录：

```bash
uv run --locked --no-python-downloads python tools/offline_replay.py \
  --config src/crawler/config/sources.yaml --data-dir data --start-date 2026-09-06 \
  [--source CN-08] [--json /tmp/offline-replay.json]
```

## 6. 运行数据与成果

所有命令共用 `CRAWL_DATA_DIR` 一个数据根，六项成果与运行记录如下：

```text
数据根/
├── raw/<source_id>/<YYYY-MM-DD>/<kind>/   原件（HTML、附件等）
├── manifests/crawl_manifest.jsonl          抓取账本
├── manifests/failed_records.jsonl          失败账（只追加，含处置行）
├── manifests/pending_items.json            待处理目标/附件（S5-06 续接状态，非交付成果）
├── manifests/discovery_cursors.json        发现分页游标（S5-06 续接状态，非交付成果）
├── normalized/documents.jsonl              完整文档
├── normalized/blocks.jsonl                 原始结构块
└── logs/crawler.log, metrics.json, metrics_history.jsonl   运行日志与计数
```

`crawl check` 校验包含 logs/ 在内的六项成果是否齐全、契约字段是否合法、documents/blocks 是否 100% 可追溯到原件，并拒绝数据根内出现采集阶段禁止的派生成果（切片、向量、索引等）。自第 87 轮起另输出**队列对账**：待处理项状态与失败账处置一致（无歧义的矛盾是：队列 `failed` 而失败账该 URL 已按 `recovered`/`skip` 关闭，第 85 轮修复即此类）；失败账仍有未关闭记录只计数、不判失败。

## 7. 常见操作

开发数据根（示例为 `.env` 中的相对路径）：

```bash
uv run --locked --no-python-downloads --env-file .env crawl sources --config specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml
uv run --locked --no-python-downloads --env-file .env crawl plan --source CN-08 --config specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml
uv run --locked --no-python-downloads --env-file .env crawl check
```

守规线上试点（示例：CN-08 单来源、10 请求 / 5 分钟上限、不下载附件、最多 1 篇）。
阶段三只离线验证了预算与选择器，没有重新执行线上采集；上一次同等试点实际用 3 个请求
（[试点记录](evidence/logs/t026-pilot-cn08.txt)），执行前仍须复核 robots 与站点条款：

```bash
CRAWL_DATA_DIR=/tmp/cn08-pilot \
  uv run --locked --no-python-downloads crawl collect \
    --config specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml \
    --source CN-08 --max-items 1 --no-attachments \
    --max-requests 10 --deadline-seconds 300
```

生产数据根（由服务或调度器注入环境变量，绝对路径）：

```bash
CRAWL_ENV=production CRAWL_DATA_DIR=/var/lib/crawl-data \
  uv run --locked --no-python-downloads crawl check --require-nonempty
```

## 8. 故障处理

| 现象 | 含义与处理 |
| --- | --- |
| 退出码 2，`配置错误` | 环境变量、来源配置或域名/路径不合法；按提示修正，不要绕过校验 |
| 退出码 2，`失败账写入失败` | 失败账追加写入出错（磁盘/权限等）：命令明确失败并停止受影响流程，不吞异常继续报告成功；恢复写入条件后重跑同一命令 |
| 退出码 2，`来源未启用` | 该来源 `enabled: false`；启用属业务决定（Q12/Q13） |
| 命令输出 `跳过 robots_disallowed` | robots.txt 拒绝，按策略跳过并记原因；不绕过、不换代理 |
| 失败账 `error_type=http_error` | 网络阶段失败；`crawl plan` 给 `refetch`，`crawl resume` 重新获取 |
| 失败账 `adapter_selector_miss` | 逐来源正文选择器未命中：修复 `adapter.content_selector` 后 `crawl resume` 本地重解析，不重复下载 |
| 计划中 `action=manual` | 永久 4xx、重试耗尽或缺少原件；需人工确认后调整来源配置 |
| 失败账出现 `manual_review` | 已转人工，保持未关闭：`crawl failures`/`crawl plan` 会继续显示；确认后按同一身份 `crawl resolve` 关闭 |
| `crawl resolve` 退出码 2，`未按给定身份找到失败记录` | 身份没写全或与记录不符：按提示补 `--source/--stage/--scope-start-date/--doc-id`，或先 `crawl failures --url URL --all` 查看现有身份 |
| 429 / `Retry-After` | 客户端按站点要求退避；等待会超出本次运行预算时结束本轮，不高频探测 |
| 镜像连接失败 | 排查网络/DNS 或有记录地更换登记镜像；不退回官方 PyPI，不据此升级 Python |
| `check` 报缺失或契约错误 | 按提示定位：缺文件、越界 `raw_path`、字段不符或追溯悬挂引用 |
| 同日重复运行 | 账本按来源与日期续号，`crawl_id` 不复用；失败补抓按 `crawl_id` 定位原件 |
| 发现状态 `partial`/`parse_error` | 该入口未完整遍历（请求失败/截断/解析失败）：失败与原件保留，游标指向未取得页；下一轮同命令从该页继续 |
| 旧游标 note 含 `incremental_head_checked` | 阶段五的“整页已知即完成”推断已按 R1 失效：下次运行重新从入口遍历核实并在 note 前缀记录；`pass_pages`/`coverage_rounds` 从新语义累计，旧 note 不作为覆盖证据 |
| `coverage.pending_total>0` | 待处理队列未清空（目标或附件）：同命令下一轮继续；不是失败，也不表示来源已完成 |
| 退出码 3，`stop.reason=request_budget` | 请求预算用尽：已归档成果保留，未处理完的目标见 `stop.unprocessed`；需要更多成果时调大预算或下次继续 |
| 退出码 3，`stop.reason=deadline` | 到达截止时间：不再发新请求；调大 `--deadline-seconds` 后重跑 |
| 退出码 3，`stop.reason=rate_limit_wait/retry_after_wait` | 网站要求的等待超过剩余时间：按时段/预算重排，不缩短等待 |
| 退出码 2，`随包契约…缺失` | 安装不完整（缺 `crawler/contracts/*.schema.json`）：重新安装完整发行包，不要指向开发机器路径 |

## 9. 已知限制
- 契约随包交付（`crawler/contracts/`，与规格契约一致）；`sources` 与 `check` 在源码外的普通安装可用。
  资源缺失或损坏时以退出码 2 明确失败，不静默跳过契约校验（[NEXT-08 证据](evidence/next08-packaged-contracts.md)）。
- 随包来源注册表只有禁用的 DEMO；真实来源接入待 Q12/Q13。
- 无后台调度/守护进程与并发采集，CLI 为单进程同步执行；旧式 DOC/XLS 转换需要系统 LibreOffice，
  本机已在 LibreOffice 24.2.7.2 上验证（[NEXT-04 证据](evidence/next04-legacy-office.md)）；
  组件缺失或受限沙箱会显式失败，不降级为空文档。转换是同步阻塞调用，单次上限 120 秒。
- 预算的同步调用终止延迟：单次连接/读取超时下限 0.1s，不宣称硬实时中断；同一数据根仍只允许一个写进程。
- 未设置预算的运行不受请求数/时间限制；线上运行必须显式给出 `--max-requests` 与 `--deadline-seconds`。
- 本节只列运行相关限制；完整局限清单、未交付范围与所需业务输入见 [局限与所需输入报告](limitations-report.md)。

## 10. 证据与验证

- 命令面与本机闭环（帮助、配置校验、采集、计划、补抓、交付检查、退出码）：[t027-cli.txt](evidence/logs/t027-cli.txt)
- 交付校验读取开发数据根（已保存原件，离线）：同上日志末节，manifest=10、documents=10、blocks=489、schema 通过、追溯 100%
- 运行预算与停止报告：[NEXT-06 证据](evidence/next06-budget.md)、阶段三完整回归 [stage-three-full-pytest.txt](evidence/logs/stage-three-full-pytest.txt)（345 passed）
- raw 完整性（发现响应归档、分页终止原因与游标、附件闭环、多轮续接）：[阶段五证据](evidence/stage-five-raw-completeness.md)、完整回归 [stage-five-full-pytest.txt](evidence/logs/stage-five-full-pytest.txt)（419 passed）
- 一致性修复（阶段六 R1—R6：复查覆盖、正文待续、归档事务锁、发现提交顺序、损坏状态失败）：[R1—R6 证据](evidence/stage-six-r1-r6.md)、完整回归 [stage-six-full-pytest.txt](evidence/logs/stage-six-full-pytest.txt)（492 passed）、[历史数据只读评估](evidence/stage-six-historical-impact.md)
- 错误可处置性与有界闭环（阶段七）：[交付证据](evidence/stage-seven-delivery.md)、复现 [23 failed](evidence/logs/stage-seven-baseline-repro.txt)、定向 [87 passed](evidence/logs/stage-seven-targeted-pytest.txt)、全量 [514 passed](evidence/logs/stage-seven-full-pytest.txt)、本机闭环 [逐步输出](evidence/logs/stage-seven-closed-loop.txt)（`uv run --locked --no-python-downloads python tools/closed_loop_fixture.py --clean`，只连 127.0.0.1 夹具站点）、正式数据根 [只读评估](evidence/logs/stage-seven-readonly-check.txt)
- CN-08 正文边界修复（离线差异与重解析）：[NEXT-07 证据](evidence/next07-cn08-body.md)
- 随包契约与源码外安装：[NEXT-08 证据](evidence/next08-packaged-contracts.md)、[next08-installed-wheel.txt](evidence/logs/next08-installed-wheel.txt)
- 旧式 DOC/XLS 真实转换、结构保留与原件追溯：[NEXT-04 证据](evidence/next04-legacy-office.md)；夹具重建 `uv run --locked --no-python-downloads python tools/make_legacy_fixtures.py`（需系统组件）
- 环境与镜像复现历史证据：[t019-lock-provenance.txt](evidence/logs/t019-lock-provenance.txt)、[T003 环境验证](evidence/T003-environment.md)
- 测试：`uv run --locked --no-python-downloads pytest -q tests/test_cli.py` → 14 passed（见证据日志）

本说明不把工程夹具通过当作正式业务验收；业务用例状态与来源启用范围仍以
[验收规范](acceptance.md)、[待决事项](clarifications.md) 和 [阶段续作说明](continuation.md) 为准。

## 本轮更正与阶段三限制

上述 sources/plan 为读取配置和失败计划，不发起站点请求；check 需要数据根已有成果，空新目录不应宣称交付通过。CN-08 配置只供工程试点。collect 与 resume 必须传入与 plan 同一份 --config 和同一数据根；不能省略配置让默认 DEMO 注册表处理 CN-08。该单篇原件的正文边界已在 NEXT-07 修复；正式启用范围和跨模板质量验收仍未完成。

阶段三已落地：统一请求/时间预算与停止报告（退出码 3）、CN-08 正文选择器 `#detailContent`、随包契约。
正文缺口按已保存原件修复并经离线重解析验证；正式启用范围仍待 Q12/Q13。

契约资源已随包交付，sources/check 在源码外可用。运行期只允许一个写进程使用同一数据根；跨进程序号续接不等于多进程写入互斥。
