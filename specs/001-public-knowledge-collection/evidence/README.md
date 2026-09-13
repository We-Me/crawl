# 开发验证证据

本目录保存开发任务的实际执行证据（命令、输出与结论）。它不改变 spec.md、acceptance.md 中业务用例的
NOT RUN 状态，也不表示 clarifications.md 的 Q 项业务决策已解决；证据只说明对应工程动作已在目标平台执行并取得结果。

| 记录 | 覆盖任务 | 状态 |
| --- | --- | --- |
| [T002 选型验证](T002-selection.md) | T002 的 Python/依赖/镜像部分 | 已完成；业务契约冻结仍待 T001 |
| [T003 工程初始化与配置验证](T003-environment.md) | T003 的工程与包部分、T004 的 settings 部分 | 已完成；夹具确定性重建与 .env 注入复核见 [logs/t003-repro-checks.txt](logs/t003-repro-checks.txt) |
| [T004—T009 采集闭环](T004-T009-collection.md) | 来源注册与边界、robots 规则执行、发现、获取、归档账本、HTML 解析、标准化与闭环编排 | 已完成并通过离线测试（当前全量 310 passed，含超时重试、三类增量、来源级请求参数、正文分页/接口正文、请求控制建模、真实页面空标题缺陷回归、T026 适配规则与配置/契约漂移用例）；真实站点接入待 Q12/Q13 |
| [T010—T013 多格式解析](T010-T013-parsers.md) | 跨格式块模型、PDF/OCR、Office/CSV/JSON/XML、统一清洗 | 已完成并通过固定样本测试；真实站点样本待 Q12/Q13 |
| [T014 去重与版本](T014-dedup-versioning.md) | 精确/近似重复、来源关系、版本与下线 | 已完成；近似阈值与合并策略待 Q11/Q05 |
| [T015 增量与频率](T015-schedule.md) | 资料类型增量、条件请求、七类频率 | 已完成并通过端到端 304 用例；真实排期待 Q13 |
| [T016 失败与恢复](T016-recovery.md) | 四阶段失败账、补抓、运行恢复 | 已完成并通过故障夹具与真实站点失败样本（CN-04 本地重解析、补抓来源过滤修复） |
| [T017 日志与计数对账](T017-logs-metrics.md) | 运行日志、四类计数、重复与异常统计、交付对账 | 已完成并通过混合运行夹具；真实来源待 Q12/Q13 |
| [T018 交付目录与边界](T018-delivery.md) | 六项成果布局、统一路径、交付检查与 FR-020 禁令 | 已完成；CFG-06—CFG-08 与字段级 schema/追溯校验已由 T019 执行并通过 |
| [CN-04 真实页面缺陷修复](logs/t008-cn04-defect-fix.txt) | T008/T009/T016 的真实站点缺陷定位、修复与本地重解析，含补抓来源过滤修复 | 已完成；新增 2 项回归用例 |
| [T026 适配规则机制](logs/t026-adapter-mechanism.txt) | T026 机制部分：逐来源列表/分页/正文规则、未命中显式记录、真实原件离线复算 | 机制已实现并通过 15 项新用例；逐来源取值与至少 10 词验证仍待 Q12/Q13 |
| [T026 前置真实来源受限核验](logs/t026-realsite-smoke.txt) | 4 个首批来源的最小请求量核验（robots 判定、发现、归档、解析）、CN-01/IN-01 回访（条件请求退化）、栏目入口探测与其余 9 个权威来源的浅层可达性核验 | 已完成五轮受限核验（14 + 9 + 15 + 22 + 9 请求，18 个登记来源均完成浅层核验，含 CN-04 真实页面缺陷的定位与修复）；适配器、至少 10 词与 Q12/Q13 决策仍待办 |
| [T019 采集验收与环境用例](T019-acceptance.md) | AT-001—AT-024 夹具级验收、schema/追溯校验、CFG-01—CFG-09（含交付态 wheel 普通安装复核与 AT 子句补强后的复验） | 已完成；AT-014/AT-024 因 Q11 标 blocked；真实来源待 Q12/Q13 |
| [T027 正式 CLI、运行说明与缺陷修复](T027-cli-runbook.md) | NEXT-01/NEXT-02：`crawl` 子命令、Linux 运行说明、同日重复运行 crawl_id 缺陷的修复与回归 | 已完成并通过本机闭环（14 项 CLI 用例、全量 325 passed、wheel 含入口，见 [logs/t027-cli.txt](logs/t027-cli.txt)、[logs/t027-full-pytest.txt](logs/t027-full-pytest.txt)、[logs/t027-lock-wheel.txt](logs/t027-lock-wheel.txt)）；T027 总体验收仍待 T019/T026 正式收口 |
| [CN-08 有限试点证据](T026-pilot-cn08.md) | NEXT-03：站点卡、离线选择器复算与一次 3 请求的受限真实闭环 | 工程试点已完成（[logs/t026-pilot-cn08.txt](logs/t026-pilot-cn08.txt)）；至少 10 词、歧义与逐站规则仍待 Q12/Q13 |
| [T012 旧格式转换环境核实](logs/t012-libreoffice-env.txt) | NEXT-04：目标 Linux 的 LibreOffice 获取方式、权限阻塞与缺组件行为 | 历史时点记录（缺组件、sudo 需密码）；该阻塞已由下方 2026-09-13 记录关闭 |
| [NEXT-04 真实旧式 Office 转换与追溯](next04-legacy-office.md) | T012：真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯 | 已在 LibreOffice 24.2.7.2 完成真实转换、结构核对与失败路径验证，原件→documents/blocks→追溯校验链路通过；5 项用例依赖系统组件，受限沙箱内按能力探测 skip；5 项已于 2026-09-13 在正常 shell 复跑通过，13 项全部通过 |
| [NEXT-06 运行预算与停止报告](next06-budget.md) | T006/T016/T026/T027：统一请求预算、截止时间、stop 报告与退出码 3 | 已完成工程交付；本地夹具 + 可注入时钟 14 项用例，见 [logs/stage-three-full-pytest.txt](logs/stage-three-full-pytest.txt) |
| [NEXT-07 CN-08 正文边界修复](next07-cn08-body.md) | T008/T013/T026：正文选择器、容器外标题回退、原 10 块 → 6 块（正文逐字保留） | 已完成工程修复；离线差异 [logs/next07-cn08-offline-diff.txt](logs/next07-cn08-offline-diff.txt)、离线重解析 [logs/next07-cn08-reparse.txt](logs/next07-cn08-reparse.txt) |
| [NEXT-08 随包契约与源码外安装](next08-packaged-contracts.md) | T003/T019/T027：契约随 wheel 交付、一致性校验、源码外 sources/check | 已完成工程交付；安装与负向检查见 [logs/next08-installed-wheel.txt](logs/next08-installed-wheel.txt) |
| [十八来源状态记录](t026-eighteen-sources.md) | T026/T005/T010/T013：按站发现抽象、`--start-date`、最小结构分块在 18 个来源上的实现/验证状态 | 已实现并验证 3 个、实现待验证 4 个、访问受限 9 个、未完成 2 个；T026/T019 仍为部分完成 |
| [第六至九轮有限线上记录](logs/t026-round6-limited.txt) | T026/T005/T015：文章级发现、起始日包含式下界、政策文件与日期 meta 的真实站点验证（登记+结果） | 40 个请求、0 失败；CN-08 边界收录/排除、CN-01 3 篇 in_window、CN-04 政策文件与 `firstpublishedtime` |

原始输出摘要在 [logs/](logs/) 目录；命令可在同一仓库状态下复跑。

2026-09-11 文档同步复核：T003—T019 完成后同步入口文档与检查表（`SDD文档说明.md`、`quickstart.md`、
`analysis.md`、`project-startup.md`、`traceability.md`、`checklists/requirements.md` 与本索引），
并修正 T019 报告中已重生成的 `executed_at` 引用；`python3 tools/verify_sdd_documents.py` → PASS
（37 需求/27 任务/37 用例/35 md/179 本地链接），当时全量测试 274 passed；后续新增超时用例、
天城文识别与 AT 子句补强（AT-001/002/004/009/012/016/019/022）、来源级限速/超时/重试生效（NFR-003）、
真实站点核验暴露并修复的空标题解析缺陷与补抓来源过滤缺陷（见 [logs/t008-cn04-defect-fix.txt](logs/t008-cn04-defect-fix.txt)，
第四轮受限核验记录见 [logs/t026-realsite-smoke.txt](logs/t026-realsite-smoke.txt)），
当前 310 passed、文档校验 PASS（37 需求/27 任务/37 用例/35 md/210 本地链接），
见 [logs/t019-pytest.txt](logs/t019-pytest.txt)。

## 本轮状态复核

本目录日志为历史执行证据，本轮仅检查文件，未复跑业务测试。T012 真实旧格式转换、T019 正式验收尚未完成；后续按 [阶段续作说明](../continuation.md) 定向补缺，不重跑所有历史验证。

阶段三追加（2026-09-11）：NEXT-06—NEXT-08 已按各自退出条件完成并留存证据（见上表），
阶段候选一次全量回归 345 passed（[logs/stage-three-full-pytest.txt](logs/stage-three-full-pytest.txt)）。
这些记录只证明对应工程动作，不把 T012/T019/T026/T027 的正式验收或 Q11—Q13 业务决定改为已完成。

## 阶段二复核范围

阶段二 325 passed、CLI 构建与 CN-08 三请求记录均为历史证据。本轮文件检查识别预算执行、正文与源码外契约缺口，见 [阶段三计划](../stage-three.md)；不改写历史日志、执行时间或 AT 状态。

## 阶段三复核边界

本轮核对 d39bdc0 与 NEXT-06/07/08 源码及历史记录，未重跑 345 项测试。同步停止不是硬实时保证；单篇正文、源码外普通安装和正式验收分别记录。当前按 [阶段四计划](../stage-four.md) 收口，不改写原日志。

## 阶段四交接记录（2026-09-11）

NEXT-09 工程交接清单见 [delivery-inventory.md](../delivery-inventory.md)；NEXT-05A 的确认栏见
[决策请求](../decision-requests.md)。本轮只做只读核对（wheel 成员与源码哈希比对）与文档校验，
未新增证据文件、未改变本目录中的历史执行结果；T012/T019/T026/T027 仍为部分完成。

## 阶段四续作记录（2026-09-13）

NEXT-04 按 [NEXT-04 证据](next04-legacy-office.md) 完成真实旧式 DOC/XLS 转换、结构保留与
追溯验证（组件为用户先前已安装的 LibreOffice 24.2.7.2，未重复安装）；NEXT-10 的分块含义
确认材料见 [当前范围与分块](../scope-and-blocking.md)，等待需求方一次性回答。
本轮另修正失败消息误报退出码的缺陷并新增 `tests/test_legacy_office_real.py`；用例门禁改为
能力探测（真的转换成功一次才算组件可用），避免受限环境误报失败、也避免失败路径用例因
组件不可用而以错误的原因通过。T019/T026/T027 与第四阶段整体不因本记录改变；受限沙箱内
5 项依赖 LibreOffice 的用例在受限沙箱内按能力探测 skip；13 项中 8 项（含 OLE2 流结构、
Word FIB 与 BIFF8 首部校验）已在沙箱内通过，另 5 项已于 2026-09-13 在目标 Linux 正常
shell 复跑通过（13 passed），用例级证据闭合。

最新环境更新：[用户提供的 WSL 组件就绪证据](next04-wsl-component-ready.md)。NEXT-04 为 READY_FOR_VALIDATION，历史缺组件日志保留，真实转换尚待验证。

2026-09-13 追加：按站发现抽象（`discover/strategies.py`）、运行时起始日（`schedule/scope.py` + `collect --start-date`）、
最小结构分块（`normalize/segmenter.py`）与本轮 18 来源状态记录已交付；全量测试 384 passed，
契约同步检查通过，第六至九轮真实站点有限运行见 [logs/t026-round6-limited.txt](logs/t026-round6-limited.txt)。
