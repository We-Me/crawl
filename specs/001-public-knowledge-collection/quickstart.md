# 文档使用与后续开发交接指南

更新：2026-09-14。当前为阶段七原型收尾：保留前轮已实施成果，仅修复后审查三个代码缺口；本轮尚未完成验证。旧版完整内容保存在 [SDD 历史说明](../../SDD历史说明.md)，不再作为开发入口。

## 继续现有项目

1. 阅读根目录 [AGENTS.md](../../AGENTS.md)、[SDD 说明](../../SDD文档说明.md)、[项目原则](../../.specify/memory/constitution.md) 和 [范围决定](raw-first-development.md)。
2. 按 [阶段七](stage-seven.md) 选择明确交付物；阶段五/六仅按需查已有方案和证据。不要重做来源选择、最小分块、CLI 或 LibreOffice 安装。
3. 按需核对 [spec](spec.md)、[plan](plan.md)、[tasks](tasks.md)、[数据模型](data-model.md) 和 [结构对照](structure-comparison.md)。外部问题按 [人工补齐清单](manual-follow-up.md) 交接，不阻断本轮；Q 编号不是重新确认全部业务的清单。
4. 复用 [tech-stack](tech-stack.md) 中 CPython 3.9.25 与现有 uv 锁文件、登记镜像。配置及命令以 [runbook](runbook.md) 为准，先 `uv sync --locked`，按实际验证范围启用需要的依赖组；不使用空模板覆盖现有 pyproject.toml。
5. 完成对应最小验证后更新证据；阶段七退出条件满足即交付。失败账允许保留可控异常，仍须可查询、有限重试、离线/人工处理且不伪造成功。

## 环境、目录与迁移

目标 Linux/WSL 的 LibreOffice 24.2.7.2 已有真实旧格式转换证据，见 [NEXT-04](evidence/next04-legacy-office.md)。新机器按运行说明核验环境，不将旧缺组件记录当成当前阻塞。

继续开发应克隆完整仓库，保留源码、测试、锁文件、配置样例、docs/ 原始输入和全部 SDD 文件。不要复制真实 .env、.venv、开发 data/。开发数据默认与 src/ 同级，正式运行数据根通过环境变量配置，详见 [项目目录](project-startup.md)。只有创建独立新项目时才使用 [uv 模板](uv-template.md)，并重新明确范围。

## 文档验证

PowerShell 7.5+、Python 3.9+ 下，在项目根目录运行：

```powershell
./tools/verify_sdd_documents.ps1
# Python 未在 PATH 时指定解释器：
./tools/verify_sdd_documents.ps1 -PythonPath 'C:/path/to/python.exe'
```

Linux 基础结构检查：

```bash
python3 tools/verify_sdd_documents.py
# 安装 PowerShell 7.5+ 后可执行完整 Schema 正反例：
pwsh -File tools/verify_sdd_documents.ps1 -PythonPath python3
```

校验只读取文档、契约、虚构样例和原始输入指纹，不访问业务站点，不代表业务环境或爬虫验收通过。Python 校验脚本不需要新增包。

## 维护与交付

正式 crawl CLI 已存在，安装、采集、预算、恢复和校验命令使用 [运行说明](runbook.md)。阶段七仅补齐当前错误处置缺口并写入实际验证过的命令，不重新设计操作入口。

需求和数据语义变动先记录依据，再同步受影响 spec/plan/tasks/acceptance/契约；不改四份原始输入，不重跑 build_sdd_documents.py 覆盖维护结果。阶段七交付报告按该阶段文档生成，软件成品结论与某来源窗口数据完整性分别报告，历史证据不改写。
