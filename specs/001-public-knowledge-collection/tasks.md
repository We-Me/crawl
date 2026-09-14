# 实施任务与交付里程碑

## 2026-09-14 审查后的当前状态

b6041ea 已有归档、分页游标、队列及对账实现；静态审查发现的六项一致性缺陷已按 [阶段六](stage-six.md) 的 R6/R5 → R3/R4 → R2/R1 顺序修复并验证（定向 103 passed、完整回归 492 passed，提交与证据见该文件）。本段之后的“工程完成、队列清空、无新增”只代表历史执行结果。已确认业务范围不重开，高级后处理与发布仍暂缓；已有数据只做只读评估，不继续无目标巡检。

## 当前实施入口

当前按 [阶段六](stage-six.md) 的缺口与证据要求推进。用户六项决定已确认，T012 已完成；T019/T026/T027 总任务仍部分完成。表内旧阶段证据保留其时点意义，不能把“等待首批名单/分块/发布”作为当前阻塞。任务编号与历史验收不重排；当前操作计划只维护在阶段五，避免两份待办表漂移。

## 当前适用入口

已确认业务边界见 [raw 优先决定](raw-first-development.md)，当前实现缺口、任务顺序和完成标准统一见 [阶段六](stage-six.md)。本文历史阶段判断不覆盖该入口；已决定的范围不重复确认，已有能力不重新开发。

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。第四阶段整体仍未完成（T019/T026/T027 与正式业务待决）。下文早期缺组件/权限记录按历史时点理解，不再作为等待安装的理由。

版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

任务状态随实现更新：已完成项勾选并附证据，未完成项保持未勾选。代码路径为计划路径，实际实现见证据链接。COMMON 表示公共任务。业务优先级见 spec.md；没有输入依据支持工期、人天或承诺日期，因此不编造排期。

T001 按相关 Q 项逐项推进，不必等全部领域问题决定后才处理采集样本；T002 冻结当前范围需要的契约及 Python 版本/框架选型，相关记录写入 tech-stack.md。条件任务仅在对应范围入选后启动。为维持可核对的依赖顺序，此处不将共享接口尚未稳定的任务标成可并行。

## G0 规格评审

- [ ] T001 [COMMON] 逐项记录范围选择、适用来源和业务阈值；将影响当前任务的 Q 项由待决更新为有署名依据的决策。

  依赖：无。角色：需求负责人。计划路径：`specs/001-public-knowledge-collection/clarifications.md`。需求：规格治理或支撑任务，见说明。

  完成标准：已选范围明确，受影响文档同步更新；未选领域范围仍保留追踪。

- [ ] T002 [COMMON] 冻结数据契约版本及 ID/哈希/引用/空值规则；按 tech-stack.md 使用 uv，优先以 Python 3.9 构建完整环境，仅在失败证据充分时逐个次版本提高；按 DEV-007 保守选择成熟依赖的兼容正式稳定版本，完成框架/依赖选型并记录锁文件差异与验证结果。

  依赖：T001 的相关契约决策。角色：架构负责人。计划路径：`specs/001-public-knowledge-collection/contracts/；specs/001-public-knowledge-collection/tech-stack.md`。需求：规格治理或支撑任务，见说明。

  完成标准：schema、样例和语义规则一致；当前模块的 TD-01/TD-02 选择及验证证据记录齐全，未选组件不默认引入。

  证据（2026-09-11）：环境与依赖选型部分已完成，见 `specs/001-public-knowledge-collection/evidence/T002-selection.md`；数据契约冻结仍待 T001，因此本任务保持未勾选。

## G1 公共基础

- [x] T003 [COMMON] 依据已验证的 Python 选型，用 uv 建立 .venv、pyproject.toml、uv.lock 和 .python-version，按 project-startup.md 配置 src 包发现、安装并初始化采集模块并构建网页、附件、OCR、表格、失败和版本固定样本。

  依赖：T002。角色：开发负责人。计划路径：`src/crawler/；tests/fixtures/`。需求：规格治理或支撑任务，见说明。

  完成标准：项目可本地加载样本；不请求真实站点即可跑通接口桩；验证 CFG-01/CFG-09 的目录与安装行为。

  证据（2026-09-11）：工程、构建配置、固定样本、CFG-01/CFG-09 与离线接口桩（本地夹具站点加采集管线）已完成，见 `evidence/T003-environment.md`；本任务已完成。

- [x] T004 [US1] 实现来源注册、配置校验、访问边界与站点规则检查；新增统一 settings 接口读取 CRAWL_ENV/CRAWL_DATA_DIR，按起步说明校验优先级、路径和权限。

  依赖：T003。角色：采集开发。计划路径：`src/crawler/config/settings.py；src/crawler/config/sources.yaml；src/crawler/config/registry.py`。需求：FR-001、FR-002。

  完成标准：非法来源拒绝；配置变更可追溯；域外跳转不会越界；CFG-01—CFG-05 通过并有证据。

  证据（2026-09-11）：settings 接口、CFG-01—CFG-05、来源配置校验、访问边界与逐跳重定向拒绝已通过，见 `evidence/T003-environment.md` 与 `evidence/T004-T009-collection.md`；同日按 FR-001/S3 C02 补上 robots.txt 规则执行（按主机缓存、最长匹配、不可用保守拒绝；页面记跳过、附件记 `final_action=skip`），见 `evidence/logs/t004-robots.txt`；本任务已完成。

## G2 采集闭环

- [x] T005 [US1] 实现栏目分页、结构化搜索、宽泛词、补漏、sitemap/API 和附件发现，保存实际策略。

  依赖：T004。角色：采集开发。计划路径：`src/crawler/discover/`。需求：FR-003、FR-004。

  完成标准：固定样本的预期详情和附件被发现；关键词不产生最终分类。

  证据（2026-09-11）：栏目分页、搜索、sitemap、API 与附件发现均有夹具测试，见 `evidence/T004-T009-collection.md`；本任务已完成。

- [x] T006 [US1] 实现详情完整获取、附件下载、重定向白名单和可配置退避限速。

  依赖：T005。角色：采集开发。计划路径：`src/crawler/fetch/http_client.py；src/crawler/fetch/downloader.py`。需求：FR-005、FR-006、NFR-003。

  完成标准：分页、展开、接口、失败附件、429 与永久 4xx 的测试结果符合规格。

  证据（2026-09-11）：逐跳边界、限速、退避（含读取超时重试与连接超时耗尽上报）、Retry-After、展开正文抽取与附件下载测试见 `evidence/T004-T009-collection.md`；同日补齐来源级速率、连接/读取超时与重试上限的实际生效（NFR-003“按站点调整”），见同页“来源级请求参数”；并按 FR-005 补上正文分页（三页样本，含部分失败标 partial）与接口正文（`<link rel="alternate" type="application/json">` 声明的正文档端点）还原，见同页“正文分页与接口正文还原”；本任务已完成。阶段三 NEXT-06 追加：robots、重定向每跳、重试、分页/接口与附件在发送前共用统一请求预算，达到请求上限或截止时间即停（退出码 3），见 `evidence/next06-budget.md`。

- [x] T007 [US1] 实现原件归档和 manifest 写出，确保原件存在后账本才可引用。

  依赖：T006。角色：采集开发。计划路径：`src/crawler/output/raw_store.py；src/crawler/output/manifest_writer.py`。需求：FR-007、FR-008。

  完成标准：成功资源字节一致且可由账本定位；中断恢复无悬挂原件引用。

  证据（2026-09-11）：原件原子写入、相同字节复用、越界拒绝、账本哈希校验与中断无残留测试见 `evidence/T004-T009-collection.md`；本任务已完成。

- [x] T008 [US1] 实现最小 HTML 正文与结构提取，供文档标准化和交付最小闭环使用。

  依赖：T007。角色：解析开发。计划路径：`src/crawler/parser/html_parser.py`。需求：规格治理或支撑任务，见说明。

  完成标准：单个公开网页样本可生成完整正文与原始块。

  证据（2026-09-11）：DOM 顺序块、表格结构、锚点、编码与缺失元数据测试见 `evidence/T004-T009-collection.md`；同日按真实页面（CN-04）暴露的缺陷补上“空标题块不产出、标题取首个非空标题”修复与回归用例 `tests/test_html_parser.py::test_empty_headings_are_skipped_and_do_not_blank_the_title`，原失败页经本地重解析补全（0 新请求），见 `evidence/logs/t008-cn04-defect-fix.txt`；本任务已完成。

- [x] T009 [US1] 实现 document 规范化、状态和元数据缺失规则、明确的 manifest 关联，并按已冻结块契约写出最小 HTML 结构块。

  依赖：T008。角色：数据开发。计划路径：`src/crawler/normalize/document_schema.py；src/crawler/output/documents_writer.py；src/crawler/output/blocks_writer.py`。需求：FR-009。

  完成标准：首个 HTML 加附件样本形成原件、账本、文档及结构块的可追溯闭环。

  证据（2026-09-11）：端到端闭环、失败附件、关键词不分类与采集边界测试见 `evidence/T004-T009-collection.md`；本任务已完成。

## G3 多格式结构

- [x] T010 [US2] 完善跨格式原始结构块模型、顺序和引用，在最小 HTML 闭环基础上扩展结构类型，禁止 token/语义重组。

  依赖：T009。角色：解析开发。计划路径：`src/crawler/normalize/block_schema.py；src/crawler/output/blocks_writer.py`。需求：FR-010。

  完成标准：长段落、列表、表格与标题顺序一致，引用不悬挂。

  证据（2026-09-11）：共享 ParsedBlock/ParsedPage 模型新增 page_no/confidence/section_path/article_no，块契约校验定位字段与页码顺序，见 `evidence/T010-T013-parsers.md`；本任务已完成。

- [x] T011 [US2] 实现文本 PDF 和 OCR 的页码、方法、置信度及部分失败处理。

  依赖：T010。角色：解析开发。计划路径：`src/crawler/parser/pdf_parser.py；src/crawler/parser/ocr_parser.py`。需求：FR-011。

  完成标准：文本和扫描样本可回页定位，OCR 异常有明确状态。

  证据（2026-09-11）：文本 PDF 逐页段落/表格、扫描件 OCR 页码与置信度、空页与部分/全部失败状态均有固定样本用例，见 `evidence/T010-T013-parsers.md`；本任务已完成。

- [x] T012 [US2] 实现 Office、CSV、JSON/XML/API 的原始结构保留及已冻结的结构数据表达。

  依赖：T010。角色：解析开发。计划路径：`src/crawler/parser/docx_parser.py；src/crawler/parser/xlsx_parser.py；src/crawler/parser/api_parser.py`。需求：FR-012。

  完成标准：不同格式样本均保留结构；旧式 DOC/XLS 的支持路线已验证。

  证据（2026-09-11）：DOCX/XLSX/CSV/JSON/XML 结构夹具通过，分派器按内容与扩展名选择解析器；旧式 DOC/XLS 经 OLE2 识别 + LibreOffice 转换路线验证（本机无 soffice，缺组件时明确报错），见 `evidence/T010-T013-parsers.md`；历史记录中的“完成”仅覆盖已有工程验证；本次按完整完成标准更正为部分完成，剩余项见下方续作说明。

  证据（2026-09-11，环境核实）：目标 Linux（Ubuntu 24.04.4 LTS）未安装 LibreOffice，apt 候选 `libreoffice-writer`/`libreoffice-calc` 4:24.2.7 可用（Ubuntu 镜像），但 sudo 需密码、无 root 授权，本轮未安装；缺组件时 `parse_legacy` 显式抛出 `LegacyFormatError`，不静默回退，见 `evidence/logs/t012-libreoffice-env.txt`。

  证据（2026-09-13，真实旧格式转换完成）：用户先前安装的 LibreOffice 24.2.7.2 420(Build:2)（`/usr/bin/soffice`）已用于真实 OLE2 样本验证。新增自产固定样本 `tests/fixtures/office/notice.doc`（sha256 `71dd62f6…`，MS Word 97）与 `notice.xls`（sha256 `aa8bbcb0…`，MS Excel 97-2003），由 `tools/make_legacy_fixtures.py` 从既有 OOXML 夹具经系统组件生成（DOC 走 ODT 中转以保留表格），非改扩展名伪文件。经现有 `parse_attachment`→`parse_legacy`→`soffice_converter` 路线实测：DOC 转出 6 块（heading L1/paragraph/heading L2/list_item×2/table，表头 `Item/Quantity/Amount` 与 2 行数据保留）；XLS 转出 3 个 sheet 状态 `ok/ok/empty`，Summary 表头（含单位）、2 行数据、Notes 表保留，空 sheet 记 `sheet_3_empty`；截断 OLE2 触发显式 `LegacyFormatError`，无空成功。原件保留与 documents/blocks 追溯链路经 `tests/test_legacy_office_real.py` 覆盖（含注入转换器的管线接线用例，已通过）。本轮同时修复失败消息误报退出码的缺陷（LibreOffice 无法加载源文件时以 0 退出且不产出文件，原实现报 `code=0`）。完整记录、样本来源与限制见 `evidence/next04-legacy-office.md`。受限沙箱内 5 项依赖组件的用例按能力探测 skip（`which` 到二进制但转换被沙箱拒绝，如实报 skip 而非失败；`needs_soffice` 已从“二进制存在”改为“样本真的转换成功一次”）；13 项用例已全部通过——8 项不依赖组件在沙箱内通过（含 OLE2 流结构校验），5 项依赖组件的用例已于 2026-09-13 在目标 Linux 正常 shell 复跑通过（命令见证据文件），不影响已完成的能力验证。

- [x] T013 [US2] 统一清洗、日期、URL、语言和不改写约束，复核各解析器全文一致性。

  依赖：T011 T012。角色：数据开发。计划路径：`src/crawler/normalize/metadata_normalizer.py`。需求：FR-013。

  完成标准：不补造日期、不翻译正文、不因文本长度裁剪。

  证据（2026-09-11）：text_utils/date_utils/metadata_normalizer 统一清洗与日期、URL、语言规则（含天城文按脚本识别为 hi、显式标记优先、超长段落不裁剪），全部解析器通过全文一致性复核，见 `evidence/T010-T013-parsers.md`；本任务已完成。

## G4 更新与恢复

- [x] T014 [US3] 实现精确及近似重复识别、来源关系、版本保留、现行状态和下线记录。

  依赖：T013。角色：数据开发。计划路径：`src/crawler/dedup/；src/crawler/versioning/`。需求：FR-014、FR-015。

  完成标准：转载不丢来源；修改条款生成新版本；旧版和下线不会删除历史。

  证据（2026-09-11）：精确/近似重复分组（近似阈值必须显式传入）、转载与修订关系及证据要求、版本判定与保留、现行状态与下线历史均有测试覆盖，见 `evidence/T014-dedup-versioning.md`；本任务已完成。

- [x] T015 [US3] 实现资料类型增量、条件请求、七类已选频率和触发关系。

  依赖：T014。角色：采集开发。计划路径：`src/crawler/schedule/；src/crawler/config/sources.yaml`。需求：FR-016、KR-012。

  完成标准：304 不产生虚假文档；新闻、法规、统计和类别更新按配置运行。

  证据（2026-09-11）：七类频率与触发表、按资料类型的增量计划、ETag/Last-Modified 条件请求与 304 复用、增量状态文件与配置校验均通过，端到端第二次采集 0 新文档，并按 news/law/statistics 三类资料补齐“新增新闻/未改法规/新年份统计”场景，见 `evidence/T015-schedule.md`；本任务已完成。

- [x] T016 [US3] 实现分阶段失败账、补抓和运行恢复，保留历史失败及原始成功下载。

  依赖：T015。角色：采集开发。计划路径：`src/crawler/monitor/failures.py；src/crawler/fetch/retry.py`。需求：FR-017。

  完成标准：四阶段失败均可复现，对账可解释。

  证据（2026-09-11）：四阶段失败按网络/本地分流补抓，失败账只追加并保留历史，网络重取与原件重解析端到端通过，中断后可列出待补全原件，见 `evidence/T016-recovery.md`；同日以真实站点失败样本复验（CN-04 `normalize` 失败 → `reparse` 0 请求补全、原件 sha256 不变），并修正 `resume_failures` 会串处理其他来源失败的缺陷（新增 `tests/test_recovery.py::test_resume_failures_only_handles_requested_source`），见 `evidence/logs/t008-cn04-defect-fix.txt`；本任务已完成。阶段三 NEXT-06 追加：resume 与 collect 共用同一预算语义，停止时报告未处理任务并保留已恢复成果；NEXT-07 的 CN-08 离线重解析也走该路径，见 `evidence/next06-budget.md`、`evidence/next07-cn08-body.md`。

- [x] T017 [US3] 实现日志、计数、重复与异常统计，区分请求、资源、文档和块。

  依赖：T016。角色：运维开发。计划路径：`src/crawler/monitor/logger.py；src/crawler/monitor/metrics.py`。需求：FR-018。

  完成标准：混合运行日志及全部成果按已定口径可对账。

  证据（2026-09-11）：logs/crawler.log 与 logs/metrics.json（口径定义+对账结果）已实现，请求/资源/文档/块分别计数，重复候选保留全部来源且近似阈值保持 Q11 未决，见 `evidence/T017-logs-metrics.md`；本任务已完成。

## G5 采集验收

- [x] T018 [US4] 在配置数据根下按已选 S1 子目录组织六项成果，统一原件、JSONL、日志及重解析路径，检查采集范围禁令和相对路径。

  依赖：T017。角色：交付开发。计划路径：`src/crawler/output/；配置数据根（开发默认 data/）`。需求：FR-019、FR-020。

  完成标准：完整交付包可读取，原件可定位，采集包中没有 RAG 派生成果。

  证据（2026-09-11）：DeliveryLayout 统一六项成果与全部读写路径，inspect_delivery 检查成果完整性、相对 raw_path 与 FR-020 禁令，重解析拒绝越界路径，见 `evidence/T018-delivery.md`；本任务已完成。

- [ ] T019 [US4] 实施 acceptance 中采集用例及全量 schema/追溯校验，补齐 project-startup.md 的 CFG-01—CFG-09（含工程外目录、搬迁、路径越界及安装），记录质量样本和缺陷。

  依赖：T018。角色：质量负责人。计划路径：`tests/acceptance/；src/crawler/validate/`。需求：NFR-001、NFR-002、NFR-004。

  完成标准：所有入选采集需求有真实验收证据；未决阈值不得自动判通过。

  证据（2026-09-11）：AT-001—AT-024 夹具级验收 27 项（AT 用例，含 AT-005/006/007/016 的补充子句）、报告一致性 2 项、CFG-01—CFG-09 环境用例 9 项与 schema/追溯校验通过；AT-014/AT-024 因 Q11 在报告中固定 blocked，不判通过；校验同时发现并修正 parse_status 与附件状态枚举偏离契约的缺陷，见 `evidence/T019-acceptance.md`。CFG-09 另按交付态 wheel 做普通安装行为复核（工程外导入、无源码根报错、随包 sources.yaml 加载），并在本轮 AT 子句补强后按同一流程复验（新构建 wheel/sdist、构建后端仅来自登记镜像、行为逐条一致），见 `evidence/logs/t019-installed-wheel.txt`；AT 子句补强（AT-001/002/004/005/006/007/008/009/012/016/017/018/019/022/023，含正文分页与接口正文、重复内容附件身份、各类型逐字节归档、PDF→document 契约校验、下载成功+解析失败仍留原件/账本、交付检查不依赖摘要、零失败空失败账、编码错误定位、速率与并发分别建模）后全量 292 passed，真实页面缺陷修复后新增 2 项回归用例、全量 294 passed，见 `evidence/logs/t019-pytest.txt`；历史记录中的“完成”仅覆盖已有工程验证；本次按完整完成标准更正为部分完成，剩余项见下方续作说明。
  阶段三 NEXT-08 追加：运行契约随 wheel 交付（`src/crawler/contracts/`，与规格契约逐字节一致），`tools/sync_contracts.py --check` 与 `tests/test_contract_resources.py` 防止漂移；在源码外独立 venv 普通安装后，`sources`/`check` 对已有离线交付样本通过、资源缺失以退出码 2 清晰失败，见 `evidence/next08-packaged-contracts.md` 与 `evidence/logs/next08-installed-wheel.txt`。正式业务验收仍未执行。

## G6 领域扩展 条件任务

- [ ] T020 [US5] 实现来源国家、等级、机构和立场映射及原文证据记录。

  依赖：T002；Q01/Q10 已选择；T009 或等价固定文档样本。角色：领域开发。计划路径：`src/knowledge/provenance/`。需求：KR-001。

  完成标准：等级与类别分离；双方表述和来源证据可独立查询。

- [ ] T021 [US5] 实现 A/B/C 的协定、政策表述与法规关系及版本时效。

  依赖：T020；Q02/Q04/Q09 已选择。角色：领域开发。计划路径：`src/knowledge/agreements/；src/knowledge/statements/；src/knowledge/laws/`。需求：KR-002、KR-003、KR-004。

  完成标准：多语和版本不覆盖，条款可引用，问答和评论类型正确。

- [ ] T022 [US6] 建立 D 事件证据关联；只有内部导入范围获选后才实施独立受控导入。

  依赖：T020；Q02/Q09 已选择；内部子任务另需 Q16。角色：领域及导入开发。计划路径：`src/knowledge/events/；src/knowledge/controlled_import/`。需求：KR-005、KR-006。

  完成标准：公开事件证据可回溯；内部流程单独验权审计，不进入公共爬虫。

- [ ] T023 [US6] 实现 E/F 的区域社区限定、地名关系、地图来源视角和区划版本。

  依赖：T020；Q02/Q09/Q10 已选择。角色：领域开发。计划路径：`src/knowledge/culture/；src/knowledge/geography/`。需求：KR-007、KR-008。

  完成标准：文化不泛化；争议地图不融合；区域实体能回原文。

- [ ] T024 [US5] 实现 G 正式多语术语及概念对齐，保留缺失语言和辖区差异。

  依赖：T021；Q02/Q09 已选择。角色：领域开发。计划路径：`src/knowledge/terminology/`。需求：KR-009。

  完成标准：写法逐项有来源，不用自动翻译冒充官方名称。

## G7 检索交接 条件任务

- [ ] T025 [US5] 先补全检索、图谱和设备部署的独立规格及契约，再据此细分实施任务；保留 chunk 到文档和原件的关系。

  依赖：T021 T024；Q01/Q17 已选择；单独检索规格完成。角色：RAG 负责人。计划路径：`specs/002-knowledge-retrieval/；src/knowledge/chunking/`。需求：KR-010。

  完成标准：检索实现前已有单独评审规格；当前任务完成不等于已交付索引或设备软件。

## G5 来源验证

- [ ] T026 [US4] 对入选来源核验入口/规则并实现适配器，记录至少 10 词、歧义和站点专属要求的验收证据。

  依赖：T019；Q12/Q13 已选择；领域指标按 Q01 范围启用。角色：采集及质量负责人。计划路径：`src/crawler/adapters/；tests/acceptance/sources/`。需求：KR-011、KR-013。

  完成标准：每个来源有规则版本、样本和结果；未接入来源明确列出，不报告全站点完成。

  证据（2026-09-11，部分）：已按用户许可分批对 CN-01/CN-03/IN-01/IN-06 及其余 9 个权威来源做最小请求量核验（五轮共 69 个请求：14 + 9 + 15 + 22 + 9，18 个登记来源均完成浅层核验，遵守 robots、逐来源限速、不重试），记录 robots 判定、发现与解析结果、条件请求退化（无 ETag/Last-Modified）及站点约束——CN-03 全站 Disallow、IN-06 首页为前端壳、IN-01 栏目页可访问但通用发现选中首页、CN-01 栏目页 75 条链接指向旧域/子域、CN-05/06/07 的 robots 508 保守拒绝、IN-03 链接指向别名域、IN-04/部分主机 robots 获取失败——其中 CN-04 的真实页面缺陷已定位修复并本地重解析闭环（见 `evidence/logs/t008-cn04-defect-fix.txt`），完整记录见 `evidence/logs/t026-realsite-smoke.txt`；同日实现 T026 的机制部分（逐来源适配规则：列表链接选择器/正则、分页终止条件、正文范围选择器；未命中显式记录，不静默回退），在固定夹具与真实原件上验证（CN-08 栏目发现 13→3 条文档链接、CN-04 正文 145→2 块），见 `evidence/logs/t026-adapter-mechanism.txt`；五轮核验后的开发数据根交付校验通过（`validate_delivery` ok=True/errors=0、追溯 doc_rate=block_rate=1.0）；适配器（栏目级路径规则/域名别名）、至少 10 词与歧义验证仍待 Q12/Q13；同日按 NEXT-03 完成 CN-08 单站受限试点（试点卡 `pilot-cn08.md`，3 个请求完成栏目发现→文章获取→交付校验，见 `evidence/logs/t026-pilot-cn08.txt` 与 `evidence/T026-pilot-cn08.md`），本任务保持未勾选。
  阶段三 NEXT-07 追加：按已保存原件修复 CN-08 正文边界（`adapter.content_selector: "#detailContent"`，容器外标题按文档范围回退提取），相关阅读与重复标题不再进入正文，6 个正文段落逐字保留；离线差异与重解析证据见 `evidence/next07-cn08-body.md`。逐站取值版本、至少 10 词与歧义验证仍待 Q12/Q13，本任务保持未勾选。

## G8 交付收口

- [ ] T027 [COMMON] 执行全范围回归、成果交接和规格一致性复核，记录已交付范围、未交付项及可复跑步骤。

  依赖：T019 T026；所有被选中的领域任务。角色：交付负责人。计划路径：`specs/001-public-knowledge-collection/acceptance.md；运行说明及实际验收报告`。需求：规格治理或支撑任务，见说明。

  完成标准：需求、任务、测试、成果四者对应；只对真实完成项目勾选任务。

  证据（2026-09-11，部分）：正式业务 CLI（`crawl`，子命令 sources/collect/plan/resume/check，退出码 0/1/2）与 Linux 运行说明已完成并实际执行，命令输出见 `evidence/logs/t027-cli.txt`，说明见 `runbook.md`，汇总见 `evidence/T027-cli-runbook.md`；闭环中发现并修复“同日同来源多次运行 crawl_id 重复、补抓指向错误原件”的缺陷（回归见 `tests/test_pipeline.py::test_crawl_ids_continue_across_runs`）；阶段候选全量回归 325 passed（`evidence/logs/t027-full-pytest.txt`），锁文件未变、wheel 含 `crawl` 入口（`evidence/logs/t027-lock-wheel.txt`）。本任务保持未勾选：T019/T026 正式验收与来源决定仍未完成。
  阶段三追加：运行预算与停止报告（退出码 3，`evidence/next06-budget.md`）、随包契约与源码外安装（`evidence/next08-packaged-contracts.md`）已交付，runbook.md 同步真实命令、停止行为、退出码与剩余限制；阶段候选一次全量回归 345 passed（`evidence/logs/stage-three-full-pytest.txt`）。
  阶段四追加：工程交接清单交付 `delivery-inventory.md`（源码提交、Python/uv 与锁文件哈希、源码/契约位置、构建产物、运行说明、证据索引、组件缺口与未交付范围），决策输入备好 `decision-requests.md` 确认栏；本轮只做只读核对与文档校验，未重跑测试、未重建 wheel。本任务保持未勾选：T019/T026 正式验收与 Q12/Q13 来源决定仍未完成。

## 里程碑与独立交付

| 里程碑 | 任务范围 | 可检查成果 | 退出条件 |
| --- | --- | --- | --- |
| M1 规格与契约可实施 | T001—T003 的采集相关部分 | 范围决策、契约、固定样本和技术环境记录 | 当前范围关键 Q 已决，候选 schema 已冻结 |
| M2 最小采集闭环 | T004—T009 | 一个来源的 HTML 加附件文件闭环 | 原件、账本、完整文档和基础结构可追溯 |
| M3 多格式与增量 | T010—T017 | 多格式结构、版本、恢复、日志 | 格式和故障夹具验证完成 |
| M4 采集交付 | T018、T019、T026 | 入选来源的六类成果和验收证据 | 采集验收及来源验证通过 |
| M5 已选领域能力 | T020—T024；T025 先产出独立检索规格 | 所选 A—G 逻辑对象及来源关联 | 只对已选范围做领域验收；索引/设备另有规格 |
| M6 总体验收 | T027 | 实际运行说明和验收记录 | 每条入选需求有结果，范围外或缺陷明确记录 |

## 支撑任务的需求关系

T001/T002 支撑全部需求的范围和契约决策；T003 支撑固定样本基础；T008 是 FR-009/FR-010 的 HTML 解析前置；T027 收口全部入选需求。它们不是新增业务功能。具体执行验收用例见 acceptance.md；质量门槛来自四份原文及明确标注的设计展开，不要求机械地为每个小改动补测试。

## 镜像环境交付补充

T002 按 [uv 模板说明](uv-template.md) 核验登记镜像、依赖兼容性、锁文件来源和镜像失败不回退行为；T003 合并模板、配置 src 包安装，并用独立空缓存验证必要包安装及锁文件复现。完成环境验收后才能勾选；提供空依赖模板不算任务完成。

## 当前续作优先级与状态更正

以 [阶段续作说明](continuation.md) 为本阶段调度入口：NEXT-01/02 已完成，NEXT-03 工程试点已完成；NEXT-06/07/08 已完成；NEXT-09 交付清单与 NEXT-05A 决策确认栏已交付；NEXT-04 真实旧格式验证已完成（见下）；NEXT-10 已确认且最小实现已交付；NEXT-05B/C 的当前 raw 工作统一映射到 stage-five.md 的 S5-06，发布暂缓。NEXT 是现有任务子项，不改变 27 个 T 编号。

2026-09-13 更正：T012 已完成并勾选——DOCX/XLSX/CSV/JSON/XML 结构保留已有证据，真实 LibreOffice 24.2.7.2 下的 OLE2 DOC/XLS 转换、结构保留与失败路径已实测，原件追溯链路已由用例覆盖，见 `evidence/next04-legacy-office.md`；依赖组件的 5 项用例已于 2026-09-13 在目标 Linux 正常 shell 复跑通过（该文件 13 passed），能力已验证的事实得到用例级确认。T019：夹具级验证已完成，AT-014/AT-024 及正式业务验收尚缺，故保持部分完成。取消勾选不表示删除代码或重做既有有效测试。T003 依赖 T002 的已验证环境部分；T013 及后续已有工程结果在已验证格式上继续有效。T026 工程机制和有限探测可使用 T019 已有工程证据；正式来源验收仍依赖有关业务决定。T027 的 CLI 与交接准备可提前实施，但总体验收保留原依赖。

2026-09-11 续作进展：NEXT-01/NEXT-02 完成（正式 CLI 与 Linux 运行说明，见 `runbook.md`）；NEXT-03 产出 CN-08 试点卡并完成一次受限真实试点；NEXT-04 记录 LibreOffice 环境阻塞；NEXT-05 仍待 Q01/Q11/Q12/Q13 业务决定。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](stage-three.md) 与 [NEXT-06](evidence/next06-budget.md)、[NEXT-07](evidence/next07-cn08-body.md)、[NEXT-08](evidence/next08-packaged-contracts.md)。（原文记 NEXT-04 受 Linux 组件权限阻塞；该阻塞已由 2026-09-13 的真实转换验证关闭。）NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](decision-requests.md)）已交付；NEXT-04 的真实旧格式验证已于 2026-09-13 完成（T012 勾选），剩余正式业务待决见 [阶段四交付收口](stage-four.md)。T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成；NEXT-04 真实旧格式验证与 T012 勾选已完成（`evidence/next04-legacy-office.md`）；NEXT-10 已按用户决定实现独立结构/div 空行最小分块，无需再确认。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量与来源缺口继续保留，不因范围收敛自动通过。

2026-09-13 本轮进展（按站发现抽象、运行时起始日期、最小结构分块；不改变 27 个 T 编号）：

- T005/T015：新增发现策略抽象与 `--start-date`（`src/crawler/discover/strategies.py`、`src/crawler/schedule/scope.py`），
  贯通发现、采集记录、失败账与恢复；CN-08/CN-01/CN-04 已有限线上验证，日期边界与恢复原范围有夹具用例。
- T010/T013：新增分块抽象与最小 dummy（`src/crawler/normalize/segmenter.py`），保留既有 HTML/Office/PDF 处理能力；
  `extraction_method` 记 `<基础>+structural_blank_line_v1`。正式质量阈值仍 deferred。
- T026：18 来源逐站状态与线上登记见 [evidence/t026-eighteen-sources.md](evidence/t026-eighteen-sources.md)
  与 [evidence/logs/t026-round6-limited.txt](evidence/logs/t026-round6-limited.txt)；第 10—41 轮续作补齐逐站适配
  （站点自身列表端点作入口、`list_link_rewrite` 等价形态改写、`attachment_pattern` 附件限幅、`date_selector`
  发布日期），当前为已实现并验证 9 个、实现待验证 0 个、访问受限 9 个、未完成 0 个。**任务仍是部分完成**：
  受限来源的访问方式与域名别名（Q12/Q13）及正式全范围验收未完成，不勾选正式完成；交付基线全量回归
  406 passed（[evidence/logs/t026-full-pytest.txt](evidence/logs/t026-full-pytest.txt)），开发数据根 `crawl check`
  为 manifest=63、documents=52、blocks=2452、failures=2、raw_files=59、追溯 100%。
- T019/T027：raw 留存、失败账与追溯仍是部分完成（夹具与有限样本级），正式全范围验收不因本轮推进自动通过。
- 阶段五（61e34d8 后复核）：当前任务按 [stage-five.md](stage-five.md)。S5-01/03/04/06 可执行，S5-02 分因处理；S5-05/07 暂缓，不作为前置。没有新增第 28 个 T 任务，不重做现有抽象和最小分块。
- 阶段五实施（2026-09-13）：S5-01/03/04/06 已完成工程实施并通过离线夹具验证（新增 13 项用例，
  全量回归 419 passed），见 [evidence/stage-five-raw-completeness.md](evidence/stage-five-raw-completeness.md)、
  [evidence/logs/stage-five-full-pytest.txt](evidence/logs/stage-five-full-pytest.txt)。对应 T005/T006/T007/T015/T016
  的能力补齐记录在案；T019/T026/T027 仍为**部分完成**（正式验收与来源决定未完成），不因本轮勾选；
  T017/T018 的成果格式未变，S5-05（后处理质量）与 S5-07（发布运维）继续暂缓。
