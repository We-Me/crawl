# uv 镜像环境模板与 Linux 使用说明

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。第四阶段整体仍未完成（T019/T026/T027 与正式业务待决）。下文早期缺组件/权限记录按历史时点理解，不再作为等待安装的理由。

> 已开发项目请先阅读 [阶段续作说明](continuation.md)。当前根目录已有 pyproject.toml、uv.lock 和 src/，不要复制空模板覆盖或重做初始化；下文起步命令仅用于新空项目。


状态：模板已于 2026-09-11 合并进业务工程并完成起步环境验证，记录见 [evidence/T002-selection.md](evidence/T002-selection.md)、[evidence/T003-environment.md](evidence/T003-environment.md)；当前范围依赖（含 PDF/OCR/Office/结构数据）已选定并锁定，调度与监控依赖待对应任务选定，见 [evidence/T010-T013-parsers.md](evidence/T010-T013-parsers.md)。用户明确项目必须使用镜像源；附件 pyproject.toml 仅作为配置参考，其模型项目名称、Python 3.10 下限、PyTorch/CUDA、TensorFlow 等依赖不属于本项目需求。

## 模板内容

复制 [pyproject.toml 模板](../../templates/uv/pyproject.toml) 到新项目根目录。已有 pyproject.toml 时合并配置，禁止覆盖。模板保留 Python >=3.9,<3.10、空运行及开发依赖、正式稳定版本策略和清华镜像；不引用不存在的 README，不虚构锁文件或已验证补丁版本。

模板的 package=false 用于 T002 环境选型起步，不安装项目自身；它不是最终业务打包方案。T003 已选择 hatchling 并配置 src 包发现、移除 package=false，可编辑安装与普通安装均验证通过，见 [evidence/T003-environment.md](evidence/T003-environment.md)。空环境同步成功不等于完整环境通过。

## 必须使用镜像的规则 DEV-009

项目 Python 包解析与安装必须使用在项目配置中明确登记的 HTTPS 镜像，当前默认采用附件提供的清华源。以下配置必须保留，或以有记录且验证过的其他镜像替换：

```toml
[[tool.uv.index]]
name = "tsinghua"
url = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/"
default = true
```

default=true 会替换 uv 内置的 PyPI 默认索引，避免未命中镜像时自动退回官方 PyPI。镜像的使用方式依据 [清华镜像帮助](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)；索引替换和优先级依据 [uv 索引文档](https://docs.astral.sh/uv/concepts/indexes/)。

执行 uv add、lock、sync、run 前，核查命令参数、进程中的 UV_INDEX/UV_DEFAULT_INDEX 及旧式 UV_INDEX_URL/UV_EXTRA_INDEX_URL，以及其他 uv 配置文件没有引入未登记源。项目根不另建与 pyproject.toml 冲突的 uv.toml；不能用 --no-config 或临时官方索引绕过规则。保留 first-index 策略。

镜像连接失败、同步延迟或缺包时先排查；必要时记录原因、替代镜像和验证结果后切换镜像，不静默回退官方源，也不能因此提高 Python 版本。镜像变更后重新解析锁文件，核查 registry、sdist/wheel URL 及关联传递依赖来源，再执行 uv sync --locked；旧锁文件可能仍指向旧站点，不能仅改配置就宣称迁移完成。缓存可能来自以前的源，来源验收须使用独立空缓存并保留实际日志，避免把缓存命中误报为镜像下载成功。

当前不需要附件中的 CUDA 专用源。未来确需专用包镜像时，登记镜像，设置 explicit=true，并通过 tool.uv.sources 仅绑定所需包；核实平台、Python 和相关系统组件兼容性。不能通过未登记的直接 URL、Git 依赖或下载脚本绕过镜像要求。自有本地项目源码不属于外部包镜像下载。

镜像配置是包管理设置，保存在 pyproject.toml；.env 保存 CRAWL_ENV/CRAWL_DATA_DIR 等应用运行配置。不依赖 uv run --env-file 来配置 uv add/lock/sync 的包源，也不把源凭据写入模板或锁文件。

## 镜像覆盖范围

PyPI 镜像不控制 uv 自身安装、Python 解释器下载、操作系统软件包或模型文件。不能声称上述索引配置让所有网络访问都经过镜像。需要下载解释器时，单独配置并验证适配 python-build-standalone 目录结构的 UV_PYTHON_INSTALL_MIRROR；不能把 PyPI simple 地址填进去，参见 [uv 解释器镜像设置](https://docs.astral.sh/uv/reference/settings/#python-install-mirror)。当前没有提供或验证解释器镜像地址。

目标 Linux 已有可用 Python 3.9 时可交由 uv 使用；否则先确定可用解释器获取方式。若运行环境要求所有下载均走镜像，必须先补齐解释器、uv 工具及系统组件的镜像/离线供应方案，再进行相应下载，不直接执行默认下载命令。

## Linux 起步步骤

1. 复制 AGENTS.md、SDD文档说明.md、docs/、specs/、.specify/、templates/、tools/、.env.example 和 .gitignore，保持结构。不复制真实 .env、.venv 和开发 data/。准备 Codex CLI、uv 和可用解释器；本说明不假定机器已安装这些工具。
2. 在新项目根目录执行下面的模板准备命令。已有文件会保留；已有 pyproject.toml 必须核查并合并镜像、Python 与稳定版本配置，不能仅因文件存在而跳过核查。

```bash
test -e pyproject.toml || cp templates/uv/pyproject.toml pyproject.toml
test -e .env || cp .env.example .env
uv --version
codex
```

3. 给 Codex 以下启动指令：

```text
按 AGENTS.md 和入口列出的 SDD 文档开始开发，目标平台是当前 Linux。
先检查 templates/uv/pyproject.toml 和 uv-template.md，合并镜像配置，
遵守 DEV-001—DEV-009；Python 包必须走登记镜像，不回退官方 PyPI。
优先 Python 3.9，成熟稳定依赖按需增加；下载失败不能作为升级依据。
先处理当前任务涉及的待决项，并完成 T002 选型与样本验证，
再按 T003 配置 src 包安装，移除起步模板的 package=false。
业务代码放 src/，开发结果放同级 data/，实现统一环境变量配置接口。
按任务依赖继续开发，每项完成后验收并记录证据，不重跑初始文档生成脚本。
```

4. T002 确定可用解释器和当前范围依赖后执行锁定与同步；无锁文件时先 lock，不能直接 sync --locked。若目标机器没有可用的 Python 3.9，先用 uv 安装并交给 uv 管理；2026-09-11 已按用户指令在本机执行 `uv python install 3.9`（结果 3.9.25，证据见 [evidence/logs/t002-python-install.txt](evidence/logs/t002-python-install.txt)）。该命令走 uv 默认解释器源（python-build-standalone 目录结构，非 PyPI 镜像），与 PyPI 包源是两件事，来源校验按上文分别进行；后续 lock/sync/run 加 `--no-python-downloads`，避免自动下载替代解释器：

```bash
uv python install 3.9
uv python pin 3.9
uv lock --python 3.9 --no-python-downloads
uv sync --locked --no-python-downloads
uv run --locked --no-python-downloads python --version
```

实际 Python 补丁版本经完整验证后写入 .python-version；若版本升级有充分依据，同步 requires-python 和上述命令。非默认依赖组及可选项按实际交付添加。T003 配置构建后端后需重新锁定与同步。

5. 业务工程和锁文件就绪后，检查开发变量注入：

```bash
uv run --locked --env-file .env python -c "import os; print(os.environ.get('CRAWL_DATA_DIR'))"
```

该命令只检查变量注入，不启动爬虫。正式业务入口已实现为 `crawl`（见 [运行说明](runbook.md)）；开发默认为 ./data，生产设置 CRAWL_ENV=production 与绝对 CRAWL_DATA_DIR，完整路径规则见 [项目起步说明](project-startup.md)。

## 环境验收记录

T002/T003 记录镜像名称/URL、uv 版本、Python 实际补丁版本、目标平台、依赖组、锁文件来源和验证命令。需证明：项目配置未被外部源覆盖；使用登记镜像完成实际必要依赖解析与安装；镜像失败不回退；干净环境可通过锁文件复现；src 包安装及代表性业务样本通过。

2026-09-11 执行结果：登记镜像 tsinghua（`https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/`）；uv 0.11.28；CPython 3.9.25；平台 linux-x86_64-gnu；dev 组 pytest（运行依赖当前为空）；锁文件与制品 URL 全部登记镜像来源，独立空缓存解析与安装；可编辑及普通安装后从工程外导入通过；固定样本 11 项与项目测试 38 项通过。证据见 [evidence/T002-selection.md](evidence/T002-selection.md)、[evidence/T003-environment.md](evidence/T003-environment.md)。后续新增真实业务依赖时按同一流程复核来源后再报告完整环境。

2026-09-11 交付态复核：T010—T013 引入 PDF/OCR/Office 运行依赖后，上段数字已不代表当前锁文件，故重做来源核查与空缓存复现。当前 `uv.lock` 的 40 个 registry 包与 202 条制品 URL 全部指向登记清华镜像，无 git/path/URL 依赖；在只含交付文件（排除 .venv、.git、data）的干净副本中用 `/tmp/crawl-repro-cache` 空缓存执行 `uv sync --locked --no-python-downloads` 成功（下载日志出现 112 条清华索引 URL、0 次 pypi.org），解释器为 uv 管理的 3.9.25，随后 `uv run --locked --no-python-downloads pytest -q` 得 262 passed。证据见 [evidence/logs/t019-lock-provenance.txt](evidence/logs/t019-lock-provenance.txt)。后续再增依赖时按同一流程复核。
