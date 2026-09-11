# Python 开发约束与技术选型登记

状态：Python 与 uv 已由用户明确，Python 3.9 为首选基线；2026-09-11 T002/T003 完成起步环境，T011/T012 完成 PDF/OCR 与 Office 解析选型（TD-08 已选定），记录见 [evidence/T002-selection.md](evidence/T002-selection.md)、[evidence/T003-environment.md](evidence/T003-environment.md) 与 [evidence/T010-T013-parsers.md](evidence/T010-T013-parsers.md)。业务待决 Q 项未改变，完整交付环境仍随未完成模块推进。本文补充四份业务文档，不改变原始需求来源。

## 当前基线

| 项目 | 当前结论 | 实施前需要记录 |
| --- | --- | --- |
| 业务开发语言 | Python，已明确 | 对应根目录 AGENTS.md 的 DEV-001 |
| TD-01 Python 版本 | SELECTED（2026-09-11）：CPython 3.9.25；当前已选范围在 3.9 下锁定、同步、导入与样本测试通过 | 实际补丁版本已写入 `.python-version` 与 `requires-python`；T014/T015 等新模块若冲突，按失败证据从 3.9 起逐个次版本重开 |
| TD-02 框架与依赖 | SELECTED（当前范围）：HTTP、HTML、YAML、PDF、OCR、Office/结构数据、测试与构建后端、调度机制（TD-09）、运行监控与日志（TD-10）、契约校验（TD-11）均已选；无需再引入框架组件 | 分项决定见下方 T002/TD-08/TD-09/TD-10/TD-11 已执行记录；包管理使用 uv；不引入调度框架、日志框架、指标系统或 JSON Schema 库 |
| 项目环境 | 已建立（T003，T011/T012 扩充）：uv 0.11.28 管理 `.venv`；pyproject.toml + uv.lock + .python-version（3.9.25）；运行依赖含 HTTP/HTML/YAML/PDF/OCR/Office，开发组 dev(pytest) | 已验证锁定、同步、导入、可编辑与普通安装；样本解析与测试见 evidence/T003-environment.md、evidence/T010-T013-parsers.md |
| 文档校验环境 | 现有工具要求 PowerShell 7.5+、Python 3.9+ | 仅供文档校验；业务另按 3.9 优先策略验证，不将校验通过当作完整环境通过 |

## T002 已执行记录（2026-09-11）

当前模块所需选型已在隔离工程按 Python 3.9 验证，完整记录与镜像来源证据见
[evidence/T002-selection.md](evidence/T002-selection.md)。业务待决 Q 项未因此关闭。

| 编号 | 决定 | 版本或工具 | 引入时机 |
| --- | --- | --- | --- |
| TD-01 | 采用 CPython 3.9.25，无需次版本升级 | `.python-version`、`requires-python` | 已生效 |
| TD-03 | 构建后端 hatchling，`src/crawler` 包发现 | hatchling | 已生效（T003）；交付态 wheel/sdist 复核见 [evidence/logs/t019-installed-wheel.txt](evidence/logs/t019-installed-wheel.txt) |
| TD-04 | 测试框架 pytest | `>=8.4,<9`，解析 8.4.2 | 已生效（dev 组） |
| TD-05 | HTTP 客户端 requests | `>=2.32,<3`，解析 2.32.5 | T006 实现时加入运行依赖 |
| TD-06 | HTML 解析 beautifulsoup4 + lxml | `>=4.13,<5`、`>=5.3,<7`，解析 4.15.0、6.1.3 | T008/T010 实现时加入 |
| TD-07 | 来源配置解析 PyYAML，仅 `safe_load` | `>=6.0.2,<7`，解析 6.0.3 | T004 注册表实现时加入 |
| TD-08 | PDF、OCR、Office、结构数据解析选型 | SELECTED（2026-09-11）：pypdf 6.18.0、rapidocr-onnxruntime 1.4.4 + pypdfium2 4.30.0、python-docx 1.2.0、openpyxl 3.1.5、defusedxml 0.7.1；CSV/JSON 用标准库 | T011/T012 实现时加入，见下方 TD-08 已执行记录 |

未引入：调度框架、数据库、Web 框架、向量库；标准库可满足的环节不新增依赖。

## TD-08 已执行记录（2026-09-11，T011—T013）

完整证据、样本结果、夹具哈希与限制见 [evidence/T010-T013-parsers.md](evidence/T010-T013-parsers.md)。
所有包经登记清华镜像 `uv add` 安装，`prerelease=disallow`，未回退官方 PyPI，Python 3.9 未升级。

| 编号 | 决定 | 候选与不采用原因 | 版本与传递依赖 | 验证 |
| --- | --- | --- | --- | --- |
| TD-08a | 文本 PDF 解析 pypdf | 候选 PyMuPDF（AGPL，许可风险）、pdfminer.six（维护较缓）；pypdf 纯 Python、维护活跃、无系统组件 | `>=5,<7` → 6.18.0；传递仅 typing-extensions | 两页文本 PDF 页码/段落/表格样本通过 |
| TD-08b | OCR rapidocr-onnxruntime | 系统 tesseract 仅库无可执行文件；paddleocr 依赖重；RapidOCR 纯 pip、自带模型、接口稳定 | `>=1.3,<2` → 1.4.4；传递 numpy 2.0.2、onnxruntime 1.19.2（coloredlogs/flatbuffers/protobuf/sympy/packaging）、opencv-python 5.0.0.93、pillow 11.3.0、shapely 2.0.7、pyclipper、six、tqdm | PNG/扫描 PDF 识别与置信度、部分失败、全失败状态用例通过 |
| TD-08c | 扫描 PDF 栅格化 pypdfium2 | pdf2image 需系统 poppler；PyMuPDF 许可风险；pypdfium2 自带 PDFium、无传递依赖 | `>=4.30,<5` → 4.30.0 | 扫描 PDF 逐页 OCR 页码映射通过 |
| TD-08d | DOCX 解析 python-docx | 不解析二进制 DOC；样式/表格接口稳定、复用已有 lxml | `>=1.1,<2` → 1.2.0 | 标题/段落/列表/表格夹具通过 |
| TD-08e | XLSX 解析 openpyxl | 只读模式内存可控；pandas/openpyxl 组合超出当前需求 | `>=3.1,<4` → 3.1.5；传递 et-xmlfile 2.0.0 | sheet/表头/行号/单位与空 sheet 状态用例通过 |
| TD-08f | CSV/JSON 标准库、XML defusedxml | pandas 属不必要大依赖；defusedxml 已在锁文件，本任务首次使用 | csv/json 标准库；defusedxml 0.7.1 | 编码/分隔符/路径/实体炸弹用例通过 |
| TD-08g | 旧式 DOC/XLS 路线 | 无成熟纯 Python 解析器；路线为 OLE2 识别 + 系统 LibreOffice headless 转换，转换器可注入 | 不新增依赖；本机无 soffice，缺组件时 `LegacyFormatError` 明确报错 | 路线与显式失败路径单测通过；实机转换未验证 |

## TD-09 已执行记录（2026-09-11，T015）

| 编号 | 决定 | 候选与不采用原因 | 版本与传递依赖 | 验证 |
| --- | --- | --- | --- | --- |
| TD-09 | 增量与频率不引入调度框架，用标准库实现策略表、状态文件与条件请求 | 候选 APScheduler/Celery 属常驻调度与分布式范围，超出当前单进程同步采集；周期、启用类别与触发源仍属 Q01/Q13 待决，标准库足够 | 不新增依赖；状态写入 `manifests/incremental_state.json` | 七类频率判定、增量计划、304 端到端复用与配置校验用例通过，见 evidence/T015-schedule.md |

## TD-10 已执行记录（2026-09-11，T017）

| 编号 | 决定 | 候选与不采用原因 | 版本与传递依赖 | 验证 |
| --- | --- | --- | --- | --- |
| TD-10 | 运行日志与指标用标准库 logging + json，指标原子写入 `logs/metrics.json` 并追加 `logs/metrics_history.jsonl` | 候选 structlog/loguru（结构化日志）与 prometheus-client（指标服务）超出当前单进程采集范围；Q15 未定日志保留与轮转策略，先不引入轮转框架 | 不新增依赖 | 计数口径、重复与异常统计、对账差异检出、304 不产生虚假文档与夹具混合运行用例通过，见 [evidence/T017-logs-metrics.md](evidence/T017-logs-metrics.md) |

## TD-11 已执行记录（2026-09-11，T019）

| 编号 | 决定 | 候选与不采用原因 | 版本与传递依赖 | 验证 |
| --- | --- | --- | --- | --- |
| TD-11 | 交付校验用标准库实现 JSON Schema 子集 + 追溯检查 | 候选 jsonschema 库功能完整，但本次只需契约实际使用的关键字（type/required/items/enum/const/pattern/format/allOf/anyOf/if-then-else 等）；DEV-007 先查标准库与现有依赖，避免为单次校验引入新依赖 | 不新增依赖 | 契约正反例、语法/类型/必填/引用错误定位、悬挂块检出与追溯率 100%/空集 N/A 用例通过，见 [evidence/T019-acceptance.md](evidence/T019-acceptance.md) |

## 选型过程与任务关系

T002 负责当前实施范围需要的版本和依赖选型，T003 在相关结论记录后初始化 Python 工程。后续 PDF/OCR 等模块可分批完成对应选型，不必等待未选领域范围的全部工具确定后才能开始最小采集闭环。选择必须满足已冻结数据契约和对应验收场景。

Agent 可先开展候选调研、兼容性试验和固定样本验证，再在授权范围内记录工程决策。需要核查官方支持期限、发行说明或库接口时查阅对应官方资料，不依据“最新版本”的猜测选型。不要未经必要性分析就引入采集框架、Web 框架、数据库服务或分布式调度。

## 选型记录内容

每条技术决定写明：编号、适用模块、候选方案、选择及版本约束、不采用其他方案的原因、官方依据及查阅日期、目标平台、固定样本与验证命令、实际结果、已知限制、决策人或 Agent、受影响文件。

TD-01/TD-02 的状态使用 OPEN / SELECTED / SUPERSEDED。SELECTED 必须有实际选择和验证证据；不能只将未定项填成“建议使用”就标为已选定。变更时保留旧决定和替代理由，不把 Agent 的技术决定写成用户已经指定的版本或框架。

## 依赖与环境交付

项目使用 uv：在 pyproject.toml 声明 Python 支持范围及依赖，用 uv.lock 锁定解析结果，用 .python-version 固定已验证的解释器，在 .venv 安装。运行、测试与可选解析组件明确依赖组和安装条件；三份配置需随代码交付，.venv 不复制。2026-09-11 更新：T003 已创建并交付这三份配置与 dev 依赖；运行依赖按 DEV-007 在对应模块实现时引入。

版本和框架选择不会关闭 Q01 等业务待决事项。未选业务范围不得因某个框架自带能力而自动纳入开发。

## 对应文档

- [开发入口与约束](../../AGENTS.md)
- [技术计划](plan.md)
- [实施任务](tasks.md)
- [项目原则](../../.specify/memory/constitution.md)

## Python 3.9 优先与保守升级

先验证 3.9 的可用补丁版本和所需依赖组合。某个依赖最新版不支持 3.9 时，先比较满足功能与质量要求的兼容版本或替代实现，避免为了追新提高 Python 版本。不得通过忽略依赖约束、漏装必需解析器、禁用必要测试或删减需求制造“可用环境”。

“完整环境”按本次已选交付范围判定，须包括运行依赖、开发/测试依赖、所有已选文件格式解析及 OCR 等能力需要的系统组件，并在目标平台完成依赖锁定、干净环境同步、关键模块导入、代表性样本解析和已存在的相关测试。uv lock 成功、空项目安装成功或 python --version 输出正常均不足以证明完整环境可用。阶段原型可以先验证部分模块，但 TD-01 不得因此提前标记最终通过。

遇到下载失败、源配置、代理、权限、缺少编译器或系统组件时，先排查对应问题；这些现象本身不是 Python 版本不兼容的证据。确实无法构建时记录失败依赖、版本、目标平台、命令、报错及尝试过的兼容方案，再从 3.9 升到 3.10；只有 3.10 仍无法构建才试 3.11，依次保守提高。每个中间次版本均须留下不兼容或构建失败的依据，不无说明跳到最新版本。

找到最低可行版本后停止提高，记录完整环境证据和实际补丁版本，更新 TD-01、pyproject.toml 的 requires-python、.python-version 及 uv.lock，重跑验证。后续必需模块加入后若发现冲突，重新打开 TD-01 并按相同策略处理；框架与 uv 自身的实际版本也记录，不将所有工具一律自动升级。

## uv 使用步骤

以下为后续 T002/T003 的操作说明，本次未执行环境创建。先依据 [uv 官方安装指南](https://docs.astral.sh/uv/getting-started/installation/) 安装适合目标平台的 uv，并记录 uv --version。项目与锁文件操作参见 [项目指南](https://docs.astral.sh/uv/guides/projects/) 和 [锁定与同步](https://docs.astral.sh/uv/concepts/projects/sync/)；解释器选择参见 [Python 版本管理](https://docs.astral.sh/uv/concepts/python-versions/)。

先按 [uv 镜像模板说明](uv-template.md) 将模板复制为根目录 pyproject.toml；已有工程合并配置，不覆盖。准备好解释器后执行下列命令，不再用 uv init 生成缺少镜像配置的另一份文件；目标机器没有可用 Python 3.9 时先用 `uv python install 3.9` 安装 uv 管理的解释器（2026-09-11 已在本机执行，得到 3.9.25，记录见 [evidence/logs/t002-python-install.txt](evidence/logs/t002-python-install.txt)；解释器来源是 uv 内置默认源 `github.com/astral-sh/python-build-standalone`，不经过 PyPI 镜像，需与本项目包源分别核查）：

```powershell
uv --version
uv python install 3.9
uv python pin 3.9
```

检查生成的 pyproject.toml，不采用工具自动选择的更高 Python 要求。验证仅面向 3.9 时，可将 requires-python 设为 `>=3.9,<3.10`，明确暂不声明其他次版本支持；这是本项目保守验证策略，不是 uv 的通用要求。后续升级或扩展支持范围时同步调整，而不只改 .python-version。完成环境验证后，将 .python-version 固定到实测的完整补丁版本。

用 uv add 添加经过选型的运行依赖，用 uv add --group dev 添加所需开发依赖；按实际组件组织其他组或可选项。这里不预置框架包名或版本，避免将未选方案变成依赖事实。补齐当前范围全部依赖后：

```powershell
uv lock --prerelease disallow
uv sync --locked
uv run --locked python --version
```

上面同步默认依赖组；如果完整交付需要额外组或 extras，应在命令中显式加入对应 --group 或 --extra，并将准确命令写入环境记录。只启用已选且可共同安装的组合，不盲目用全部 extras 掩盖互斥组件。再使用 uv run --locked 执行实际模块导入、样本验证和所选测试命令，保存结果。uv sync --locked 用于检查声明和锁文件一致；不得用 --frozen 或临时手装包掩盖未同步的配置。

后续复制项目时携带 pyproject.toml、uv.lock、.python-version，使用相同已记录的 uv/解释器和组配置重新同步，不复制 .venv。文档校验仍可在现有 Python 3.9+ 工具环境运行，它不代替本节完整业务环境验证。

## 成熟依赖与稳定版本策略

依赖按需增加，先检查标准库、已有库和当前代码是否足够。只有能对应当前任务及需求的能力缺口才新增包；不因为“以后可能用到”安装大框架，不引入功能重叠的多套 HTTP、解析或调度方案。必要且成熟的库应合理复用，不能为了减少依赖而重新实现复杂功能并降低质量。

成熟度依据包括：维护与发布记录、稳定 API 和兼容说明、文档及测试质量、问题修复情况、目标平台支持和实际使用积累。不仅凭下载量、星数、发布日期或版本号大于 1 判断成熟。版本优先选已验证的正式稳定版本，并确认与 Python 3.9 或有依据升级后的版本兼容；不自动选最新大版本，也不故意长期停留在已有重要修复的旧版本。需要缺陷修复或兼容修复时，优先评估当前稳定系列的较小更新。

默认不采用 alpha、beta、rc、dev、nightly，也不将 Git 分支头或未固定提交作为可复现依赖。只有当前必要能力确无可行稳定方案时，才记录替代方案、必要性、固定版本/提交、影响、实际测试与后续替换条件，作为明确例外；uv 配置与锁文件同步体现该例外，不为一个包放开所有依赖的预发布策略。

### uv 稳定解析配置

后续创建业务 pyproject.toml 时，合并以下配置到已有的 tool.uv 表，不重复定义同一张表：

```toml
[tool.uv]
prerelease = "disallow"
```

该配置用于明确默认排除预发布版本；仅当已记录必要例外时才按使用的 uv 版本支持的方式作最小范围调整。它不证明包本身成熟、没有缺陷或适合本项目，仍需选型和样本验证。设置说明参见 [uv 官方设置](https://docs.astral.sh/uv/reference/settings/#prerelease)。

首次依赖解析可显式使用：

```powershell
uv lock --prerelease disallow
uv sync --locked
```

正式运行和复现继续使用已记录的依赖组及 uv run --locked。锁文件已有可行版本时优先保留；默认不使用 uv lock --upgrade 作全量升级。必要更新采用针对具体包的 --upgrade-package，并在需要时限定已验证的目标版本；这仍可能改变相关传递依赖，必须检查整个 uv.lock 差异，不能宣称只变了指定的一个包。锁文件更新方式参见 [uv 锁定版本升级说明](https://docs.astral.sh/uv/concepts/projects/sync/#upgrading-locked-package-versions)。

### 每次依赖变更的记录与验证

在 TD-02 或关联任务记录中写明：对应需求/任务、为何标准库或现有依赖不足、候选及成熟度依据、所选正式版本与兼容范围、新增或变更的传递依赖、系统组件、uv 命令、锁文件差异、实际验证结果。直接依赖在 pyproject.toml 给出有依据的约束，精确解析结果由 uv.lock 保存；不要把不必要的传递依赖全部提升为直接依赖。

一次变更尽量聚焦一项能力或一组必须共同调整的依赖。完成同步、导入、相关解析样本与适用测试后再继续下一项，发现无关大范围更新时先查明原因。失败时根据已保留的声明和锁文件恢复环境，不手工篡改锁文件或全局补装包。无需为每个正常工程选型额外申请批准，但必须保留依据；业务范围变化仍按原有待决流程处理。

本节规定后续开发规则，Python 3.9 优先与逐个次版本保守升级规则继续适用。2026-09-11 更新：T002/T003 已创建业务锁文件，并选定构建后端、测试框架及后续模块的候选运行依赖版本；HTTP、HTML、YAML 运行依赖按 DEV-007 推迟到对应任务引入，见 T002 已执行记录。

## 源码布局与 uv 环境配置

执行 [项目起步说明](project-startup.md)：T002 先在隔离工程验证候选环境，T003 整理正式 src 包布局与构建后端配置，验证可编辑安装及常规安装。uv init --bare 本身不保证业务包可导入。开发使用 uv run --locked --env-file .env 显式加载配置，应用从 os.environ 读取；暂不为这项能力增加 python-dotenv。生产由启动环境注入 CRAWL_ENV=production 和绝对 CRAWL_DATA_DIR。

## 强制镜像源与起步模板

执行 DEV-009 和 [uv 镜像模板说明](uv-template.md)。默认清华镜像替换内置 PyPI，禁止失败回退；核查环境覆盖、专用源、锁文件制品地址和空缓存安装证据。模板 package=false 已于 T003 移除，hatchling 与 src 包发现已配置，可编辑与普通安装验证见 [evidence/T003-environment.md](evidence/T003-environment.md)。

## 续作环境边界

当前复用已记录的 Python 3.9.25、uv 与锁文件，不重复初始化或空缓存安装来证明未变化环境。TD-08g 旧式 DOC/XLS 的真实 LibreOffice 转换仍未验证；不能把现有包环境测试通过称为包含该能力的完整环境通过。按 [阶段续作说明](continuation.md) NEXT-04 关闭该实际缺口；仅相关依赖/环境变化才触发新环境验证。

## 运行契约的打包方式（NEXT-08，无新增依赖）

`crawl sources` 与 `crawl check` 所需的 6 个 JSON Schema 随 wheel 交付到 `crawler/contracts/`，
运行期用标准库 `importlib.resources` 读取包资源，不再依赖源码树或开发机器路径；
`specs/001-public-knowledge-collection/contracts/` 仍是权威来源，`tools/sync_contracts.py` 负责同步与
`--check` 漂移校验，`tests/test_contract_resources.py` 守住一致性。该能力只用标准库与既有 hatchling 打包，
未新增运行依赖、未引入配置框架；普通安装与源码外命令验证见 [NEXT-08 证据](evidence/next08-packaged-contracts.md)。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](stage-three.md) 与 [NEXT-06](evidence/next06-budget.md)、[NEXT-07](evidence/next07-cn08-body.md)、[NEXT-08](evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。
