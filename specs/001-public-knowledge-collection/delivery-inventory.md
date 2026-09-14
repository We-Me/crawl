# 工程交付清单（NEXT-09）

> 历史记录说明（2026-09-14）：本文保存对应阶段的计划、资产或限制快照，旧“当前/下一步/等待”不代表当前调度。当前开发仅按 [阶段七](stage-seven.md)；T012 已完成，来源与最小分块已确认。阶段七交付时据实际成果更新清单/限制，不能提前宣称已验收。

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。T012 已完成；T019/T026/T027 的全业务验收记录与阶段七基础软件交付分别判断。旧缺组件/权限记录不再作为当前阻塞。

版本：0.1.0｜日期：2026-09-11｜状态：工程交接清单；工程交接完成不等于正式验收完成

本清单登记当前工作副本（项目根、git 仓库）实际可交接的工程版本：源码提交、Python/uv 与锁文件、
源码/契约/来源配置位置、可取得的构建产物、运行说明、验证证据、系统组件缺口与未交付范围。
三类材料严格区分：

- **仓库文件**：随 git 提交交付，可用提交号复核；
- **历史执行日志**：`specs/001-public-knowledge-collection/evidence/` 下的文本记录，是证据文本，不是可执行产物；
- **未随仓库交付的本机产物**：被 `.gitignore` 排除的 `dist/`、`data/`、`.venv/` 等（存在则给哈希，未留存则如实写未交付）。

本清单不改变 [验收规范](acceptance.md) 的用例状态和 [待决事项](clarifications.md) 的 Q 项结论。

## 2026-09-13 增量（不重写上文 2026-09-11 基线）

- NEXT-04 真实旧式 DOC/XLS 验证已完成，T012 勾选；两条记录随之更新：
  旧式转换环境（第 5 节表内 `t012-libreoffice-env.txt` 行）已由
  [NEXT-04 证据](evidence/next04-legacy-office.md) 关闭；系统组件缺口（第 6 节）中
  LibreOffice 已安装并用于验证，不再是缺口。
- 源码基线前进：`src/crawler/parser/legacy_parser.py`（失败消息区分退出码/无输出）、
  `src/crawler/pipeline.py`（新增 `legacy_converter` 注入点）；新增
  `tests/fixtures/office/notice.doc`、`notice.xls`、`tests/test_legacy_office_real.py`、
  `tools/make_legacy_fixtures.py`。第 1 节的 `d39bdc0` 基线仅适用于 2026-09-11 版清单。
- 候选产物已重建，与历史产物的哈希对比见 [NEXT-04 证据](evidence/next04-legacy-office.md)；
  `dist/` 仍不随仓库交付。
- 本轮交付（NEXT-04/T012、NEXT-10 澄清材料、决策输入与「仍需解读事项（含阶段四归属）」）已提交，
  并按用户要求合并为一条阶段四提交，提交号以 `git log -1` 为准，工作树干净；组件用例级证据
  （13 passed）与沙箱内诊断见 [NEXT-04 证据](evidence/next04-legacy-office.md)。
- 未交付范围与业务待决（Q01 剩余分块含义、Q11、Q12、Q13、Q14）不变；NEXT-10 澄清材料见
  [当前范围与分块](scope-and-blocking.md)，仍需解读事项及其阶段四归属见
  [决策请求](decision-requests.md) 的「仍需解读事项（含阶段四归属）」一节。

## 1. 版本基线

| 项 | 实际值 | 位置/证据 |
| --- | --- | --- |
| 源码提交 | 代码基线 `d39bdc0`（阶段三 NEXT-06/07/08 的源码与契约变更）；其后 `1b51121`（阶段三复核文档）与 `e9e522c`（阶段四 part1）只改文档，未改 `src/`、`tests/`、`tools/` | git 历史 |
| 交付版本号 | `0.1.0` | `pyproject.toml`、wheel 元数据 |
| Python | CPython `3.9.25`，uv 管理 | `.python-version`；[运行说明](runbook.md) |
| uv | `0.11.28`（`x86_64-unknown-linux-gnu`） | 历史环境证据 [T003 环境验证](evidence/T003-environment.md) |
| 锁文件 | `uv.lock`，74526 字节，SHA-256 `f5e8fa9cc7685ba1e37ba0b097cb8815d9db398843716386b34fcdd785d1b4e6` | 仓库根；来源核对见 [锁文件来源证据](evidence/logs/t019-lock-provenance.txt) |
| 目标平台 | Linux x86_64（Ubuntu 24.04.4 LTS / WSL2 内核 6.6.114.1） | [t027-cli.txt](evidence/logs/t027-cli.txt)、[t012 环境记录](evidence/logs/t012-libreoffice-env.txt) |
| 仓库跟踪文件 | 238 个 | `git ls-files` |

本清单、[决策请求](decision-requests.md) 确认栏与 [局限与所需输入报告](limitations-report.md) 随
「阶段四 part1：工程交接清单、决策确认栏与局限报告」提交交付，可用该提交号复核；
`src/`、`tests/`、`tools/` 的代码内容仍以 `d39bdc0` 及其之前的代码提交为准。

锁文件哈希与运行证据为 2026-09-11 记录；本轮未重跑 `uv sync`、pytest 或线上采集。

## 2. 源码、契约与配置位置

### 业务源码与包资源（随仓库交付）

| 位置 | 内容 | 规模 |
| --- | --- | --- |
| `src/crawler/` | 采集业务包：`cli.py`、`pipeline.py`、`fetch/`（robots、预算、HTTP、重试、下载）、`discover/`、`parser/`、`normalize/`、`dedup/`、`versioning/`、`output/`、`validate/`、`monitor/`、`config/` | 63 个 `.py` 文件，约 9510 行 |
| `src/crawler/contracts/` | 随包交付的 6 份 JSON Schema（attachment、block、document、failure、manifest、source-registry） | 与 [规格契约](contracts/README.md) 同源 |
| `src/crawler/config/sources.yaml` | 随包来源注册表，只有默认禁用的虚构 `DEMO` 来源 | 真实来源待 Q12/Q13 |
| `tests/` | 24 个 Python 文件（单元、端到端、`tests/acceptance/` 验收夹具、`tests/fixtures/` 样例原件） | 含 HTML/Office/PDF/CSV/JSON/XML 固定样本 |
| `tools/` | 6 个脚本：`build_sdd_documents.py`（初始生成，不再重跑）、`make_fixture_binaries.py`、`realsite_smoke.py`（开发核验，不是业务入口）、`sync_contracts.py`、`verify_sdd_documents.py`/`.ps1` | 文档与夹具工具 |
| `docs/` | 4 份业务输入（2 份 Word + 2 份需求审查），SHA-256 登记在 [来源登记](sources.md) | 业务依据，不随代码修改 |
| `specs/001-public-knowledge-collection/` | 规格、契约、计划、验收、决策请求与 `evidence/`（47 个已跟踪证据文件） | 本清单所在目录 |

### 契约与来源配置的对照位置

- 契约双份保持一致：随包 `src/crawler/contracts/*.schema.json`（6 份）与规格侧 `specs/001-public-knowledge-collection/contracts/`（6 份 schema + README）；同步脚本 `tools/sync_contracts.py`，一致性证据见 [NEXT-08](evidence/next08-packaged-contracts.md)。
- 来源登记与专站输入：`specs/001-public-knowledge-collection/sources.md`、`source-adapters.md`、`sources/source-register.json`（4 份业务输入指纹）；18 个候选来源（CN-01—CN-08、IN-01—IN-10）均只有浅层核验记录，未启用。
- 试点来源配置：`specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml`（CN-08 试点专用，正式注册表仍只有禁用 DEMO）；随仓库的示例交付样本在 `examples/data/`（虚构 DEMO）。

## 3. 历史构建产物（当前副本不含，未随 git 仓库交付）

`dist/` 被 `.gitignore` 排除。下表是 2026-09-11 Linux 交接时的本机产物记录；2026-09-13 当前 Windows 副本无 dist/，不能从当前仓库直接取得这些产物：

| 产物 | 大小 | SHA-256 |
| --- | --- | --- |
| `dist/public_knowledge_collection-0.1.0-py3-none-any.whl` | 136424 字节 | `866324e160a75479032a3651d13c19320b9c11c191e7299aff0398c583e9dec7` |
| `dist/public_knowledge_collection-0.1.0.tar.gz` | 715340 字节 | `2c7399c52a128846abc04882aab46a156a70c3898dc85935ebf0309c053e96d0` |

- 构建时间 2026-09-11 21:40，构建命令与安装验证见 [next08-installed-wheel.txt](evidence/logs/next08-installed-wheel.txt)（`uv build`，构建后端 hatchling 来自登记清华镜像）。
- 阶段四续作（2026-09-13）已重建候选产物（源码修复 + 测试/文档收尾快照）：当前候选哈希、
  逐成员比对与 `--no-build-isolation` 的沙箱构建方式见 [NEXT-04 证据](evidence/next04-legacy-office.md)；
  本表仍只记录 2026-09-11 历史产物，两者不要混用。
- 阶段四 part1 的只读核验记录：wheel 内 70 个 `crawler/**` 的 `.py`/`.json`/`.yaml` 成员与 `src/` 同名文件 SHA-256 全部一致，wheel 与当前源码对应；未重建 wheel。
- wheel 含控制台入口（`crawl = crawler.cli:main`）、`crawler/config/sources.yaml` 与 6 份契约；阶段三随包契约的源码外普通安装证据见 [next08-installed-wheel.txt](evidence/logs/next08-installed-wheel.txt)。
- 历史日志中的临时目录（`/tmp/t027-wheel`、`/tmp/next08-venv`、`/tmp/next08-run`、`/tmp/cn08-pilot`）已不存在，**未随仓库交付**；需要时按 [运行说明](runbook.md) 重新安装/重建。

## 4. 安装、配置与运行入口

正式入口是安装后的控制台命令 `crawl`（等价 `python -m crawler`，源码 `src/crawler/cli.py`）；子命令
`sources`/`collect`/`plan`/`resume`/`check`，退出码 0/1/2/3。完整说明以 [运行说明](runbook.md) 为准：

```bash
uv python install 3.9.25                       # 仅在缺少已固定解释器时
uv sync --locked --no-python-downloads          # 按锁文件复现依赖并安装 crawl
test -e .env || cp .env.example .env            # 开发环境；生产用绝对 CRAWL_DATA_DIR
uv run --locked --no-python-downloads --env-file .env crawl --help
```

- 配置入口：`CRAWL_ENV`（`development` 默认 / `production`）与 `CRAWL_DATA_DIR`（开发默认工程根 `data/`；生产必须显式绝对路径），规则见 [项目起步说明](project-startup.md)。
- 交付校验：`uv run --locked --no-python-downloads --env-file .env crawl check`（六项成果、schema、100% 原件追溯）。
- 线上运行必须显式给出 `--max-requests` 与 `--deadline-seconds`；守规试点预算取 10 请求 / 300 秒。
- 快速上手与阅读顺序见 [交接指南](quickstart.md)。

## 5. 验证证据索引

证据总索引为 [evidence/README.md](evidence/README.md)（16 份记录 + 日志目录）。主要条目：

| 证据 | 覆盖 | 结果（历史执行，本轮未复跑） |
| --- | --- | --- |
| [t027-cli.txt](evidence/logs/t027-cli.txt) | 正式 CLI 命令面与退出码 | 通过；末节读取已有开发数据根（manifest 10 / documents 10 / blocks 489，追溯 100%） |
| [t027-full-pytest.txt](evidence/logs/t027-full-pytest.txt) | 阶段二候选回归 | 325 passed |
| [t019-pytest.txt](evidence/logs/t019-pytest.txt) | T019 及后续补强回归 | 310 passed（当时） |
| [stage-three-full-pytest.txt](evidence/logs/stage-three-full-pytest.txt) | 阶段三候选回归（NEXT-06/07/08 后） | 345 passed；6 契约一致 |
| [T019 验收记录](evidence/T019-acceptance.md) + [报告 JSON](evidence/logs/t019-acceptance-report.json) | AT-001—AT-024 夹具级验收、schema/追溯、CFG-01—CFG-09 | passed 22、blocked 2（AT-014/AT-024，取决于 Q11）、not_applicable 13（领域用例未选中） |
| [NEXT-06](evidence/next06-budget.md) | 请求预算、截止时间、停止报告、退出码 3 | 14 项预算用例 + `test_budget.py`，见 [next06-cli-stop.txt](evidence/logs/next06-cli-stop.txt) |
| [NEXT-07](evidence/next07-cn08-body.md) | CN-08 正文边界修复 | 已有原件离线重解析 10 块 → 6 块，正文逐字保留 |
| [NEXT-08](evidence/next08-packaged-contracts.md) | 随包契约与源码外普通安装 | 通过；见 [next08-installed-wheel.txt](evidence/logs/next08-installed-wheel.txt) |
| [t026-realsite-smoke.txt](evidence/logs/t026-realsite-smoke.txt) | 18 个登记来源浅层核验 | 五轮共 69 个请求，遵守 robots 与逐来源限速；记录保守拒绝与别名域等约束 |
| [t026-pilot-cn08.txt](evidence/logs/t026-pilot-cn08.txt) + [试点卡](pilot-cn08.md) | CN-08 单站受限试点 | 3 个请求完成栏目发现 → 文章获取 → 交付校验 |
| [t019-lock-provenance.txt](evidence/logs/t019-lock-provenance.txt) | 锁文件与制品来源 | 40 个 registry 包与 202 条制品 URL 均为登记清华镜像，空缓存 `uv sync --locked` 成功 |
| [t012-libreoffice-env.txt](evidence/logs/t012-libreoffice-env.txt) | 旧式 DOC/XLS 转换环境 | 组件缺失与权限阻塞已记录，真实转换未验证 |

以上均为固定夹具、已有原件离线复算或受限线上核验的工程证据，不是正式业务验收结论。

## 6. 系统组件缺口

| 项 | 现状 | 影响与恢复条件 |
| --- | --- | --- |
| LibreOffice（`soffice`/`libreoffice` headless） | 目标 Linux 未安装；`sudo -n` 需要密码，Agent 无 root 授权；apt 候选已核验（`libreoffice-writer`/`libreoffice-calc` 4:24.2.7-0ubuntu0.24.04.6） | 真实旧式 DOC/XLS（OLE2）转换无法验证（T012 部分完成）；缺组件时 `LegacyFormatError` 明确报错、不静默回退。恢复条件：获得安装权限或提供可用转换器 |
| 其他解析能力 | PDF/OCR/DOCX/XLSX/CSV/JSON/XML 均由 pip 依赖提供，无额外系统组件 | 见 [选型记录](tech-stack.md) TD-08 表 |
| 依赖与解释器来源 | Python 包由登记清华镜像提供（`uv.lock` 已核对）；uv 解释器来源单独核验 | 见 [uv 模板说明](uv-template.md)、[T002 选型验证](evidence/T002-selection.md) |

## 7. 未交付范围与未决事项

- **业务待决（不阻塞已完成工程）**：Q01 阶段范围、Q11 质量阈值与样本分母、Q12 发现流程与站点规则落地、
  Q13 启用来源/时间范围/运行参数、Q14 成果仓库与发布策略，见 [决策请求](decision-requests.md) 与 [待决事项](clarifications.md)。
- **来源启用**：随包注册表只有禁用 DEMO；CN-08 正文选择器只记录在试点配置，不等于正式启用；18 个候选来源未接入正式采集。
- **正式验收**：T012（真实旧格式转换）、T019（AT-014/AT-024 及正式业务验收）、T026（逐站规则与至少 10 词验证）、
  T027（总体验收）均保持部分完成，任务勾选状态见 [实施任务](tasks.md)；工程交接不代替正式验收。
- **未实现能力**：无后台调度/守护进程、无并发采集（CLI 单进程同步执行）；同步网络调用的硬实时中断未验证
  （0.1 秒为超时下限，见 [NEXT-06 限制](evidence/next06-budget.md)）；同一数据根只允许一个写进程。
- **本机开发产物（不随仓库交付）**：`data/` 根当前 1.2M，含 `raw/`（CN-01/04/08、IN-01/02/10 的受限核验原件）、
  `manifests/`（10 条账本、10 条文档、489 个块）、`logs/` 及 `data/*.yaml|json` 探针记录；`.venv/`、`.pytest_cache/`
  同为本地环境。真实站点原件仅存在于此，**未随仓库交付**；随仓库的只有虚构 `examples/data/` 样本。
- **历史日志的边界**：证据目录中的通过数、请求数与时间为历史执行结果，本轮仅做文档结构校验，未复跑测试或站点探测。

## 8. 清单边界

- 本清单覆盖仓库实际文件、已留存证据与已知缺口；未列出的产物不存在或未留存，不补造路径。
- 复现环境用 `uv sync --locked`（[运行说明](runbook.md)）；构建产物需 `uv build` 重建，本清单不承诺随仓库附带 wheel。
- 局限、未交付范围与所需业务输入的交接汇总见 [局限与所需输入报告](limitations-report.md)。
- 工程交接已完成不等于正式验收完成：正式验收与来源启用必须等 [决策请求](decision-requests.md) 的确认后按
  [阶段四交付收口](stage-four.md) 的 NEXT-05B/C 执行。

## 2026-09-13 只读复核

基线 e9e522c；git diff d39bdc0 HEAD -- src tests tools pyproject.toml uv.lock 无变化。当前副本无 dist/；上述产物哈希、data 大小及临时目录状态属于历史 Linux 时点，本轮未重新计算其文件哈希或重建产物。当前工作区换行符可能影响文件字节，复现锁文件应使用仓库版本及平台换行设置，不将本机字节差异直接判为依赖升级。范围与分块语义见 [当前范围与分块](scope-and-blocking.md)。

## 2026-09-14 增量核验（计数与锁文件）

在阶段五第 87 轮时点上只读复核 2026-09-11 基线中的计数（提交已按阶段合并整理，合并前短哈希 `4021288`），不重写上文节次、
不重做本清单；原始输出见[第 88 轮日志](evidence/logs/stage-five-round88-offline-inventory-counts.txt)。

- 锁文件未变：`uv.lock` 74526 字节、SHA-256 `f5e8fa9c…d1b4e6`，与基线登记一致
  （仅字节校验，未重跑 `uv sync`）。
- 计数变化（前为 2026-09-11 登记值）：仓库跟踪文件 238 → **335** 个；
  `specs/001-public-knowledge-collection/evidence/` 已跟踪证据文件 47 → **98** 个；
  `src/crawler/` 63 → **71** 个 `.py`、约 9510 → **13042** 行；`tests/` 24 → **33** 个 `.py`；
  `tools/` 6 → **9** 个脚本（新增 `coverage_table.py`、`make_legacy_fixtures.py`、
  `offline_replay.py`）。
- 第 2 节 `src/crawler/config/sources.yaml` 行已过期：现登记全部 18 个开发来源
  （`enabled: true` 仅表示开发范围可执行，正式启用仍待 Q12/Q13），随包 DEMO 仍禁用。
- 第 1/2 节表内数字与源码提交 `d39bdc0` 基线保持原样，适用于 2026-09-11 时点；
  阶段五实施状态与数据计数以 [阶段五](stage-five.md)、[续作说明](continuation.md) 为准。
- 文档一致性复核通过（契约 6 份一致、`verify_sdd_documents` PASS）；用例状态不变：
  T019/T026/T027 保持部分完成，不自动勾选（[验收规范](acceptance.md)）。
