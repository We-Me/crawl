# SDD 历史说明归档

归档日期：2026-09-14。保存 0cd04e0 及之前的说明、阶段进度和曾经的调度依据。以下“当前”“待选”“等待安装”等均指原记录时点，不能作为现在的执行指令。当前开发入口为 [阶段七](specs/001-public-knowledge-collection/stage-seven.md)。来源文档与原始 evidence 日志不修改；仅为归档后的链接位置作相对路径调整。


## 根目录说明旧版

# 公开知识采集项目 SDD 文档说明

## 当前使用方式（复核 61e34d8 后）

从根目录 AGENTS.md 开始。先读 [已确认范围](specs/001-public-knowledge-collection/raw-first-development.md)，再按 [阶段六修复说明](specs/001-public-knowledge-collection/stage-six.md) 执行。阶段六六项缺陷（状态/恢复判定、归档与游标提交一致性、正文续接、增量覆盖）已完成修复与验证（定向 103 passed、完整回归 492 passed，提交与证据见 [stage-six.md](specs/001-public-knowledge-collection/stage-six.md)）；不再等待分块或 18 来源选择，不进入发布部署。

文档职责：spec/constitution 管需求原则；raw-first-development 管用户决定；stage-six 管唯一当前修复顺序，stage-five 管上一阶段交付摘要；tasks 管 T 编号与证据状态；decision-requests 管真正需要外部输入的事项；continuation、stage-five-history 与阶段三/四保存历史。不要在每个文件复制最新统计和待办表；只更新实际受影响的契约、代码说明与证据。下方早期复制/初始化说明用于空项目，现有项目不重新初始化。

版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

本套文件根据工作区的两份 Word 原始规范和两份 Markdown 需求审查生成，将公开资料采集与七类知识组织转成需求、设计、契约、任务和验收追踪。按规格驱动开发理解 SDD，参考 GitHub Spec Kit 的文档结构。没有默认某个版本覆盖另一版本，所有未决事项明确保留。

当前已有采集源码、锁定环境、夹具验证和有限真实站点核验；正式业务范围、部分系统组件与验收仍有缺口。续作按下方阶段入口推进，不从初始文档阶段重来。文档采用 Markdown，方便开发和版本维护；四份输入统一存放于 docs/；两份 Word 字节不变，两份需求审查仅更新链接，业务内容不变。

## 项目目录与迁移

四份输入文件统一放在项目根目录的 docs/ 下；.specify/ 和 specs/ 保持现有位置。新项目开发时整体复制以下内容，保持相对路径：

```text
新项目/
├── .env.example           开发环境配置样例
├── .gitignore             排除本地环境与开发数据
├── AGENTS.md              Agent 启动与 Python 开发约束
├── docs/                  两份 Word 原件和两份需求审查 Markdown
├── .specify/memory/        项目原则
├── specs/001-public-knowledge-collection/  完整规格 契约 样例和追踪
├── templates/uv/pyproject.toml  uv 镜像环境模板
├── tools/verify_sdd_documents.py
├── tools/verify_sdd_documents.ps1
└── SDD文档说明.md
```

来源登记的 path 字段相对于项目根目录，指向 docs/；两份审查文件内部也使用相对链接。复制时包含隐藏目录 .specify，以及 .env.example 和 .gitignore；不要复制真实 .env、.venv 或开发 data/。build_sdd_documents.py 是初始生成脚本，可不复制；不要通过重跑它覆盖已评审的规格。

## 文档导航

| 文件 | 用途 |
| --- | --- |
| [项目原则](.specify/memory/constitution.md) | 规格治理、保真追溯、来源和范围原则 |
| [需求规格](specs/001-public-knowledge-collection/spec.md) | 用户场景、37 条需求、成功标准和边界 |
| [待决事项](specs/001-public-knowledge-collection/clarifications.md) | 17 项冲突/缺口、候选处理和受影响工作 |
| [技术设计](specs/001-public-knowledge-collection/plan.md) | 模块职责、数据流、恢复、目录与风险 |
| [Python 开发约束与选型](specs/001-public-knowledge-collection/tech-stack.md) | Python 与 uv 已明确；优先 3.9；保守引入成熟稳定依赖，框架待选 |
| [项目起步说明](specs/001-public-knowledge-collection/project-startup.md) | src 布局、环境变量、开发与生产数据目录及 9 项待执行配置验收 |
| [设计依据](specs/001-public-knowledge-collection/research.md) | SDD 方法依据、7 项候选决策及新增目录配置决定 |
| [数据模型](specs/001-public-knowledge-collection/data-model.md) | 原字段层级、对象关系和领域映射 |
| [数据契约](specs/001-public-knowledge-collection/contracts/README.md) | 6 份 JSON Schema 与虚构 JSONL 样例 |
| [实施任务](specs/001-public-knowledge-collection/tasks.md) | 27 项待实施任务、依赖和完成标准 |
| [验收规范](specs/001-public-knowledge-collection/acceptance.md) | 37 项未执行用例、指标和验收证据格式 |
| [追踪矩阵](specs/001-public-knowledge-collection/traceability.md) | 来源到需求、模块、任务、用例的对应 |
| [来源登记](specs/001-public-knowledge-collection/sources.md) | 四份输入的指纹和 Word 结构转录 |
| [来源适配输入](specs/001-public-knowledge-collection/source-adapters.md) | S2 的 18 个首批来源及专站规则登记 |
| [质量检查表](specs/001-public-knowledge-collection/checklists/requirements.md) | 已核查的文档项和后续实施/验收门槛 |
| [运行说明](specs/001-public-knowledge-collection/runbook.md) | Linux 安装、配置、`crawl` 命令、故障处理与已知限制 |
| [CN-08 试点卡](specs/001-public-knowledge-collection/pilot-cn08.md) | NEXT-03 的来源候选参数与受限试点结果 |
| [阶段交付决策请求](specs/001-public-knowledge-collection/decision-requests.md) | 收口前需要业务确认的 6 项决定与影响 |
| [工程交付清单](specs/001-public-knowledge-collection/delivery-inventory.md) | 源码提交、锁文件与构建产物、运行说明、证据索引、组件缺口与未交付范围 |
| [局限与所需输入报告](specs/001-public-knowledge-collection/limitations-report.md) | 局限清单、未交付范围、所需业务输入、环境需求与恢复条件 |
| [交接指南](specs/001-public-knowledge-collection/quickstart.md) | 阅读顺序、文档校验和后续开发使用方式 |
| [一致性核验](specs/001-public-knowledge-collection/analysis.md) | 本次实际检查结果及仍未解决的业务问题 |

## 关键范围处理

S1 V1.1 明确采集阶段不做 RAG 切片和索引，S2 V1.3 确实包含七类实体、切片、索引及边缘目标。两侧都被保留：采集要求及领域条件要求分别可追踪。Q01 的范围选择尚未完成，因此这是一套可评审草案，不能冒充无待决项的实施基线。

原文未给出完整的附件对象、抓取到文档的关联、哈希统一含义和领域交付格式。本套提供可审查候选，明确哪些是新增设计；不把此前无依据的发布目录、分类审核状态或引用清单恢复成强制要求。每个来源的现场规则、数据规模和验收阈值仍按原文事实保留为待定。

## 验证与后续使用

运行 [verify_sdd_documents.ps1](tools/verify_sdd_documents.ps1) 可以复核文档链接、编号映射、四份原文件指纹、Schema 样例、哈希和引用。核验不会联网采集。按照待决事项确定当前范围后，再执行任务文档；真实软件和数据验收按验收规范记录。

文档组织参考 [GitHub Spec Kit 快速指南](https://github.github.com/spec-kit/quickstart.html)，字段契约采用 [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)。引用用于说明方法，不表示项目通过外部标准认证，也不表示安装或执行了 Spec Kit 工具。

## uv 镜像模板与 Linux 开发

项目 Python 包必须使用镜像源，复制项目时包含 templates/。从 [uv 镜像模板与 Linux 使用说明](specs/001-public-knowledge-collection/uv-template.md) 开始，先复制或合并配置，再由 Codex 按任务推进；当前模板无业务依赖，不是已完成的业务环境。

2026-09-11 进展：已按 DEV-009 合并模板，并完成 T002 起步选型与 T003 工程初始化（CPython 3.9.25、uv 0.11.28，锁文件与制品均来自登记镜像，CFG-01—CFG-09 通过）；采集范围 T004—T019 已在固定夹具上实现（来源边界与 robots 规则、发现、获取、归档账本、HTML/PDF/OCR/Office/结构数据解析、去重与版本、增量调度、失败补抓、日志对账、交付目录与采集验收），全量 310 项测试通过（含真实站点核验暴露的空标题解析缺陷与补抓来源过滤缺陷的回归用例），其中 AT-014/AT-024 因 Q11 未决在报告中保持 blocked，业务用例状态仍为 NOT RUN。同日在用户许可下分批对 18 个登记来源完成五轮最小请求量核验（共 69 个请求，遵守 robots 与逐来源限速），记录条件请求退化、robots 保守拒绝与域名别名等站点约束，见 [T026 前置核验](specs/001-public-knowledge-collection/evidence/logs/t026-realsite-smoke.txt)。业务契约冻结（T001/T002 契约部分）、真实来源接入与领域任务 T020—T027 仍待相应 Q 项决策；记录见 [T002 选型验证](specs/001-public-knowledge-collection/evidence/T002-selection.md)、[T003 环境验证](specs/001-public-knowledge-collection/evidence/T003-environment.md) 与 [T004—T019 证据索引](specs/001-public-knowledge-collection/evidence/README.md)。

## 阶段进展（2026-09-11 续作）

NEXT-01/NEXT-02 完成：正式业务 CLI `crawl`（sources/collect/plan/resume/check，退出码 0/1/2）与 Linux 运行说明已交付，本机回环闭环与 `--env-file .env` 命令均实际执行（见 [运行说明](specs/001-public-knowledge-collection/runbook.md)、[CLI 证据](specs/001-public-knowledge-collection/evidence/T027-cli-runbook.md)）；闭环中发现并修复同日多次运行 `crawl_id` 重复导致补抓指向错误原件的缺陷，全量回归 325 passed。NEXT-03 产出 [CN-08 试点卡](specs/001-public-knowledge-collection/pilot-cn08.md) 并完成一次 3 请求的受限真实试点；NEXT-04 记录目标 Linux 的 LibreOffice 权限阻塞。任务状态仍以 tasks.md 与 acceptance.md 为准。

## 后续开发入口

优先阅读 [阶段续作说明](specs/001-public-knowledge-collection/continuation.md)：已有工程证据直接复用，先做正式业务操作入口和运行说明，不以反复全量测试作为默认工作。T012/T019 更正为部分完成，详见 tasks.md；历史记录中的完成表述按此限定。用户已授权遵守网站规则的有限真实测试，无需逐轮重复确认。继续现有项目时须携带 src/、tests/、pyproject.toml、uv.lock、.python-version 及现有工具与证据；上面的文档复制清单仅用于新建规格项目。

## 阶段二后续开发

阶段二提交 4f07c6f 已交付正式 CLI 和单站试点；不再重复 NEXT-01/02。[阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 的 NEXT-06—NEXT-08 已完成，当前按 stage-four.md 收口。325 passed 为历史结果；本轮仅复核文件并修订后续文档。

## 阶段四：交接与正式验收准备

当前入口为 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md)。NEXT-09 工程交付清单已交付
（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)），NEXT-05A 决策确认栏见
[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)；等待业务确认与 Linux 组件条件变化后执行
NEXT-04/05B/05C 正式验收收口。本轮不新增业务代码或重跑阶段测试。

## 当前入口（2026-09-13）

第四阶段 part1 已交付清单、确认栏与局限报告，勿重复生成。按 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 将本轮范围收敛到采集、标准化及分块交付，不安排 RAG；跨段语篇组合含义待回答。工程交接完成不等于正式来源和质量验收完成。


## 交接指南旧版

# 文档使用与后续开发交接指南

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](specs/001-public-knowledge-collection/evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。第四阶段整体仍未完成（T019/T026/T027 与正式业务待决）。下文早期缺组件/权限记录按历史时点理解，不再作为等待安装的理由。

> 已开发项目请先阅读 [阶段续作说明](specs/001-public-knowledge-collection/continuation.md)。当前根目录已有 pyproject.toml、uv.lock 和 src/，不要复制空模板覆盖或重做初始化；下文起步命令仅用于新空项目。


版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

当前工作区交付的是 SDD 文档、虚构契约样例与固定夹具上的采集实现。正式业务 CLI crawl 与 Linux 运行说明已交付；尚无索引或边缘软件。已有有限真实站点工程试点，不能与正式业务验收混同。以下步骤先用于审查，再用于后续开发交接。

2026-09-11 状态：采集范围 T003—T019 已实现并通过 310 项测试（无 CLI、无真实站点任务；AT-014/AT-024 因 Q11 未决保持 blocked），领域与真实来源任务仍待相应 Q 项决策。任务勾选见 [tasks.md](specs/001-public-knowledge-collection/tasks.md)，证据索引见 [evidence/README.md](specs/001-public-knowledge-collection/evidence/README.md)。

## 项目输入位置

四份输入位于项目根目录 docs/。新建项目时一起复制 AGENTS.md、docs/、.specify/、specs/、两个 verify_sdd_documents 校验脚本和根目录说明，并保持相对路径；不要再将输入文件放回根目录。来源登记用 path 字段定位 docs/ 文件。

## 阅读顺序

1. 先阅读根目录 AGENTS.md，再阅读 SDD文档说明.md、spec.md 和 tech-stack.md，明确 uv 管理、Python 3.9 优先与失败后逐个次版本升级规则，以及尚未选定的框架。
2. 阅读 clarifications.md，先处理当前范围会用到的 Q 项；不需要先解决所有未选领域问题。
3. 阅读 plan.md、research.md 和 data-model.md，核对候选方案和原文要求的区别。
4. 在 contracts/ 评审字段和样例；使用 traceability.md 对照原文、任务与验收。
5. 按 tasks.md 实施已选任务，实际执行 acceptance.md 用例后再勾选任务。

## uv 与业务环境

按 tech-stack.md 使用 uv 管理业务环境，优先构建 Python 3.9 的完整依赖和已选功能。不能构建时先排查依赖及平台问题，有明确失败证据才尝试 3.10，仍不成立再尝试 3.11，依次提高；找到最低可行版本即停止。uv 初始化、锁定、同步和验证命令详见 tech-stack.md；本次不实际创建业务环境。

新增依赖先确认当前任务确有需要，优先成熟库的兼容正式稳定版本。pyproject.toml 设置 uv 的 prerelease = "disallow"；默认保留可行锁定版本，必要更新针对具体包并验证传递依赖变化。完整说明见 tech-stack.md 的成熟依赖与稳定版本策略。

## 文档验证命令

在项目根目录使用支持 Test-Json 和 ConvertFrom-Json -DateKind String 的 PowerShell 7.5 或更新版本运行：

```powershell
./tools/verify_sdd_documents.ps1
```

该命令只读取规格、schema、样例和四份原文件，检查链接、编号、来源指纹、契约样例和引用，并输出核验摘要；它不会访问业务站点。当前 Test-Json 将 format 视为注解，脚本另外断言日期、带时区时间和 URI 格式；使用 DateKind String 防止 PowerShell 在检查前自动改写时间字符串。校验要求 PowerShell 7.5+ 和 Python 3.9+，不需要额外 Python 包。默认使用 PATH 中的 python 命令；若 Python 未加入 PATH 或需使用指定环境，通过 -PythonPath 传入解释器路径。脚本根据自身位置定位项目，不依赖原电脑路径或当前工作目录。

```powershell
./tools/verify_sdd_documents.ps1 -PythonPath 'C:/path/to/python.exe'
```

脚本中所有原件和 JSONL 都是虚构样例，验证通过只表示文档和样例一致，不能算实际爬虫验收。现有 checks 的实际结果见 analysis.md。

## 后续采集程序的操作说明要求

实现完成后，T027 再依据真实 CLI/API 补充安装、来源配置、首次回填、增量、补抓、重新解析、数据校验和交付命令。本次不提供不存在的 python -m crawler 等命令。运行说明应明确目录根、必需权限、依赖版本、恢复方式、日志位置以及成功/失败/partial 的判定。

## 规格变更

新增或修改需求先记录原文或决策依据，再改 spec.md 与相应 Q 项，随后同步数据契约、plan/tasks/acceptance 和 traceability。不能只修改某个 schema 而保留过期验收。tools/build_sdd_documents.py 是本次初始文档生成脚本，维护者手工修订文档后不要直接重跑覆盖；若需要重生成，应先将已评审内容同步到生成脚本并检查差异。

## 可保留的验证资产

固定原件夹具、schema、AT 场景及来源记录可供后续开发继续使用。虚构样例适合验证数据关系，但不足以覆盖 PDF、OCR、Office、真实页面和网络故障；这些实际夹具由 T003 及相应任务建立。

## 新项目初始化与数据目录

复制时一并带上根目录 [.env.example](.env.example) 与 [.gitignore](.gitignore)，不复制真实 .env、.venv 或开发 data/。按 [项目起步说明](specs/001-public-knowledge-collection/project-startup.md) 创建 src/crawler/、配置包安装和统一 settings 接口。开发默认 data/ 与 src/ 同级，正式运行用环境变量指定绝对数据根。说明中的命令需在业务 uv 工程初始化后执行；当前文档校验不等于运行环境已就绪。

## Linux 上使用 Codex CLI 与强制镜像

新版起步步骤、模板复制命令和可直接粘贴的开发指令见 [uv 镜像模板与 Linux 使用说明](specs/001-public-knowledge-collection/uv-template.md)。复制包必须包含 templates/。Linux 基础文档校验可执行 python3 tools/verify_sdd_documents.py；完整 Schema 正反例仍需 PowerShell 7.5+，执行 pwsh -File tools/verify_sdd_documents.ps1 -PythonPath python3。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 与 [NEXT-06](specs/001-public-knowledge-collection/evidence/next06-budget.md)、[NEXT-07](specs/001-public-knowledge-collection/evidence/next07-cn08-body.md)、[NEXT-08](specs/001-public-knowledge-collection/evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)）已交付，按 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md) 等待业务确认与 Linux 组件条件；保留 NEXT-04 环境阻塞及正式业务待决，T012/T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成，NEXT-10 仅澄清原始结构分块与跨段语篇组合的差异。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量、来源与旧格式组件缺口继续保留，不因范围收敛自动通过。


## spec 阶段追加记录

## 阶段续作补充

本阶段沿用原业务需求，DEV-010—DEV-012 新增测试停止条件、有限交付顺序及用户授权的守规真实测试，见 [阶段续作说明](specs/001-public-knowledge-collection/continuation.md)。T012/T019 的部分状态不改变业务完成标准，工程验证不自动冻结业务决定。


## 阶段三实施约束

[阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 将既有 DEV-012 预算、正文保真与可安装交付细化为 NEXT-06—NEXT-08，不改变原有 37 条业务需求。上述工程项已在阶段三实现并有证据，当前按 stage-four.md 处理交接与正式验收，不改变原业务范围。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成，NEXT-10 仅澄清原始结构分块与跨段语篇组合的差异。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量、来源与旧格式组件缺口继续保留，不因范围收敛自动通过。


## plan 阶段追加记录

## 阶段续作与验证收敛

当前已有采集工程实现，按 [阶段续作说明](specs/001-public-knowledge-collection/continuation.md) 的 DEV-010—DEV-012 推进有限交付项。适用测试通过后停止测试并交付，业务待决不触发无限夹具完善。用户允许遵守网站规则的有限真实测试；不重复请求同一授权，也不将其扩大为正式采集范围批准。历史测试数只代表对应记录，T012/T019 尚有真实组件/正式验收缺口。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 与 [NEXT-06](specs/001-public-knowledge-collection/evidence/next06-budget.md)、[NEXT-07](specs/001-public-knowledge-collection/evidence/next07-cn08-body.md)、[NEXT-08](specs/001-public-knowledge-collection/evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)）已交付，按 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md) 等待业务确认与 Linux 组件条件；保留 NEXT-04 环境阻塞及正式业务待决，T012/T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成，NEXT-10 仅澄清原始结构分块与跨段语篇组合的差异。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量、来源与旧格式组件缺口继续保留，不因范围收敛自动通过。


## tasks 阶段追加记录

## 当前续作优先级与状态更正

以 [阶段续作说明](specs/001-public-knowledge-collection/continuation.md) 为本阶段调度入口：NEXT-01/02 已完成，NEXT-03 工程试点已完成；NEXT-06/07/08 已完成；NEXT-09 交付清单与 NEXT-05A 决策确认栏已交付；NEXT-04 真实旧格式验证已完成（见下）；NEXT-10 已确认且最小实现已交付；NEXT-05B/C 的当前 raw 工作统一映射到 stage-five.md 的 S5-06，发布暂缓。NEXT 是现有任务子项，不改变 27 个 T 编号。

2026-09-13 更正：T012 已完成并勾选——DOCX/XLSX/CSV/JSON/XML 结构保留已有证据，真实 LibreOffice 24.2.7.2 下的 OLE2 DOC/XLS 转换、结构保留与失败路径已实测，原件追溯链路已由用例覆盖，见 `evidence/next04-legacy-office.md`；依赖组件的 5 项用例已于 2026-09-13 在目标 Linux 正常 shell 复跑通过（该文件 13 passed），能力已验证的事实得到用例级确认。T019：夹具级验证已完成，AT-014/AT-024 及正式业务验收尚缺，故保持部分完成。取消勾选不表示删除代码或重做既有有效测试。T003 依赖 T002 的已验证环境部分；T013 及后续已有工程结果在已验证格式上继续有效。T026 工程机制和有限探测可使用 T019 已有工程证据；正式来源验收仍依赖有关业务决定。T027 的 CLI 与交接准备可提前实施，但总体验收保留原依赖。

2026-09-11 续作进展：NEXT-01/NEXT-02 完成（正式 CLI 与 Linux 运行说明，见 `runbook.md`）；NEXT-03 产出 CN-08 试点卡并完成一次受限真实试点；NEXT-04 记录 LibreOffice 环境阻塞；NEXT-05 仍待 Q01/Q11/Q12/Q13 业务决定。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 与 [NEXT-06](specs/001-public-knowledge-collection/evidence/next06-budget.md)、[NEXT-07](specs/001-public-knowledge-collection/evidence/next07-cn08-body.md)、[NEXT-08](specs/001-public-knowledge-collection/evidence/next08-packaged-contracts.md)。（原文记 NEXT-04 受 Linux 组件权限阻塞；该阻塞已由 2026-09-13 的真实转换验证关闭。）NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)）已交付；NEXT-04 的真实旧格式验证已于 2026-09-13 完成（T012 勾选），剩余正式业务待决见 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md)。T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成；NEXT-04 真实旧格式验证与 T012 勾选已完成（`evidence/next04-legacy-office.md`）；NEXT-10 已按用户决定实现独立结构/div 空行最小分块，无需再确认。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量与来源缺口继续保留，不因范围收敛自动通过。

2026-09-13 本轮进展（按站发现抽象、运行时起始日期、最小结构分块；不改变 27 个 T 编号）：

- T005/T015：新增发现策略抽象与 `--start-date`（`src/crawler/discover/strategies.py`、`src/crawler/schedule/scope.py`），
  贯通发现、采集记录、失败账与恢复；CN-08/CN-01/CN-04 已有限线上验证，日期边界与恢复原范围有夹具用例。
- T010/T013：新增分块抽象与最小 dummy（`src/crawler/normalize/segmenter.py`），保留既有 HTML/Office/PDF 处理能力；
  `extraction_method` 记 `<基础>+structural_blank_line_v1`。正式质量阈值仍 deferred。
- T026：18 来源逐站状态与线上登记见 [evidence/t026-eighteen-sources.md](specs/001-public-knowledge-collection/evidence/t026-eighteen-sources.md)
  与 [evidence/logs/t026-round6-limited.txt](specs/001-public-knowledge-collection/evidence/logs/t026-round6-limited.txt)；第 10—41 轮续作补齐逐站适配
  （站点自身列表端点作入口、`list_link_rewrite` 等价形态改写、`attachment_pattern` 附件限幅、`date_selector`
  发布日期），当前为已实现并验证 9 个、实现待验证 0 个、访问受限 9 个、未完成 0 个。**任务仍是部分完成**：
  受限来源的访问方式与域名别名（Q12/Q13）及正式全范围验收未完成，不勾选正式完成；交付基线全量回归
  406 passed（[evidence/logs/t026-full-pytest.txt](specs/001-public-knowledge-collection/evidence/logs/t026-full-pytest.txt)），开发数据根 `crawl check`
  为 manifest=63、documents=52、blocks=2452、failures=2、raw_files=59、追溯 100%。
- T019/T027：raw 留存、失败账与追溯仍是部分完成（夹具与有限样本级），正式全范围验收不因本轮推进自动通过。
- 阶段五（61e34d8 后复核）：当前任务按 [stage-five.md](specs/001-public-knowledge-collection/stage-five.md)。S5-01/03/04/06 可执行，S5-02 分因处理；S5-05/07 暂缓，不作为前置。没有新增第 28 个 T 任务，不重做现有抽象和最小分块。
- 阶段五实施（2026-09-13）：S5-01/03/04/06 已完成工程实施并通过离线夹具验证（新增 13 项用例，
  全量回归 419 passed），见 [evidence/stage-five-raw-completeness.md](specs/001-public-knowledge-collection/evidence/stage-five-raw-completeness.md)、
  [evidence/logs/stage-five-full-pytest.txt](specs/001-public-knowledge-collection/evidence/logs/stage-five-full-pytest.txt)。对应 T005/T006/T007/T015/T016
  的能力补齐记录在案；T019/T026/T027 仍为**部分完成**（正式验收与来源决定未完成），不因本轮勾选；
  T017/T018 的成果格式未变，S5-05（后处理质量）与 S5-07（发布运维）继续暂缓。


## constitution 阶段追加记录

## 阶段续作与验证收敛

当前已有采集工程实现，按 [阶段续作说明](specs/001-public-knowledge-collection/continuation.md) 的 DEV-010—DEV-012 推进有限交付项。适用测试通过后停止测试并交付，业务待决不触发无限夹具完善。用户允许遵守网站规则的有限真实测试；不重复请求同一授权，也不将其扩大为正式采集范围批准。历史测试数只代表对应记录，T012/T019 尚有真实组件/正式验收缺口。

阶段二后续以 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 的当前状态为准，已完成 NEXT-01/02 不回到 READY。工程预算必须由实际程序执行，结果数上限不等同请求数上限；历史通过证据不得扩大到未验证的安装或正文质量范围。

当前阶段按 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md) 继续。NEXT-06—NEXT-08 已完成，不作为新一轮默认开发目标；正式业务和组件阻塞继续按证据保留。

## 当前范围补充（2026-09-13）

用户近期补充使本轮计划止于采集、标准化与分块交付；RAG 不作为本轮交付目标。沿用原始 blocks，跨段组合未明确前不修改业务契约。原输入及范围外追踪保留，详见 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md)。


## acceptance.md 阶段追加记录

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 与 [NEXT-06](specs/001-public-knowledge-collection/evidence/next06-budget.md)、[NEXT-07](specs/001-public-knowledge-collection/evidence/next07-cn08-body.md)、[NEXT-08](specs/001-public-knowledge-collection/evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)）已交付，按 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md) 等待业务确认与 Linux 组件条件；保留 NEXT-04 环境阻塞及正式业务待决，T012/T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成，NEXT-10 仅澄清原始结构分块与跨段语篇组合的差异。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量、来源与旧格式组件缺口继续保留，不因范围收敛自动通过。

## R1—R6 缺陷验收（2026-09-14）

六项故障场景与完成标准统一见 [阶段六](specs/001-public-knowledge-collection/stage-six.md)，映射现有 S5/T/AT，不新建重复的全量验收清单。历史通过项保持证据时点，静态审查发现的未覆盖场景先复现再修复。状态损坏、正文待续、恢复身份串联、归档冲突及游标/入队中断均不得由“队列全清”或 raw 哈希通过替代。最终覆盖、对象处置、追溯与状态解析完整性分别报告。


## tech-stack.md 阶段追加记录

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 与 [NEXT-06](specs/001-public-knowledge-collection/evidence/next06-budget.md)、[NEXT-07](specs/001-public-knowledge-collection/evidence/next07-cn08-body.md)、[NEXT-08](specs/001-public-knowledge-collection/evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)）已交付，按 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md) 等待业务确认与 Linux 组件条件；保留 NEXT-04 环境阻塞及正式业务待决，T012/T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。


## traceability.md 阶段追加记录

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](specs/001-public-knowledge-collection/stage-three.md) 与 [NEXT-06](specs/001-public-knowledge-collection/evidence/next06-budget.md)、[NEXT-07](specs/001-public-knowledge-collection/evidence/next07-cn08-body.md)、[NEXT-08](specs/001-public-knowledge-collection/evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](specs/001-public-knowledge-collection/delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](specs/001-public-knowledge-collection/decision-requests.md)）已交付，按 [阶段四交付收口](specs/001-public-knowledge-collection/stage-four.md) 等待业务确认与 Linux 组件条件；保留 NEXT-04 环境阻塞及正式业务待决，T012/T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](specs/001-public-knowledge-collection/scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成，NEXT-10 仅澄清原始结构分块与跨段语篇组合的差异。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量、来源与旧格式组件缺口继续保留，不因范围收敛自动通过。
