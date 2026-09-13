# NEXT-04：真实旧式 DOC/XLS 转换、结构保留与原件追溯（2026-09-13）

本记录对应 [当前范围与分块](../scope-and-blocking.md) 的 NEXT-04（T012 的旧格式子项），
执行者是本轮 Agent 在目标 WSL（本机 = 用户已装组件的同一 Linux）中运行，不是模拟转换器。
它只证明旧格式解析与追溯链路在固定样本上可用，**不代表真实站点或机构文档验收**，
也不改变 T019/T026/T027 与第四阶段整体状态。

## 组件与环境

| 项目 | 实测值 | 说明 |
| --- | --- | --- |
| 组件路径 | `/usr/bin/soffice` → `/usr/lib/libreoffice/program/soffice` | `command -v soffice`、`command -v libreoffice` 均可解析 |
| 版本 | `LibreOffice 24.2.7.2 420(Build:2)` | 与用户提供的环境证据一致 |
| 程序发现 | `uv run --locked --no-python-downloads python -c "from crawler.parser.legacy_parser import find_soffice; print(find_soffice())"` → `/usr/bin/soffice` | 复用现有 `find_soffice()`，未新增配置项 |
| 解释器 | CPython 3.9.25（uv 管理，`.python-version`） | 未升级 Python、未改依赖与锁文件 |
| 沙箱限制 | 本轮执行环境带 AppArmor/seccomp：`soffice --version` 可运行，完整初始化/转换被拒（退出码非 0、无输出） | 因此所有真实转换命令都在沙箱外执行；沙箱内 `uv run pytest` 的 5 个真实转换用例按能力探测 skip 并给出原因，不误报为失败 |

## 样本来源与哈希

自产固定样本，全部来自仓库既有确定性 OOXML 夹具，由系统 LibreOffice 生成真实 OLE2
二进制文件（非改扩展名、非只有魔数）。生成过程与局限见
[tools/make_legacy_fixtures.py](../../../tools/make_legacy_fixtures.py) 与
[夹具 README](../../../tests/fixtures/README.md)。

| 样本 | 大小 | sha256 | 来源 |
| --- | --- | --- | --- |
| `tests/fixtures/office/notice.docx` | 36895 | `65da833b0864734c4b4ff21422a8542ab63d986239eae1cacc5f534a4525af79` | T010 既有夹具（python-docx 生成） |
| `tests/fixtures/office/notice.xlsx` | 5861 | `d2e61aa457ea7d4a57a5143e662e2aa76b30295deef29998b999057eeb175f92` | T010 既有夹具（openpyxl 生成） |
| `tests/fixtures/office/notice.doc` | 19456 | `71dd62f6c722ce3f65d17c1ad83ba070171a63d22c9f930e9c740a4f7f2aa765` | 生成路线 `notice.docx → odt → doc` |
| `tests/fixtures/office/notice.xls` | 6656 | `aa8bbcb06f7d8b0a07468ae0f48326e54616aa6142c47b03e7972420c7a8e069` | 生成路线 `notice.xlsx → xls` |

`file(1)` 对两个旧格式样本均报 `Composite Document File V2 Document`，魔数为
`d0 cf 11 e0 a1 b1 1a e1`；同版本 LibreOffice 下重复生成字节一致（两次独立 profile
运行哈希相同），`tools/make_legacy_fixtures.py` 默认与记录值比对，不一致时不覆盖夹具。

### 结构级真实性（本轮新增，不依赖 LibreOffice）

`test_legacy_samples_carry_real_word_or_excel_streams` 用标准库直接解析 OLE2/CFB 目录与
FAT/miniFAT 链，证明样本不是“只有魔数的伪文件”：

| 样本 | 关键流 | 大小 | 流首部 |
| --- | --- | --- | --- |
| `notice.doc` | `WordDocument` | 4157 | `ec a5 01 01`（Word FIB：wIdent=0xA5EC、nFib=0x0101） |
| `notice.doc` | `1Table` | 10399 | 随 `WordDocument` 一同存在的表流 |
| `notice.xls` | `Workbook` | 2807 | `09 08 10 00`（BIFF8 BOF，版本字段 0x0600） |

两个样本还各含 `\x05SummaryInformation` 与 `\x05DocumentSummaryInformation` 属性集流
（CFB 约定：属性集流名前缀 `\x05`，OLE 嵌入对象名前缀 `\x01`）。

反向对照（本轮实测，确认该用例不是空断言）：`notice.docx`（ZIP）交给同一读取器 →
`ValueError: 不是 OLE2 复合文档`；`notice.doc` 截为前 600 字节后再用 0 补齐 →
`ValueError: OLE2 FAT 链越界，疑似伪造或损坏的复合文档`。

## 执行命令与结果

全部经项目代码路径执行（`parse_attachment` → `dispatcher` → `parse_legacy` →
`soffice_converter` → LibreOffice → `parse_docx`/`parse_xlsx`）：

```bash
# 生成夹具（沙箱外）
uv run --locked --no-python-downloads python tools/make_legacy_fixtures.py
# notice.doc  19456 bytes  sha256=71dd62f6…  与记录一致
# notice.xls   6656 bytes  sha256=aa8bbcb0…  与记录一致

# 真实转换 + 结构核对
uv run --locked --no-python-downloads python /tmp/probe_legacy.py
```

| 检查项 | 结果 |
| --- | --- |
| DOC 转换成功且目标 DOCX 有效 | 通过：LibreOffice 输出被 `python-docx` 正常打开，`extraction_method=python_docx` |
| DOC 正文/段落/列表保留 | 通过：6 个块依次为 heading(L1)、paragraph、heading(L2)、list_item、list_item、table；标题 `Fixture Notice - Office Formats`，段落文本逐字一致 |
| DOC 表格保留 | 通过：`headers=["Item","Quantity","Amount"]`，`rows=[["Widgets","12","340.00"],["Gadgets","3","125.50"]]` |
| XLS 转换成功且目标 XLSX 有效 | 通过：`openpyxl` 只读打开，`extraction_method=openpyxl_read_only` |
| XLS sheet/单元格保留 | 通过：`page_count=3`，页状态 `ok/ok/empty`；Summary 表头 `["Item","Quantity（单位：件）","Amount（单位：元）"]`、行 `[["Widgets","12","340"],["Gadgets","3","125.5"]]`、`units={"Quantity（单位：件）":"件","Amount（单位：元）":"元"}`；Notes 表 `[["Fixture only"]]`；空 sheet 记 `sheet_3_empty`，未静默丢弃 |
| 失败不返回空成功 | 通过：截断的 OLE2 样本（保留魔数）触发 `LegacyFormatError`，消息为“LibreOffice 未生成转换结果 .docx（源文件无法转换）…”，未产生空文档 |
| 未安装组件时显式失败 | 通过：`find_soffice()` 返回 None 时报“本机未安装 LibreOffice…”，不静默降级 |

## 本轮发现与最小修复

1. **失败消息误报退出码（已修复）**：实测 LibreOffice 24.2 在源文件无法加载时**以退出码 0
   结束且不产出文件**，原实现把这种情况报成 `code=0`，误导失败账读法。现按“退出码非 0”与
   “未生成目标文件”分别报错，两者都不放行空成功（`src/crawler/parser/legacy_parser.py`）。
   新增针对性用例：`test_converter_exit_zero_without_output_is_failure`（注入 `subprocess.run`
   返回 0 且不产出文件）与 `test_converter_nonzero_exit_reports_code`。
2. **夹具生成侧限制（非本项目链路缺陷）**：LibreOffice 24.2.7.2 把 python-docx 写出的 DOCX
   直接 `--convert-to doc` 时，导出结果含单元格标记但**再读回会把表格拉平成普通段落**
   （有边框/无边框、`tblW` 为 auto/dxa 均可复现）；换成 LibreOffice 自己写出的 DOCX 或 ODT
   作为输入则表格保留。本项目只做 `.doc/.xls → docx/xlsx` 方向转换，不产出 `.doc`，故该导出
  行为不影响解析链路；夹具经 ODT 中转，使“表格结构保留”有真实对象可验。
3. **用例门禁用 `which` 不够（已修复，本轮追加）**：原 `needs_soffice` 只看
   `find_soffice() is None`。受限沙箱里 `/usr/bin/soffice` 存在、`soffice --version`
   也正常退出，但完整初始化与转换被拒（`code=1`、无输出），结果是真实转换用例**失败**
   而不是跳过；更关键的是 `test_corrupt_ole2_…` 会在“组件其实不可用”的情况下以错误的
   原因通过（它只断言抛 `LegacyFormatError`，而缺组件与转换失败都会抛同一个异常）。
   现改为能力探测：真的转换一次 `notice.doc` 成功才算组件可用，否则 skip 并把转换器
   错误写进 skip 原因；损坏 OLE2 用例同时断言命中转换分支（消息含“转换”、不含
   “未安装 LibreOffice”）。判定只影响“能否执行”，不放宽任何断言。

## 用例与可复跑命令

`tests/test_legacy_office_real.py`（13 项）：

- 不依赖系统组件（8 项，本地沙箱已通过）：样本真实性/哈希、OLE2 流结构（含 Word FIB 与
  BIFF8 首部，见下）、退出码 0 无输出、退出码非 0、缺组件提示，以及两条端到端追溯用例中
  的失败分支。
- 依赖 LibreOffice（5 项，本地沙箱按能力探测 skip，见下）：DOC 结构保留、XLS 结构保留、
  损坏 OLE2 显式失败、原件→重解析→documents/blocks→追溯校验的端到端链路、
  转换失败仍保持可再次补抓。

受限沙箱内的实际结果（本轮）：

```text
uv run --locked --no-python-downloads pytest tests/test_legacy_office_real.py -q -rs
8 passed, 5 skipped in 0.49s
SKIPPED … LibreOffice 无法在当前环境完成真实转换，跳过真实旧格式用例：
        LibreOffice 转换失败（code=1）：Warning: failed to launch javaldx …
```

其中 8 项通过的是不依赖系统组件的用例（含本轮新增的 OLE2 流结构校验）。

同一文件在**目标 WSL 的正常 shell**（未受限、组件同为本机 LibreOffice 24.2.7.2）复跑：

```text
$ UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads \
      pytest tests/test_legacy_office_real.py -q
.............                                              [100%]
13 passed in 4.63s
```

即 5 项依赖组件的用例（DOC 结构保留、XLS 结构保留、损坏 OLE2 显式失败、原件→重解析→
documents/blocks→追溯校验的端到端链路、转换失败仍可再次补抓）在真实 LibreOffice 下实际
执行并通过。NEXT-04 的用例级证据至此闭合：13 项全部通过。

全量沙箱基线（同一环境，本轮最终）：`1 failed, 247 passed, 5 skipped, 105 errors`；
唯一失败为 `tests/acceptance/test_collection_acceptance.py::
test_acceptance_report_covers_all_cases`（回环 HTTP 被沙箱禁止），105 个 error 均为
沙箱 `PermissionError`，与旧格式链路无关。

### 受限沙箱内 LibreOffice 为何无法完成转换（本轮诊断，属执行环境限制）

同版本组件在正常 shell 可用（上一轮已用它生成夹具并完成真实转换），但在本沙箱内
`soffice.bin` 会在启动阶段自我重启两次后静默 `exit 1`：

- `soffice --version` 与 `/usr/lib/libreoffice/program/soffice.bin --headless --version`
  都正常（退出码 0）；
- `--headless --convert-to docx`、`--headless --terminate_after_init` 均退出码 1，
  且 stderr/stdout 一个字节都不输出；
- 用自建的 `LD_PRELOAD` 观察探针（只记录，不拦截行为）可见：进程 `fork` → 子进程以
  同一 argv 重新 `exec`（仍带 `-env:UserInstallation=…`）→ 再重复一次 → 最内层进程
  正常 `exit(1)`（父进程 `waitpid` 得到状态 `0x100`，不是被信号杀死），父进程随后同样退出 1；
- 全程没有 `open`/`openat`/`mkdir` 的 `EACCES/EROFS/EPERM` 失败；`/dev/shm` 可写
  （`shm_open` 成功）；`inotify_init1`/`epoll_create1`/`eventfd`/`socketpair`/`memfd_create`
  等 syscall 均可用；
- 换 `HOME`/`TMPDIR`/`XDG_*`/`SAL_USE_VCLPLUGIN=svp`/`SAL_NOLOCK_PROFILE=1`、或完全去掉
  `-env:UserInstallation` 参数，结果完全相同（退出码 1、无输出）。

结论：这是执行环境对组件完整初始化的限制，与本仓库代码、夹具和转换器实现无关；沙箱内
这 5 项按能力探测 skip 并打印原因，真实结果已在目标 Linux 正常 shell 复跑并通过（见上，
13 passed），本节的诊断仅用于解释沙箱内的 skip 现象。

```bash
# 目标 Linux 正常 shell（非受限沙箱）
uv run --locked --no-python-downloads pytest tests/test_legacy_office_real.py -q
```

端到端用例覆盖：原件按 `raw_path` 落盘且字节不变、manifest 记录同一 `crawl_id` 与哈希、
失败行经 `resume_failures` 关闭为 recovered、documents 的 `raw_path`/`sha256` 指回同一原件、
blocks 归属正确 `doc_id`，最后经 `crawler.validate.traceability.trace_delivery` 检查
`documents/blocks` 追溯率 100%；转换失败的样本保留原件、失败仍未关闭（可再次补抓）。

## 随包候选产物（源码变化后重建）

本轮改了 `src/crawler/parser/legacy_parser.py` 与 `src/crawler/pipeline.py`，因此按既有
构建流程重建候选产物，并与历史记录分开记账。收尾时又改了 `tests/` 与 `specs/`，而 sdist
按配置打包 `tests/`、`docs/`、`specs/`，故再构建一次使随包快照与工作树一致（源码未再变，
wheel 内容判定见下表）：

- **wheel（当前候选，与工作树一致）**：`71895c789971a2ec358aa387bad262af5ec9b4b24c7c4355d805456cbbc7fe4b`
  （136857 字节）。两次构建（源码改动后、测试/文档收尾后）哈希相同，可视为对该 `src/` 的确定性产物。
- **sdist（当前候选）**：`b60f469151e864cc8bdf4d9c4dd7edc8a030595618e9c6d38739d1f7b4628ac2`
  （776729 字节）。sdist 打包 `tests/` 与 `specs/`，因此测试文件或证据文档变更后需重建；包内
  `tests/test_legacy_office_real.py` 与工作树逐字节一致。
- 本轮被覆盖的中间候选（均已备份到执行机 `/tmp/dist-historical/`）：
  wheel 首建 `855c03084450480541716f24e6d24607b593f40965dd356681239e17f0f90caa`（136861 字节）；
  sdist 首建 `f5f79b38aa51a0b68cd2a9db502e24519e4be1eb5b815cd8750d8117ae91f350`（768553 字节）、
  二次 `6dc8130054e364783864a741fd81eaab163a524ed928d8e24143967f9efb951f`（771698 字节）、
  三次 `25b4eaeadacbc434d22d62fcc540a6c66c4403eef3f7d1133728b36132a9e900`（772667 字节）、
  四次 `f4c76c78c6aeb772e4eb924fd2efaf6eb6c110065a660b79b87c453639be3d86`（776441 字节）。
- 历史（2026-09-11 NEXT-09 核对）：wheel `866324e160a75479032a3651d13c19320b9c11c191e7299aff0398c583e9dec7`（136424 字节）、
  sdist `2c7399c52a128846abc04882aab46a156a70c3898dc85935ebf0309c053e96d0`（715340 字节）。

wheel 跨两次构建哈希一致，说明同一 `src/` 下产物可复现；内容一致性另有成员逐一比对为准。
sdist 内含构建时的 `specs/` 快照，因此包内本文件记录的是
构建前的哈希行（包内 `delivery-inventory.md` 的指向行同理）——文档自引用，属预期。
除此之外，源码、`tests/`、`tools/`、夹具与包内内容一致：构建后只再改了本证据文件与
`delivery-inventory.md` 的说明行，未改任何代码或测试。

`dist/` 仍由 `.gitignore` 排除、不随仓库交付；被覆盖的候选均已先备份到执行机
`/tmp/dist-historical/`（`round1-855c0308-wheel.whl`、`round1-f5f79b38-sdist.tar.gz`、
`round2-71895c78-wheel.whl`、`round2-6dc81300-sdist.tar.gz`、`round3-71895c78-wheel.whl`、
`round3-25b4eaea-sdist.tar.gz`、`round4-71895c78-wheel.whl`、`round4-f4c76c78-sdist.tar.gz`），
更早的历史两份也在同目录，避免旧产物被静默覆盖。

```bash
# 构建（本机沙箱无网络且默认缓存只读：用只读缓存里的 hatchling 1.27.0 及其依赖 +
# --no-build-isolation，避免联网解析 build-system.requires）
PYTHONPATH=<缓存内 hatchling/pathspec/pluggy/packaging/trove_classifiers/editables 目录> \
  UV_CACHE_DIR=/tmp/crawl-uv-cache uv build --no-build-isolation
# 随包契约与源一致性
uv run --locked --no-python-downloads python tools/sync_contracts.py --check   # 契约一致：6 个文件
```

| 检查项 | 结果 |
| --- | --- |
| wheel 内 `crawler/**` 成员 | 70 个；其中 63 个 `.py` 与 `src/crawler/` 同名文件逐一 sha256 比对，无差异、无缺失 |
| 随包契约 | `crawler/contracts/*.schema.json` 6 个，与规格目录逐字节一致（`sync_contracts --check`） |
| 随包来源注册表 | `crawler/config/sources.yaml` 在包内 |
| sdist 快照 | 248 个成员；打包 `tests/`、`tools/`、`docs/`、`specs/`，其中 `tests/test_legacy_office_real.py` 与工作树逐字节一致，两个旧格式夹具与 `tools/make_legacy_fixtures.py` 均在包内 |
| 入口点 | `[console_scripts] crawl = crawler.cli:main` |
| 新能力随包 | wheel 内 `legacy_parser.py` 含新失败分支、`pipeline.py` 含 `legacy_converter` 注入点 |
| 源码外执行 | 独立 venv（依赖副本，`/tmp/candidate-venv`）安装**当前候选** wheel，`cwd=/tmp/candidate-run`、`CRAWL_DATA_DIR=/tmp/candidate-data`：`crawl sources` 退出码 0（读包内 `crawler/config/sources.yaml`，version=0.1.0、digest=a195a6e5、1 条 DEMO 禁用），`crawl check` 退出码 0（manifest=10、documents=10、blocks=489、failures=2、schema 通过、追溯 100%）；`site-packages` 内 `legacy_parser.py` 与本轮 `src/` 版本 sha256 相同，`CrawlPipeline.__init__` 含 `legacy_converter` 形参 |
| 旧格式能力 | 源码外解释器 `is_legacy_office` 识别 OLE2、`find_soffice()` 返回 `/usr/bin/soffice`、截断 `broken.doc` 显式抛 `LegacyFormatError`（沙箱内组件被拒时为 `code=1`，仍为显式失败，非空成功） |

限制：本次构建使用缓存内的 hatchling 并关闭构建隔离（沙箱无网络、默认缓存只读），
与 [NEXT-08](next08-packaged-contracts.md) 的隔离构建在构建环境上不同；包内成员一致性检查
不受影响。源码外执行用的是项目 venv 依赖副本，不是镜像全新安装，因此不替代 NEXT-08 的
“普通安装”结论，也不把本候选写成已发布产物。

## 限制（不得省略）

- 样本是本项目自产的虚构夹具，**不是真实站点下载件**，不构成 T026/Q12/Q13 的正式来源验收；
  也未覆盖真实机构文档中的复杂排版（多级表格、合并单元格、文本框、宏、加密文件等）。
- 真实转换只在 LibreOffice 24.2.7.2 上验证；换组件版本或换平台需重新核对样本字节与结构。
- 依赖 LibreOffice 的 5 项用例已在本机正常 shell 复跑（13 passed，2026-09-13），用例级
  证据闭合；受限沙箱内它们按能力探测 skip 并有本次诊断记录，skip 仅代表执行环境不支持，
  不能当作通过。
- `soffice_converter` 仍是同步阻塞调用（超时上限 120 秒），未涉及并发或服务化改造。

## 本轮交接状态

本轮改动（源码修复、注入点、夹具、工具、用例与门禁、文档与证据）已提交：代码与夹具部分
首次提交时统计为 27 files changed, 1057 insertions(+), 50 deletions(-)；随后按用户要求把本轮
提交合并为一条阶段四交付提交（含 NEXT-04/T012、NEXT-10 澄清材料与「仍需解读事项（含阶段四
归属）」），当前提交号见 `git log -1`。提交主题：

```text
阶段四：真实旧式 DOC/XLS 转换与追溯（NEXT-04/T012）并给出 NEXT-10 分块澄清
```

本轮提交命令（已在**不受限沙箱**的正常 shell 执行）：

```bash
cd /home/zhou/workspaces/crawl && git add -A && git commit -F /tmp/commit-message.txt
git reset --soft 627b74b && git commit -F /tmp/commit-message.txt   # 合并本轮提交，基线 627b74b 不变
```

依赖组件的用例已在本机正常 shell 复跑完毕（2026-09-13，`13 passed in 4.63s`，见上文）。
至此 NEXT-04 的三类证据都已闭合：真实转换与结构核对（上一轮在本机执行）、样本结构级
真实性（不依赖组件，仓库内可复跑）、组件用例级验证（13 passed）。复跑命令保留在
“用例与可复跑命令”一节，供换机或回归时使用。
