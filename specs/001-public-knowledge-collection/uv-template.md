# uv 镜像环境模板与 Linux 使用说明

状态：已提供可复制的环境模板，业务依赖和完整环境尚未选定或验证。用户明确项目必须使用镜像源；附件 pyproject.toml 仅作为配置参考，其模型项目名称、Python 3.10 下限、PyTorch/CUDA、TensorFlow 等依赖不属于本项目需求。

## 模板内容

复制 [pyproject.toml 模板](../../templates/uv/pyproject.toml) 到新项目根目录。已有 pyproject.toml 时合并配置，禁止覆盖。模板保留 Python >=3.9,<3.10、空运行及开发依赖、正式稳定版本策略和清华镜像；不引用不存在的 README，不虚构锁文件或已验证补丁版本。

模板的 package=false 用于 T002 环境选型起步，不安装项目自身；它不是最终业务打包方案。T003 选择兼容构建后端并配置 src 包发现后，移除 package=false，验证可编辑安装及常规安装，再报告业务包可导入。空环境同步成功不等于完整环境通过。

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

4. T002 确定可用解释器和当前范围依赖后执行锁定与同步；无锁文件时先 lock，不能直接 sync --locked。下面假定已经有 Python 3.9，不允许自动下载替代解释器：

```bash
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

该命令只检查变量注入，不启动爬虫。真实入口由后续实现提供；开发默认为 ./data，生产设置 CRAWL_ENV=production 与绝对 CRAWL_DATA_DIR，完整路径规则见 [项目起步说明](project-startup.md)。

## 环境验收记录

T002/T003 记录镜像名称/URL、uv 版本、Python 实际补丁版本、目标平台、依赖组、锁文件来源和验证命令。需证明：项目配置未被外部源覆盖；使用登记镜像完成实际必要依赖解析与安装；镜像失败不回退；干净环境可通过锁文件复现；src 包安装及代表性业务样本通过。当前这些运行验收均未执行，模板静态检查不替代环境验收。
