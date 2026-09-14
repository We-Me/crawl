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
