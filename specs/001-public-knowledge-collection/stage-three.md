# 阶段二复核与阶段三交付计划

> 历史记录说明（2026-09-14）：本文保存对应阶段的计划、资产或限制快照，旧“当前/下一步/等待”不代表当前调度。当前开发仅按 [阶段七](stage-seven.md)；T012 已完成，来源与最小分块已确认。阶段七交付时据实际成果更新清单/限制，不能提前宣称已验收。

检查基线：提交 `4f07c6f`（阶段二）。本轮只读源码、配置、文档和留存日志，未重新执行 Python 业务测试、联网采集或安装系统组件。本文开头为阶段二检查时点；阶段三已完成工程项，结果见末节，当前续作按 stage-four.md。历史执行平台为 Linux，当前文档复核在 Windows，不能据此宣称 Windows 业务环境已验证。

## 已交付与证据边界

- NEXT-01 已完成：pyproject.toml 注册 `crawl = crawler.cli:main`，存在 `python -m crawler`，包含 sources、collect、plan、resume、check。复用 [CLI 证据](evidence/T027-cli-runbook.md)，不重新搭建命令框架。
- NEXT-02 已完成操作说明初版：[runbook.md](runbook.md)。本轮更正复现命令及限制表述，后续只随实际功能改动更新。
- NEXT-03 工程试点已完成：[CN-08 证据](evidence/T026-pilot-cn08.md) 记录 3 请求、1 文档、10 块和交付检查通过；不代表正文质量完全达标或正式来源启用。
- [阶段候选日志](evidence/logs/t027-full-pytest.txt) 记录 325 passed；[构建日志](evidence/logs/t027-lock-wheel.txt) 证明构建成功、入口和版本元数据存在，不证明 wheel 在无源码目录时全部命令可用。日志为历史证据，本轮没有重新运行。
- NEXT-04 仅完成环境核实：[Linux 环境记录](evidence/logs/t012-libreoffice-env.txt) 表明缺少 LibreOffice，sudo 需要密码。真实 DOC/XLS 成功转换仍未完成。NEXT-05 仍待业务决定，T012/T019/T026/T027 不勾选总完成。

## 阶段二识别的缺口（历史，结果见执行记录）

| 编号 | 文件依据与现象 | 影响 |
| --- | --- | --- |
| GAP-01 | continuation.md 同时写 NEXT-01/02 已完成和 READY，仍要求下一轮先做 NEXT-01 | 可能导致重复开发和测试；本轮统一状态，默认转 NEXT-06 |
| GAP-02 | cli.py 只有 max-items/max-tasks；http_client.py 有请求计数和重试，但没有统一请求预算/运行截止时间 | 一篇文档可能产生 robots、分页、附件、重定向和重试等多个请求；上次恰好 3 请求不证明 10 请求/5 分钟预算被程序强制执行 |
| GAP-03 | CN-08 试点证据明确正文尾部含“相关阅读”，未固定正文选择器 | schema/追溯通过不等于正文质量达标；应基于已取原件修复，不能仅增加通用测试 |
| GAP-04 | validate/schema.py 的 contracts_dir 依赖源码根；sources 调用 load_contract，check 调用 validate_delivery | 无源码 wheel 安装时，至少 sources 和 check 无法定位契约；运行说明只强调 check，交付入口尚未完整可移植 |
| GAP-05 | runbook 安装步骤 pin 3.9 会重写已固定的补丁版本；常见操作引用不随交付提供的 data/dev-sources.yaml，resume 未沿用采集配置 | 复制项目后的操作不完整；本轮修正文案，不把历史临时路径当作可复现资产 |

## 有限续作工作项

NEXT-06—NEXT-08 是原有 T 任务的子项，保留 27 个 T 编号，不增加业务范围。DEV-010 的测试停止条件持续适用。

| 次序 | 对应任务 | 交付物与状态 | 必要验证和退出条件 |
| --- | --- | --- | --- |
| NEXT-06 | T006/T016/T026/T027；GAP-02 | DONE（工程交付，2026-09-11）。collect/resume 统一执行请求数和截止时间预算，报告 stop_reason、实际请求数和耗时；参数为 `--max-requests`/`--deadline-seconds`，退出码 3，已写入 runbook；证据 [NEXT-06](evidence/next06-budget.md) | 已按退出条件完成：本地夹具 + 可注入时钟覆盖 robots/重定向/重试共用计数、预算用尽不再发请求、Retry-After/限速等待超剩余时间即停、分页/附件停止后已归档数据保留；未用真实站点压力测试验证限流 |
| NEXT-07 | T008/T013/T026；GAP-03 | DONE（工程修复，2026-09-11）。CN-08 正文容器 `#detailContent` 写入试点配置，容器外标题回退提取；相关阅读/重复标题排除，正文逐字保留；证据 [NEXT-07](evidence/next07-cn08-body.md) | 已按退出条件完成：原件 sha256 与账本一致（无需补取，0 请求），前后块差异 + 离线重解析与交付检查证明正文未删减 |
| NEXT-08 | T003/T019/T027；GAP-04 | DONE（工程交付，2026-09-11）。契约随包交付（`src/crawler/contracts/`，与规格逐字节一致），`tools/sync_contracts.py --check` 防漂移，运行改读包资源；证据 [NEXT-08](evidence/next08-packaged-contracts.md) | 已按退出条件完成：候选 wheel 源码外普通安装（独立 venv、绝对数据根）运行 sources/check 均通过，缺失资源以退出码 2 清晰失败；一次构建与安装检查，未重跑无关格式全部测试 |
| NEXT-04 | T012 | BLOCKED_ENV，已有 sudo/组件证据。目标 Linux 权限或组件供应条件改变后再恢复，优先已有批准的安装流程或运维提供组件 | 真实 DOC、XLS 各一份完成转换、解析和原件追溯；没有成功路径证据不能关闭。不要反复运行 sudo 探测、重装 Python，或把 Windows 组件代替 Linux 结果 |
| NEXT-05 | T001/T002/T019/T026/T027 | WAITING_DECISION，复用 [决策请求](decision-requests.md)，只提交当前采集相关问题 | 决定后只补受影响的正式验收；阶段候选一次必要回归后交接，不把全部未选领域决定作为采集工作的前置 |

## NEXT-06 的预算语义

预算是一次 CLI 运行共享的工程限制：所有实际 HTTP 尝试，包括 robots、重定向每跳、重试、发现页、正文接口及附件，必须在发送前扣减；缓存命中不算新请求，不能在更换来源/客户端或恢复任务时重置。max-items 是结果目标数量限制，不可代替请求预算。

截止时间使用单调时钟。等待限速或 Retry-After 前检查剩余时间，不缩短网站要求的等待来抢发请求；不足时停止。连接、读取和流式下载需受剩余时间约束，停止后不得继续解析下一批或发起额外请求。同步库若不能严格中断正在阻塞的调用，应明确最大终止延迟并验证，不宣称存在实际没有的硬实时截止。停止不得清空成功原件，不把预算耗尽误记为网站永久失败；未处理项和非成功退出须可识别，不伪装任务全量完成。

默认守规试点预算仍按 DEV-012（一个来源、10 请求、5 分钟及更严格网站速率）。NEXT-06 已实现统一限额；线上工程测试必须显式传入预算参数，省略参数不提供上述保护。此前有限测试授权继续有效，不需要重复授权；该约束是落实既有授权范围，不新增业务审批。

## 状态与证据维护

已完成项不再列 READY，不再写“默认从 NEXT-01 起”。状态表作为续作依据，日志按执行时点保留；发现新缺陷时增加明确子项，不能重开全部已完成任务。正文修复可在工程试点范围内进行，不要求先批准生产启用；生产参数和质量阈值仍由业务决定。

阶段三已交付 NEXT-06—NEXT-08，345 passed 为历史候选回归。下一轮按 stage-four.md 收口交接和决定，不重开这些工程项。上述工程项完成而只剩权限/业务阻塞时，提供一次清晰交接并等待条件改变，不创造无边界的故障演练或更多来源测试。

## 执行结果（2026-09-11）

NEXT-06—NEXT-08 已完成工程交付，命令面与证据：

| 项 | 结果 | 证据 |
| --- | --- | --- |
| NEXT-06 运行预算 | `collect`/`resume` 统一请求数与截止时间，停止报告 `stop.reason`/`stop.unprocessed`/`budget`，退出码 3；本地夹具 + 可注入时钟 14 项新用例 | [evidence/next06-budget.md](evidence/next06-budget.md) |
| NEXT-07 CN-08 正文 | `#detailContent` 正文容器 + 容器外标题回退；原 10 块 → 6 块（移除 2 个重复标题、2 个相关阅读），6 个正文段落逐字保留；离线重解析 0 请求、`crawl check` 100% | [evidence/next07-cn08-body.md](evidence/next07-cn08-body.md)、[差异日志](evidence/logs/next07-cn08-offline-diff.txt)、[重解析日志](evidence/logs/next07-cn08-reparse.txt) |
| NEXT-08 随包契约 | 6 个契约随 wheel 交付、一致性校验通过、源码外安装运行 sources/check 通过、资源缺失清晰失败 | [evidence/next08-packaged-contracts.md](evidence/next08-packaged-contracts.md)、[安装日志](evidence/logs/next08-installed-wheel.txt) |
| 阶段候选回归 | 一次全量 `pytest -q` → 345 passed；契约一致性检查通过 | [evidence/logs/stage-three-full-pytest.txt](evidence/logs/stage-three-full-pytest.txt) |

仍未完成（不因上述工程项改变状态）：T012 真实旧格式转换（NEXT-04，缺 Linux 组件/权限）、
T019/T026/T027 的正式业务验收（含 AT-014/AT-024 与 Q11—Q13）、Q14 发布与运维交接。
没有新缺陷或业务决定时，不重开已完成项，也不以更多测试或更多来源探测替代决定。
