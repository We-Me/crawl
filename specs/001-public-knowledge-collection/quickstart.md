# 文档使用与后续开发交接指南

版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

当前工作区交付的是 SDD 文档、虚构契约样例与固定夹具上的采集实现。没有爬虫命令、已运行的站点任务、索引或边缘软件。以下步骤先用于审查，再用于后续开发交接。

2026-09-11 状态：采集范围 T003—T019 已实现并通过 310 项测试（无 CLI、无真实站点任务；AT-014/AT-024 因 Q11 未决保持 blocked），领域与真实来源任务仍待相应 Q 项决策。任务勾选见 [tasks.md](tasks.md)，证据索引见 [evidence/README.md](evidence/README.md)。

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

复制时一并带上根目录 [.env.example](../../.env.example) 与 [.gitignore](../../.gitignore)，不复制真实 .env、.venv 或开发 data/。按 [项目起步说明](project-startup.md) 创建 src/crawler/、配置包安装和统一 settings 接口。开发默认 data/ 与 src/ 同级，正式运行用环境变量指定绝对数据根。说明中的命令需在业务 uv 工程初始化后执行；当前文档校验不等于运行环境已就绪。

## Linux 上使用 Codex CLI 与强制镜像

新版起步步骤、模板复制命令和可直接粘贴的开发指令见 [uv 镜像模板与 Linux 使用说明](uv-template.md)。复制包必须包含 templates/。Linux 基础文档校验可执行 python3 tools/verify_sdd_documents.py；完整 Schema 正反例仍需 PowerShell 7.5+，执行 pwsh -File tools/verify_sdd_documents.ps1 -PythonPath python3。
