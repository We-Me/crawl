# T026 十八来源状态记录（raw 优先开发）

> 61e34d8 后复核口径：下文 9/0/9/0 为原执行时点的有限样本与访问状态，保留原统计；不表示“无剩余实现”。已验证来源仍可能缺列表分页、附件覆盖与发现响应归档。TLS/网络、边界与明确 robots 禁止需分因处理；当前任务见 [阶段五](../stage-five.md)。

日期：2026-09-13（Asia/Shanghai）。依据：`raw-first-development.md`（全部 18 来源、运行时起始时间、
最小结构分块）、`scope-and-blocking.md`、DEV-010（按交付物选择最小必要验证）与 DEV-012（有限真实站点测试）。
本轮代码基线含：按站发现抽象（`src/crawler/discover/strategies.py`）、运行时起始日 `--start-date`
（`src/crawler/schedule/scope.py`）、最小结构分块（`src/crawler/normalize/segmenter.py`）。

状态口径（互不替代）：

- **已实现并验证**：有适配规则，且在真实站点上完成有限运行（有原件、账本与文档）；
- **实现待验证**：有规则或可从已归档原件复算，但尚无该来源的线上运行证据；
- **访问受限**：robots、可达性或网络条件按规则拒绝，未请求页面或只取 robots.txt；
- **未完成**：入口/接口形态未落实，尚无实现。

说明：本轮线上运行按轮次登记目的、窗口（`--start-date 2026-09-06`，运行日前 7 天）、来源与请求预算
（2026-09-13 第六至四十一轮合计 171 个请求、0 失败，预算/截止停止均如实记录；第三十七轮为受限来源复核、
第四十一轮仅为恢复路径与条件请求抽查，无页面采集），
遵守 robots、限速与边界；证据见
`evidence/logs/t026-round6-limited.txt` 与 `evidence/logs/t026-realsite-smoke.txt`（2026-09-11 五轮 69 请求）。
“登记启用”不等于“验收通过”；零文档不按通过处理。

## 逐站状态

| 来源 | 入口 | 发现策略与实现状态 | 日期处理 | 分块 | 原件 / 文档 | 上次真实核验 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CN-01 外交部 | `www.mfa.gov.cn/eng/`（+`/eng/wjbzhd/`） | list + 文章规则 `eng/xw/zyxw/<YYYYMM>/t<id>_<id>.html`（`max_pages: 1`）；**已实现并验证**（3 篇文章，6 请求） | 文章页日期 2026-09-12，判定 `in_window`；起始日包含式下界在真实数据上成立 | `structural_blank_line_v1`，94 块/3 篇 | 6 / 6 | 2026-09-13 | 栏目索引 `/eng/xw/zyxw/` 线上复验；旧域 `fmprc.gov.cn` 别名待 Q12 |
| CN-02 条约数据库 | `treaty.mfa.gov.cn/web/index.jsp`（站点根为 JS 跳转壳） | search：`list.jsp?chnltype_c=all&keywords={query}` + `detail1.jsp?objid=` 规则（`max_pages: 1`）；**已实现并验证**（检索页 10 个目标，取到条约详情与 PDF 附件） | 详情页日期是条约生效/签署时间（2018.01.19、2009.07.01），按语义不写入 `publication_date` → `date_unknown` 保留并记原因 | `structural_blank_line_v1`，6 块/篇 | 6 / 4 | 2026-09-13 | 列表通道（栏目）仍未实现；第 17 轮预算停止后第 18 轮以 `--no-attachments` 完整通过（status=ok） |
| CN-03 法律法规数据库 | `flk.npc.gov.cn/` | robots 命中 `Disallow /`；**访问受限**（只取 robots.txt） | 不适用 | 不适用 | 0 / 0 | 2026-09-11 | 按其规则申请允许的访问方式或使用公开接口（Q12） |
| CN-04 政策文件库 | `www.gov.cn/`（首页；“最新政策”`/zhengce/index.htm` 为前端渲染） | list + `/zhengce/*content_<id>.htm`；**已实现并验证**（3 份政策文件/解读，5 请求）。搜索库入口 `sousuo.www.gov.cn` robots `Disallow /` | 政策页 `<meta name="firstpublishedtime">`；解析器已支持并离线复算（2026-09-10/11 判 `in_window`）；第九轮已写文档为修复前结果（未回填） | `structural_blank_line_v1`，54 块/3 篇 | 6 / 6 | 2026-09-13 | 政策文件列表分页；允许的接口/检索方式（Q12） |
| CN-05 西藏自治区人民政府 | `www.xizang.gov.cn/` | robots HTTP 508 → 按不可用保守拒绝；**访问受限**（第 37 轮复核仍 508，稳定复现） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 确认可达性与允许方式（Q12） |
| CN-06 西藏外事办 | `wsb.xizang.gov.cn/` | 同上（robots 508）；**访问受限**（第 37 轮复核仍 508） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 同上 |
| CN-07 西藏民委 | `mw.xizang.gov.cn/` | 同上（robots 508）；**访问受限**（第 37 轮复核仍 508） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 同上 |
| CN-08 新华网 | `www.news.cn/xinhuashe/` | list + `div.newsTitle a` + `#detailContent`；**已实现并验证**（1 篇 in_window；2 篇 `before_start_date` 只留原件不产文档） | 文章日期 2026-09-06（等于下界→收录）、2026-09-05、2026-08-28（排除） | `structural_blank_line_v1`，6 块（收录篇） | 4 / 2 | 2026-09-13 | 正文选择器在更多文章页的覆盖率；分页规则 |
| IN-01 MEA | `mea.gov.in/`（+`/bilateral-documents.htm`） | list + 文档规则 `mea\.gov\.in/…dtl/<id>`（`max_pages: 1`）；**已实现并验证**：栏目页 `bilateral-documents[.htm]` 与 `press-releases.htm` 静态 HTML 无 `?dtl/` 链接（`zero_results`）→ 改用首页入口（首页原件含 `?dtl/<id>` 文稿链接），第二十六轮采集 1 篇文稿（5 请求、0 失败） | 文稿页无发布日期 → `date_unknown`（保留） | `structural_blank_line_v1`：线上 29 块/篇；已归档栏目原件离线复算 119 块/页 | 6 / 6 | 2026-09-13 | 文稿列表分页与附件下载按需扩展；栏目入口复验 |
| IN-02 MEA 条约库 | 站点自身列表端点 `/FrontEnd/FetchTreatyListGenericLatest?page=1&PageSize=10&sortBy=sortby`（人类入口 `treatylist-generic.htm` 与 `TreatyList?1` 为前端壳，无静态详情链接；`--entry-url` 可指向站点自身分页第 N 页） | list + 详情规则 `mea\.gov\.in/(TreatyDetail\?\d+|.*dtl/\d+)`（`max_pages: 1`）；**已实现并验证**：第 28 轮归档端点响应（HTML 片段含 `/TreatyDetail?<id>` 链接、共 433 页），第 29 轮采集 2 篇条约；**附件**：`attachment_pattern` 限定条约 PDF（第 38/39 轮，2 个 PDF 哈希与 referrer 核对通过） | 详情页有签署/生效日期（语义非发布日期，如 `Date of Signature 06/07/2026`）→ `date_unknown` 保留并记原因 | `structural_blank_line_v1`：线上 4 块/篇（2 heading + 标题段 + 元数据表） | 12 / 9 | 2026-09-13 | 检索参数与 Hindi 目录 PDF 按需扩展；条约日期语义另行处理（不写入 publication_date） |
| IN-03 India Code | `indiacode.nic.in/` | 入口可达，链接指向别名域 `indiacode.gov.in`；**访问受限（边界）** | 不适用 | 不适用 | 0 / 0 | 2026-09-11 | 域名别名关系待 Q12 后配置 |
| IN-04 eGazette | `egazette.gov.in/` | robots 获取失败（TLS 重置）→ 保守拒绝；**访问受限**（第 37 轮仍复现；curl verify=20） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 确认可达性/允许方式（Q12） |
| IN-05 MHA | `www.mha.gov.in/en`（站点根 302 到印地语 `/hi.html`） | list + `/en/` 文稿/通知/司局/媒体规则（`max_pages: 1`）；**已实现并验证**（离线命中 54 个目标；线上 2 份文稿、4 请求、0 失败）；**附件**：页内 PDF 同域取件（第 40 轮 1 个 PDF 哈希与 referrer 核对通过） | 文稿页无解析出的发布日期 → `date_unknown`（保留） | `structural_blank_line_v1`，125 块/2 篇 | 6 / 5 | 2026-09-13 | 印地语镜像与大量 PDF 页（如 AGMUT 97 个）按需分批扩展 |
| IN-06 PIB | `pib.gov.in/indexd.aspx?reg=48&lang=1`（英文桌面入口；根/`index.aspx` 为 6 KB 前端壳，脚本按 UA 跳转 indexd/indexm） | list + 详情规则 `pib\.gov\.in/PressReleaseDetail\.aspx\?PRID=\d+`，并按站点自身等价形态改写为 reader 页 `PressReleasePage.aspx?PRID=<id>`（`list_link_rewrite`，详情页正文在 iframe）；**已实现并验证**：第 36 轮 2 篇文稿（6 请求、0 失败） | `#PrDateTime` 发布日期（`date_selector`，如 `Posted On: 12 SEP 2026`）→ 2026-09-12、2026-09-13 判定 `in_window` | `structural_blank_line_v1`：线上 18–20 块/篇（标题/日期/正文/Release ID） | 10 / 10 | 2026-09-13 | 列表分页与附件按需扩展；reader 页语言随文稿本身（参数不改变变体，已记录） |
| IN-07 Census 数据目录 | `censusindia.gov.in/nada/index.php/catalog/` | robots 获取失败（证书链本机不可验证）→ 保守拒绝；**访问受限**（第 37 轮仍复现；curl verify=1） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 确认可达性/信任链（Q12） |
| IN-08 Ladakh 文化部 | `ladakh.gov.in/culture-department/` | robots 获取失败（TLS 重置）→ 保守拒绝；**访问受限**（第 37 轮仍复现） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 确认可达性（Q12） |
| IN-09 Sikkim 文化部 | `culture.sikkim.gov.in/` | robots 获取失败（TLS 重置）→ 保守拒绝；**访问受限**（第 37 轮仍复现） | 不适用 | 不适用 | 0 / 0 | 2026-09-13 | 确认可达性（Q12） |
| IN-10 Survey of India | `onlinemaps.surveyofindia.gov.in/` | list（通用规则选中 `Home.aspx`）；**已实现并验证**（真实站点 66 块、4 请求、0 失败；无需正文选择器） | 无发布日期 → `date_unknown`（保留） | `structural_blank_line_v1`；已归档原件离线复算 33 块（8 heading + 25 paragraph） | 2 / 2 | 2026-09-13 | 地图/附件专业页后续按需扩展 |

汇总：已实现并验证 9 个（CN-01、CN-02、CN-04、CN-08、IN-01、IN-02、IN-05、IN-06、IN-10）；实现待验证 0 个；
访问受限 9 个（CN-03、CN-05、CN-06、CN-07、IN-03、IN-04、IN-07、IN-08、IN-09 —— 其中 CN-03 为规则拒绝，
其余为 robots 508/获取失败或域名别名）；未完成 0 个。18 个来源均有记录，不等于 18 个来源通过。

## 本轮能力在真实数据上的验证（第六至四十一轮）

| 能力 | 证据 | 结论 |
| --- | --- | --- |
| 按站发现抽象 | CN-08 `list_pagination`、CN-01 文章规则、CN-04 政策规则；CN-02/IN-06 `not_implemented` | 策略状态区分 `ok`/`zero_results`/`selector_miss`/`not_implemented`/`access_restricted`/`request_error`，未以空结果冒充成功 |
| `--start-date` 包含式下界 | CN-08：2026-09-06→收录、2026-09-05 与 2026-08-28→保留原件不产文档；CN-01：3 篇 2026-09-12→收录；CN-04 离线复算 2026-09-10/11→收录 | 判定基于内容发布日期；未知日期保留候选并记原因（IN-01/IN-02/IN-10 首页无日期） |
| 恢复保留原范围 | 夹具用例（`tests/test_start_date.py`）；第六轮 CN-01 两次预算停止 | 停止运行的未处理项与失败账保留 `scope_start_date`，恢复不混入新窗口 |
| 最小结构分块 | CN-01/CN-04/IN-01/IN-02/IN-10 真实原件离线复算与线上文档；`tests/test_segmenter.py` | 标题/段落/列表项/表格独立块；div 内正文按空行拆块；嵌套容器不重复；源码缩进不拆块 |
| 日期 meta 兼容 | CN-04 `<meta name="firstpublishedtime">` | 解析器新增该 meta 名（夹具 + 真实原件复算），未回填旧文档 |
| 显式 URL 采集 | `crawl collect --url`（CN-02 入口与检索页、CN-02 详情离线分析） | `discovery_method=manual`；只给 `--url` 时不隐式跑入口；越界 URL 只记跳过；仍受 robots、起始日与预算约束 |
| form 包裹内容保留 | IN-10 `Home.aspx`（4 h2/17 p/2 table 全在 `<form>` 内） | 解析器改为只丢控件（input/select/option/textarea/button），保留 form 正文：离线复算 0 → 33 块，线上 66 块 |
| 站点自身端点作列表入口 | IN-02 `/FrontEnd/FetchTreatyListGenericLatest`（人类页面脚本调用的 HTML 片段端点）；第 28/29 轮 | 入口不限于完整页面：列表发现可直接解析端点返回的 HTML 片段；端点与规则按来源登记，`max_pages: 1` 限幅，不构造未公开接口 |
| 列表目标等价形态改写 | IN-06 `list_link_rewrite`：详情壳页 `/PressReleaseDetail.aspx?PRID=<id>` → 站点自身 reader 页 `PressReleasePage.aspx?PRID=<id>`（详情页 iframe src，第 33–36 轮）；`tests/test_discover.py` | 改写作用于链接解析后的绝对 URL，结果仍过来源边界检查（越界记跳过）；只登记站点自身等价形态，不构造未公开接口 |
| 按来源附件规则 | IN-02 `attachment_pattern: mea\.gov\.in/Portal/LegalTreatiesDoc/`（第 38/39 轮）；CN-02（第 14–18 轮，3 个 PDF）与 IN-05（第 40 轮，1 个 PDF）完整取件 | 附件候选入边界判定前按正则过滤，站点级 footer PDF 不入范围；附件原件按 `attachment_id`/`referrer_url` 关联母页，sha256 与账本逐条核对 |
| 按来源日期选择器 | IN-06 `date_selector: #PrDateTime`（`Posted On: 12 SEP 2026 6:11PM by PIB Delhi`）；`tests/test_html_parser.py`、月份缩写见 `tests/test_metadata_normalizer.py` | 命中且可验证到日精度才回填 `publication_date`，未命中/不可验证回落 meta 与正文启发式并保留 `raw_date_text`；不补造日期 |
| 预算停止的继续语义 | 第 41 轮：第 38 轮 IN-02 `deadline` 停止（`unprocessed=2`）后 `crawl plan` 为 0 项，`failed_records.jsonl` 仅 CN-04 一条失败及一条 `resolved` | 预算/截止停止**不入**补抓队列，继续方式为重跑该来源 collect（重新发现）；`plan`/`resume` 只处理失败账未解决任务，runbook 已按实测修正 |

## 数据与追溯（开发数据根 `data/`，gitignore，不复制进交付目录）

- 原件与账本：`raw/<source_id>/<date>/{html,...}`、`manifests/crawl_manifest.jsonl`（账本 63 条、文档 52 份、原件文件 59 个；`crawl check`：blocks=2452、失败 2、追溯 100%；附件经 attachment 契约校验）；
- 失败与跳过：`manifests/failed_records.jsonl`、运行指标 `logs/metrics.json` 与 `logs/metrics_history.jsonl`；
- 逐条校验：`validate_delivery(Path('data'))`、`trace_delivery(Path('data'))`（离线，只读）。

复跑命令（离线，无网络）：

```
uv run --locked --no-python-downloads python tools/offline_replay.py \
  --config src/crawler/config/sources.yaml --data-dir data --start-date 2026-09-06
```

## 逐站分页与附件核验（离线，2026-09-13）

| 来源 | 正文/列表分页 | 附件 |
| --- | --- | --- |
| CN-01 | 栏目与文章均为单页（无 `rel=next`/页码链接） | 归档页无附件链接 |
| CN-02 | 搜索/详情单页 | 3 个 PDF 已归档并核验（第 14–18 轮） |
| CN-04 | 政策列表为前端渲染，静态页无分页链接；检索通道受限（Q12） | 无附件候选 |
| CN-08 | 列表单页（无 `rel=next`） | 无附件候选 |
| IN-01 | 首页/栏目页单页；文稿页无分页链接 | 首页 4 个站点级 PDF（非文稿附件，未取） |
| IN-02 | 列表端点 433 页 `?page=N`（列表级，`max_pages: 1`；`--entry-url` 可指第 N 页）；详情单页 | 条约 PDF 已取（`attachment_pattern` 限幅，2 个核验） |
| IN-05 | 栏目/文稿单页 | 同域 PDF 可取（1 个核验；AGMUT 页 97 个待分批） |
| IN-06 | 列表页无页码链接（站点自身 `allRel` 为前端壳）；reader 单页 | 文稿页无附件链接（已核验；站点级文档在 static CDN 域，未纳入边界） |
| IN-10 | 无分页标记 | 无附件候选 |
| 受限 9 个 | 不适用（未请求页面） | 不适用 |

## 明确未完成与暂缓

- 后处理质量（正文精细抽取、OCR 准确率、近似去重阈值）仍 deferred，不作为本记录通过项；
- CN-04 第九轮已写文档的 `publication_date` 为空（解析器修复前），未回填；后续采集/重解析按新规则执行；
- 附件下载：CN-02（3 个 PDF）、IN-02（2 个条约 PDF，含规则限幅）、IN-05（1 个 PDF）已验证哈希与母页关联；其余来源多为无附件候选或按需再启用（第 24 轮起多数轮次以 `--no-attachments` 控制预算）；
- 正文分页：已归档文章页均为单页（无 `rel=next`/页码链接）；能力已具备（pipeline parts + 夹具用例），
  出现多页正文的来源时再登记 `pagination_selector`，不在无证据时猜测配置；
- 域名别名（CN-01 旧域、IN-03）与受限来源的访问方式仍属 Q12，需要外部决定或站点许可。
