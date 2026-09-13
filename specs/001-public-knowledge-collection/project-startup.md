# 项目起步与运行目录配置

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。第四阶段整体仍未完成（T019/T026/T027 与正式业务待决）。下文早期缺组件/权限记录按历史时点理解，不再作为等待安装的理由。

> 已开发项目请先阅读 [阶段续作说明](continuation.md)。当前根目录已有 pyproject.toml、uv.lock 和 src/，不要复制空模板覆盖或重做初始化；下文起步命令仅用于新空项目。


状态：用户已确定业务代码放在 src/、开发结果目录与 src/ 同级，且需要可配置的正式运行目录。本文将其具体化为项目约束；2026-09-11 已初始化 src/crawler 与起步环境，settings 接口按本文实现并通过 CFG-01—CFG-09 全部验证（CFG-01—CFG-05、CFG-09 见 [evidence/T003-environment.md](evidence/T003-environment.md)，CFG-06—CFG-08 见 [evidence/T019-acceptance.md](evidence/T019-acceptance.md)）。

## 实现方式与依据

采用 Python 的 src 布局：可导入业务包放在 src/crawler/，后续被选中的领域模块放在 src/knowledge/；tests/ 和 tools/ 保留在根目录，分别放测试与工程辅助脚本。src 是源码容器，不是需要导入的业务包。需用选定且兼容 Python 3.9 的构建后端配置包发现与可编辑安装，不依赖手工修改 sys.path 或 PYTHONPATH 才能运行。[Python Packaging 指南](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)

配置采用“进程环境变量作为应用接口、.env 作为开发启动时的便捷来源”。uv 已支持显式 --env-file 加载，并使进程已有变量优先；程序只读取 os.environ，经统一配置入口校验。单纯为了读取这两个变量，不额外引入 dotenv 或大型配置框架。[uv 环境变量文件说明](https://docs.astral.sh/uv/concepts/configuration-files/#environment-variable-files)

已比较 python-dotenv：它可在应用启动时读取文件且默认不覆盖已有变量，适合必须由应用本身加载文件的场景。本项目已有 uv，暂不增加这项依赖；若以后确需非 uv 启动且应用自行读文件，再按成熟依赖规则选定兼容版本，使用明确文件路径并保持环境变量优先。[python-dotenv 项目说明](https://pypi.org/project/python-dotenv/)

## 目录约定

```text
项目根目录/
├── AGENTS.md
├── docs/                         四份业务输入
├── specs/                        规格、契约与验收
├── .specify/memory/               项目原则
├── src/
│   ├── crawler/                   采集业务包，初始化时创建 __init__.py
│   │   ├── config/settings.py     统一应用配置入口，计划文件
│   │   └── discover/ fetch/ parser/ normalize/ output/ …
│   └── knowledge/                仅在领域范围获选后创建
├── tests/                        固定样本、配置和业务测试
├── tools/                        文档校验等工程辅助工具
├── data/                         开发默认结果目录，与 src/ 同级
│   ├── raw/
│   ├── manifests/
│   ├── normalized/
│   └── logs/
├── .env.example                  已提供，可复制的配置说明
├── .env                          开发者自行创建，不纳入版本控制
├── .gitignore                    已提供
├── pyproject.toml                T002/T003 创建
├── uv.lock                       uv 生成，需交付
└── .python-version               固定实测解释器
```

本次已有文档、配置示例及忽略规则；树中的业务包、data/ 和 uv 工程配置是后续初始化结构，不表示它们已经实现。S1 中的 crawler/ 是原文推荐目录，本项目根据用户补充把它放到 src/ 内，原文转录和四份输入保持原样。

## 配置契约

| 变量 | 取值与默认 | 规则 |
| --- | --- | --- |
| CRAWL_ENV | development 或 production；默认 development | 其他值以及显式空字符串报配置错误；生产启动必须显式设 production |
| CRAWL_DATA_DIR | 开发未设置时为项目根目录下 data/ | 开发允许绝对路径或相对项目根的路径；生产必须显式配置绝对路径；显式空值报错而不回退 |

应用可见优先级是：进程已有环境变量 > 通过 uv 显式加载的 .env 值 > 应用默认值。生产直接由服务、容器或调度器注入环境变量即可，不要求存在 .env。仅有 .env 文件不会让 os.environ 自动出现这些变量；开发命令必须带 --env-file，或由启动器显式设置 UV_ENV_FILE。首版使用单一显式文件，不增加隐式向上搜索、多文件覆盖或额外业务 CLI 配置优先级。

应用路径解析以一次构建的配置对象为准，不由各模块分别读取环境变量或硬编码 data/。计划接口是 src/crawler/config/settings.py 中的 load_settings(environ, project_root=None)，返回运行模式和解析后的绝对 data_dir；这是待实现的内部接口，不是 HTTP API。测试可注入映射及项目根。写入、补抓、重新解析、校验及日志组件都接收同一配置对象或派生目录。

开发启动入口从自身源码所在位置识别同时含 pyproject.toml 和 src/crawler/ 的工程根，再传入 project_root；不能把 Path.cwd() 当隐式数据根，不能按 .env 所在目录解释数据路径。打包安装后若没有可识别的源码工程根，未配置路径或相对路径必须明确报错，不能猜测 site-packages 附近是项目根。显式绝对路径不需要源码工程根，便于正式部署。

路径值只接受本机文件系统路径，不将 URL 当目录，不隐式执行 shell 或展开命令。先校验空值和格式，再用 pathlib 归一为绝对路径。根目录变更通过配置完成；不把生产路径写入源码。正式配置建议使用当前平台格式的绝对路径，Windows 的本机盘符和 Linux 路径不能混用。

## 启动前校验与数据可搬迁

解析后验证目标不是文件、可创建且可写；创建时处理实际权限错误，不能仅凭字符串或 exists 检查就报告可用。默认开发 data/ 可自动创建，显式配置的合法目录也可按需创建；失败应在发起抓取前返回明确错误，不默默写入其他目录。不自动清空、删除或搬迁已有内容。

写出的 raw_path 继续是相对于当前数据根的路径，例如 raw/DEMO/2026-09-11/html/main.html，不含 data/ 前缀，也不保存机器绝对路径。实际读取位置为 data_dir / raw_path，规范化后验证仍位于数据根内，防止 ..、绝对路径或符号链接导致越界。数据根本身可位于工程外，这与其内部记录不得越界是两层规则。不得因开发目录叫 data/ 就在多个模块拼出固定项目路径。

变更 CRAWL_DATA_DIR 只改变本次读写的数据根，不自动搬迁旧数据。需要继承旧数据时另行复制完整 raw/、manifests/、normalized/、logs/ 并校验引用和哈希；相对 raw_path 不应因目录搬迁重写。交付的根仍是所选数据根，正式运行目录的实际挂载路径由部署时设置。

日志可记录运行模式、解析后的数据根以及是否采用默认值，便于诊断；不得为了调试打印整个环境或 .env 内容。来源白名单、关键词等结构化站点配置仍使用来源配置文件，不将它们全部塞入环境变量。

## 新项目起步顺序

1. 复制 AGENTS.md、docs/、.specify/、specs/、templates/、校验脚本、SDD文档说明.md，并包含隐藏的 .env.example 和 .gitignore。不要复制开发机器的 .env、.venv 或真实 data/ 作为程序依赖。
2. 按当前范围处理业务待决项，按 tech-stack.md 使用 uv，优先验证 Python 3.9。T002 可在隔离的选型工程建立候选 uv 配置并使用小样本试验；T003 将已验证配置整理成正式工程，避免两任务互相等待。
3. 按上述 src 结构配置实际包发现和安装，创建统一 settings 接口。先使用 [uv 镜像模板](uv-template.md) 初始化配置；模板的 package=false 只供选型，T003 必须移除并补全构建后端，不能据此宣称 src 包已经可导入；补全选定后端配置后，通过 uv sync --locked 安装项目，再用 uv run --locked 验证实际包导入。
4. 若本地尚无 .env，将 .env.example 复制为 .env，修改其中的路径。现有文件不得自动覆盖；它只保存本机设置，不纳入版本控制。
5. 业务入口为 `crawl`；用 uv run --locked --env-file .env crawl … 执行实际命令（命令面见 [运行说明](runbook.md)）。以下命令仅验证变量被注入，不启动爬虫，也不证明配置接口已实现：

```powershell
uv run --locked --env-file .env python -c "import os; print(os.environ.get('CRAWL_DATA_DIR'))"
```

该命令的前提是 uv 项目和锁文件已建立，且从项目根启动。若从别的目录运行，显式指定 --project 和 --env-file 的正确路径；.env 文件的查找路径与应用 data_dir 的相对解析基准不同，不要混淆。

开发示例为 CRAWL_ENV=development、CRAWL_DATA_DIR=./data。正式运行可由部署配置注入 CRAWL_ENV=production 和绝对 CRAWL_DATA_DIR，例如 Windows 的 D:/crawl-data 或 Linux 的 /var/lib/crawl-data；它们仅是路径写法示意，不是本项目已分配的目录，不在本次创建。

## 需要实现的验证场景

以下属于新增开发约束验证，不是已经执行的业务用例；不改变原有 37 项 AT 的来源统计。

| 编号 | 输入或操作 | 预期结果 | 任务 |
| --- | --- | --- | --- |
| CFG-01 | 开发源码工程，未设置目录变量 | 结果根为工程/data，与 src 同级 | T003/T004 |
| CFG-02 | .env 指定一目录，进程变量指定另一目录 | 采用进程变量，保持 uv 优先级 | T004 |
| CFG-03 | 从不同工作目录执行同一工程，变量为 ./data | 实际数据根一致；不随 cwd 或 .env 位置改变 | T004 |
| CFG-04 | 生产模式缺少目录、目录为空或为相对路径 | 启动报错，不开始抓取，不偷偷回退开发目录 | T004 |
| CFG-05 | 目录有效、目录是文件、无写入权限三种情况 | 有效时成功，其余明确失败，无外部网络请求 | T004 |
| CFG-06 | 生产绝对目录位于仓库外，无源码树 | 使用指定目录，raw/manifest/document/block/log 全部来自同一根 | T018/T019 |
| CFG-07 | 原数据复制到新根后重设变量 | 原有相对 raw_path 不变，引用与哈希检查通过 | T019 |
| CFG-08 | 注入越界 raw_path 或指向根外的符号链接 | 拒绝越界读取或写入，不修改根外文件 | T019 |
| CFG-09 | 可编辑安装与普通安装后从工程外导入 | 正常导入业务包；不能依赖 PYTHONPATH 或源码 cwd | T003/T019 |

2026-09-11 执行结果：CFG-01—CFG-09 全部 PASS（CFG-01—CFG-05 与 CFG-09 见
[evidence/T003-environment.md](evidence/T003-environment.md)，CFG-06—CFG-08 与逐项复核见
[evidence/T019-acceptance.md](evidence/T019-acceptance.md) 与 [logs/t019-cfg.txt](evidence/logs/t019-cfg.txt)）。
CFG-06 用工程外绝对数据根完成一次真实夹具采集，raw/manifest/document/block/log 全部来自同一根；
CFG-07 搬迁后相对 raw_path 不变、引用与哈希校验通过；CFG-08 的绝对路径、``..`` 与符号链接越界均被拒绝。
CFG-09 除可编辑安装外，另按交付态 wheel 做普通安装复核（工程外导入、无源码根时的报错与显式绝对路径
行为、随包默认 sources.yaml 加载），见 [logs/t019-installed-wheel.txt](evidence/logs/t019-installed-wheel.txt)。

以上 PASS 是固定夹具与临时目录上的工程验证，不代表业务验收：acceptance.md 的业务用例状态保持
NOT RUN；真实来源与运行参数待 Q12/Q13，成果目录的仓库与发布策略待 Q14 剩余部分。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](stage-three.md) 与 [NEXT-06](evidence/next06-budget.md)、[NEXT-07](evidence/next07-cn08-body.md)、[NEXT-08](evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。
