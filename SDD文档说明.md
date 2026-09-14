# 公开知识采集项目 SDD 文档说明

更新：2026-09-14。当前开发阶段：**阶段七原型已交付，转入实际问题驱动维护**。后审查三个代码缺口（P7-01—P7-03）已修复并验证（实现提交 `e4e5c39`，见 [原型收尾证据](specs/001-public-knowledge-collection/evidence/stage-seven-prototype.md)）；保留 c752807 及以前的实现与测试成果，前轮完成判断见 [阶段七历史记录](specs/001-public-knowledge-collection/stage-seven-history.md)。

## 当前开发入口

从 [AGENTS.md](AGENTS.md) 开始，阅读 [用户范围决定](specs/001-public-knowledge-collection/raw-first-development.md)，然后仅按 [阶段七](specs/001-public-knowledge-collection/stage-seven.md) 选择任务和验收。spec/plan/tasks 保存需求、设计、编号和证据，不另维护一套阶段待办。

阶段七原型收尾已完成：后审查三个代码问题（P7-01—P7-03）已修复验证，三条原型退出条件满足，不再执行旧 S7-01/02/03 待办。外部访问、代理、许可及缺失数据按 [人工补齐清单](specs/001-public-knowledge-collection/manual-follow-up.md) 交接，不主动联网诊断或扩站。本轮开发已结束，转入实际问题驱动维护；不以穷尽所有异常、修复全部 issue 或清空失败账作为完成条件。关键原件留存、追溯和状态真实性仍须保证，可控异常允许留账交付。软件可交付与某来源某时间窗口的数据完整性分别说明。

## 当前范围与环境

- 范围：登记的全部 18 来源、运行时起始时间、按站发现、采集归档、标准化、独立结构块/div 空行的最小分块和追溯。RAG、高级后处理质量及最终发布部署暂缓。
- 已有代码、正式 crawl CLI、uv 锁定环境、来源适配、分页/队列、增量与恢复能力；18 来源都有登记不等于全部来源已通过数据完整性验收。
- 环境沿用 tech-stack 中的 CPython 3.9.25 与现有依赖，使用登记镜像和 uv；不重新选框架或复制空模板覆盖锁文件。目标 Linux/WSL 的 LibreOffice 已完成组件及真实转换验证，T012 不再等待安装。
- 阶段六的定向 103 passed、完整回归 492 passed 是对应提交的历史证据；阶段七前轮证据（复现 23 failed → 定向 87 passed、全量 514 passed）保留其提交范围。原型收尾（`e4e5c39`）定向 4/8/2 项、全量 523 passed 与扩展闭环通过，见 [原型收尾证据](specs/001-public-knowledge-collection/evidence/stage-seven-prototype.md)；业务数据验收状态仍按 T019/T026/T027 分别记录，不因软件交付改变。

## 阶段记录及职责

| 阶段 | 已有成果或记录 | 当前用途 |
| --- | --- | --- |
| 初始规格与起步 | 四份业务输入、需求/契约/任务、Python/uv 初始化及早期采集实现 | 保留依据和选型，不重新生成工程 |
| 阶段二 | 正式 CLI、运行说明、有限单站试点；见 continuation 历史 | 已交付工程能力，不重做 |
| 阶段三 | 请求预算、正文边界、安装包契约；见 stage-three | 历史实现与证据 |
| 阶段四 | 交接清单与决策记录；旧格式转换在后续完成 | 保留阶段事实；原“等安装/等全部决定”不再适用 |
| 阶段五 | 发现归档、游标、队列、附件推进等实现 | stage-five 保存摘要，stage-five-history 保存运行过程 |
| 阶段六 | R1—R6 修复、故障验证及历史数据只读评估 | stage-six 保存已提交成果；后审查发现已由阶段七修复 |
| **阶段七原型交付** | **P7-01—P7-03 三项修复（`e4e5c39`）；外部错误转人工** | **原型已交付，三条退出条件满足；转实际问题驱动维护，入口仍为 stage-seven** |

不因阶段编号推进修改历史测试日志，不将旧“工程完成/队列清空”解释为全站完整。T019/T026/T027 的业务数据验收与本轮基础软件交付分别记录，范围外任务不阻塞基础成品。

## 文档导航

| 文件 | 职责 |
| --- | --- |
| [项目原则](.specify/memory/constitution.md) / [需求规格](specs/001-public-knowledge-collection/spec.md) | 需求依据、治理和当前适用边界 |
| [阶段七](specs/001-public-knowledge-collection/stage-seven.md) | 当前代码收尾、人工补齐边界与原型退出条件 |
| [技术设计](specs/001-public-knowledge-collection/plan.md) / [任务追踪](specs/001-public-knowledge-collection/tasks.md) | 模块职责、原 T 编号与实施证据 |
| [技术栈](specs/001-public-knowledge-collection/tech-stack.md) | 已验证环境、依赖选择及升级约束 |
| [起步与目录](specs/001-public-knowledge-collection/project-startup.md) / [uv 模板](specs/001-public-knowledge-collection/uv-template.md) | 环境变量、数据根和新项目模板；现有项目复用配置 |
| [数据模型](specs/001-public-knowledge-collection/data-model.md) / [结构对照](specs/001-public-knowledge-collection/structure-comparison.md) / [契约](specs/001-public-knowledge-collection/contracts/README.md) | 基础字段、组织扩展及兼容性 |
| [验收规范](specs/001-public-knowledge-collection/acceptance.md) / [证据索引](specs/001-public-knowledge-collection/evidence/README.md) | 区分验收定义、历史测试与本轮实际结果 |
| [当前决定](specs/001-public-knowledge-collection/decision-requests.md) / [原 Q 编号](specs/001-public-knowledge-collection/clarifications.md) | 已确认决定和真正需要外部输入的局部事项 |
| [运行说明](specs/001-public-knowledge-collection/runbook.md) / [交接指南](specs/001-public-knowledge-collection/quickstart.md) | 实际命令、环境与继续开发方法 |
| [交付清单](specs/001-public-knowledge-collection/delivery-inventory.md) / [限制报告](specs/001-public-knowledge-collection/limitations-report.md) | 已交付资产及有范围的限制；已按阶段七交付结果更新 |
| [来源依据](specs/001-public-knowledge-collection/sources.md) / [追踪矩阵](specs/001-public-knowledge-collection/traceability.md) | 四份输入指纹和需求关联 |
| [阶段六](specs/001-public-knowledge-collection/stage-six.md) / [阶段五](specs/001-public-knowledge-collection/stage-five.md) / [阶段四](specs/001-public-knowledge-collection/stage-four.md) / [阶段三](specs/001-public-knowledge-collection/stage-three.md) / [早期续作](specs/001-public-knowledge-collection/continuation.md) | 按需追溯，不作当前调度 |
| [SDD 历史说明](SDD历史说明.md) | 原根说明、交接指南和分散阶段追加记录 |

## 复制与继续开发

继续本项目优先克隆完整 Git 仓库，保留 src/、tests/、tools/、pyproject.toml、uv.lock、.python-version、AGENTS.md、docs/、.specify/、specs/、templates/、.env.example、.gitignore 和根目录说明。不要复制真实 .env、.venv 或开发 data/；运行数据如需迁移另行按运行说明处理。

仅新建独立规格项目时，才复制上述文档/契约/模板和校验工具而不带本项目业务代码，并在新项目中重新明确范围。不要把这份“规格模板复制”清单用于恢复现有可运行项目。tools/build_sdd_documents.py 是初始生成工具，不得重跑覆盖已维护文档。

## 文档验证

在项目根目录执行 `pwsh -File tools/verify_sdd_documents.ps1`，或按交接指南指定 Python 路径；Linux 基础结构检查可用 `python3 tools/verify_sdd_documents.py`。验证包含本地链接、编号、四份输入指纹、虚构数据引用及契约样例，不访问业务站点，不等同于软件或数据验收。

四份业务输入仍在 docs/，原始内容不随阶段变更改写。SDD 采用规格驱动开发组织方式；当前用户补充决定与工程约束独立记录，不冒充原文要求或外部认证。
