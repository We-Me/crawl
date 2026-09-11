# 来源适配与检索规则输入登记

版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

本文登记 S2 已写出的来源适配输入，保留原有专站要求。它们没有因 S4 暂不整理而消失，也没有自动变成通用要求。入口与描述的原始核验日期为 S2 的 2026-09-07。2026-09-11 按用户许可对 4 个来源做了最小请求量核验（每站至多 3 个请求、遵守 robots、0.5 req/s、不重试），结果与站点约束见 [evidence/logs/t026-realsite-smoke.txt](evidence/logs/t026-realsite-smoke.txt)；同日又对 CN-01/IN-01 以栏目页入口（`/eng/wjbzhd/`、`bilateral-documents`）做了第三轮最小核验，确认栏目页可达但通用发现选中的是首页/子域页；第四轮再对 CN-02/CN-04/CN-05/CN-06/CN-07/IN-02/IN-03/IN-04/IN-05 做浅层可达性核验（CN-05/06/07 的 robots 508、IN-04 与部分主机的 robots 获取失败均保守拒绝，IN-03 链接指向别名域 `indiacode.gov.in`，CN-02 无可发现站内链接），并借 CN-04 真实页面修复空标题块缺陷。第五轮补齐 CN-08/IN-07/IN-08/IN-09/IN-10，至此 18 个登记来源均完成浅层核验（IN-07/08/09 的 robots 获取失败与 CN-03/CN-05/06/07 的 508 均按策略保守拒绝，IN-10 空正文按 partial 记录）。逐站规则版本、字段定位、至少 10 词与 Q12/Q13 决策仍属 T026。

逐来源适配规则的**机制**已实现（T026 机制部分）：来源可显式配置列表链接选择器/正则、分页终止条件与正文范围选择器；规则未命中一律记录（列表页记跳过、正文页记 `adapter_selector_miss` 失败并保留原件，修正后可本地重解析），不静默回退到通用规则。字段为候选，待 T002 冻结；逐来源取值、规则版本与核验日期仍待 Q12/Q13，见 [evidence/logs/t026-adapter-mechanism.txt](evidence/logs/t026-adapter-mechanism.txt)。

通用正文还原（FR-005）按确定性规则实现：内容区 `rel=next` 或明确翻页文案视为正文分页链接、`<link rel="alternate" type="application/json">` 视为接口正文档端点；站点专属的 DOM/接口形态、分页终止条件与字段名仍在 T026 逐站核验。具体启用哪些来源、时间范围、语种和调用参数由 Q13 决定；逐站点实现为 T026。来源类别是 A—G 知识类别，不是证据等级。原件字段、正文保真及追溯要求仍从通用契约继承。

## 首批来源目录

来源为 S2 附录 B109。所有来源当前状态均为“登记，未启用，未重新核验”。

| 编号 | 来源 | 原入口 | 知识类别 |
| --- | --- | --- | --- |
| CN-01 | 中华人民共和国外交部 | https://www.mfa.gov.cn/ | A/B/D/G |
| CN-02 | 外交部条约数据库 | https://treaty.mfa.gov.cn/ | A/G |
| CN-03 | 国家法律法规数据库 | https://flk.npc.gov.cn/ | C/G |
| CN-04 | 中国政府网政策 | https://www.gov.cn/zhengce/ | C/B |
| CN-05 | 西藏自治区人民政府 | https://www.xizang.gov.cn/ | C/E/F |
| CN-06 | 西藏自治区外事办公室 | https://wsb.xizang.gov.cn/ | E/B |
| CN-07 | 西藏自治区民族事务委员会 | https://mw.xizang.gov.cn/ | E/C |
| CN-08 | 新华社 | https://www.news.cn/ | B/D（补充） |
| IN-01 | Ministry of External Affairs (MEA) | https://www.mea.gov.in/ | A/B/D/G |
| IN-02 | MEA — Indian Treaties Database | https://www.mea.gov.in/treatylist-generic.htm | A/G |
| IN-03 | India Code | https://www.indiacode.nic.in/ | C/G |
| IN-04 | eGazette of India | https://egazette.gov.in/ | C |
| IN-05 | Ministry of Home Affairs (MHA) | https://www.mha.gov.in/ | C/B |
| IN-06 | Press Information Bureau (PIB) | https://www.pib.gov.in/ | B/D |
| IN-07 | Census of India | https://censusindia.gov.in/ | E/F/G |
| IN-08 | Ladakh Culture Department | https://ladakh.gov.in/culture-department/ | E/G |
| IN-09 | Sikkim Culture Department | https://culture.sikkim.gov.in/ | E/G |
| IN-10 | Survey of India Online Maps Portal | https://onlinemaps.surveyofindia.gov.in/ | F/G |

## 逐来源实施输入

以下直接转录 S2 §15 的站点条目，包含来源专属过滤和数据要求；具体 DOM/接口、分页终止条件和字段选择器要在接入时核验。

### CN-01  中华人民共和国外交部（MFA）

服务知识库：A / B / D / G

入口：https://www.mfa.gov.cn/

怎么检索：优先不用全站关键词盲搜，而是进入“国家和组织 → 国家（地区） → 亚洲 → 印度”，固定抓取“相关新闻、发言人有关谈话、讲话、文件、驻外报道”等子栏目；全站搜索仅用于补漏。对边界类正式资料，另进入“外交部 → 组织机构 → 边界与海洋事务司 → 边海国际条约/边海声明公报/相关新闻”。

推荐关键词（宽泛）：印度；中印；关系；边境；边界；外交；合作；会谈；会晤；声明；文件；和平；安全；贸易。具体机制名、事件名和年份仅在补漏时追加。

爬取/入库建议：首选抓固定国家页和栏目列表页，按发布日期增量；详情页提取标题、日期、来源、正文、附件和栏目。不要把首页推荐、页脚“相关链接”当正文。正式文件和新闻表述分不同 document_type。

### CN-02  外交部条约数据库

服务知识库：A / G

入口：https://treaty.mfa.gov.cn/

怎么检索：进入首页“高级搜索”。第一步：类别=双边；第二步：缔约对象/关键词优先输入“印度共和国”（比“印度”更精准）；第三步：如只查边界类，可把“领域”筛选为“边界海洋”；第四步再用条约名称片段补搜。已知条约可直接按完整名称检索。

推荐关键词（宽泛）：在“缔约对象=印度共和国、类别=双边”等结构化条件下，主要使用边界、边境、协定、协议、条约、关系、合作、机制、和平、安全、贸易。具体条约全称只用于已知文件回查；“边界海洋”仅作领域筛选。

爬取/入库建议：抓搜索结果中的 detail1.jsp 详情页及中文/英文/印地文正式文本/PDF，保存条约名称、类别、领域、签署时间、生效时间、签署地点和多语文本链接。以 objid/条约唯一标识去重，同一协定多语版本用 agreement_id 对齐。

### CN-03  国家法律法规数据库

服务知识库：C / G

入口：https://flk.npc.gov.cn/search

怎么检索：搜索页支持“标题”精确/模糊检索，并可用高级检索筛选法律法规分类、制定机关、时效性、公布/施行日期。已知法律名时先精确搜；主题发现时用模糊搜。地方规则优先筛“地方法规 → 西藏”，并把时效性优先设为“有效”。

推荐关键词（宽泛）：国界、边境、口岸、出入境、外国人、国籍、护照、国家安全、民族、宗教、地图、测绘、西藏。具体法律名称只用于精确回查。

爬取/入库建议：只抓命中主题的法律详情，不全库镜像。保存法律效力位阶、制定机关、时效性、公布日期、施行日期、网页版/公报原版下载链接；条文按“章-节-条”切片，版本变更通过相关文件和时效性字段管理。

### CN-04  中国政府网—国务院政策文件库

服务知识库：C / B

入口：https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?t=zhengcelibrary

怎么检索：使用政策文件库搜索框；优先“搜索全文”发现主题，再切换“只搜标题”确认高相关文件。可按发布机构、主题分类、日期过滤，并按相关度/时间排序。对本项目重点关注外交部、公安/移民、国家民族事务委员会、自然资源等发布机构。

推荐关键词（宽泛）：边境、口岸、出入境、外国人、跨境、贸易、民族、宗教、地图、测绘、西藏、日喀则、安全。

爬取/入库建议：优先抓国务院文件、国务院部门文件和政策解读的详情页；保存发文机关、文号、成文/发布日期、正文和附件。政策解读与规范性文件分开标记，解读不能替代法规原文。

### CN-05  西藏自治区人民政府

服务知识库：C / E / F

入口：https://www.xizang.gov.cn/

怎么检索：首页有站内搜索框“请输入您想要搜索的内容”。法律规则类同时固定抓“政府信息公开 → 政府规章库、行政规范性文件、信息公开目录”；地方背景类按“日喀则/地区 + 主题”搜索。

推荐关键词（宽泛）：边境、口岸、外事、贸易、宗教、民族、文化、行政区划、日喀则、条例、办法、规定、通知。具体县名可在区域补漏时添加。

爬取/入库建议：法规和规范性文件按栏目增量，不依赖全文搜索结果作为唯一入口；文化/地理信息只抓政府正式介绍和公开数据。对行政区划变化保存 effective_date；避免抓旅游营销转载作为高权威证据。

### CN-06  西藏自治区外事办公室

服务知识库：E / B

入口：https://wsb.xizang.gov.cn/

怎么检索：当前站点以栏目导航为主，建议固定抓“民族风情、涉外常识、要闻动态、西藏新闻、信息公开目录”等栏目；如站内搜索不可稳定调用，不依赖搜索接口，而在抓取后的标题/正文中本地过滤。

推荐关键词（宽泛）：西藏、日喀则、民族、文化、宗教、信仰、礼仪、民俗、节庆、语言、外事、边境。

爬取/入库建议：按栏目分页抓标题、日期、正文；“海外预警”等外链栏目若跳转外交部/公众号，只保存原始权威来源链接，不重复入库。文化条目作为 A2 背景证据，不作为法律/政策结论依据。

### CN-07  西藏自治区民族事务委员会

服务知识库：E / C

入口：https://mw.xizang.gov.cn/

怎么检索：固定抓“政策法规、政策解读、民族概况、重要文献、最新公开”等栏目。若站内搜索不稳定，采用栏目遍历 + 本地关键词过滤，并沿“国家民委/自治区政府”权威外链回查原文。

推荐关键词（宽泛）：民族、文化、语言、宗教、风俗、政策、法规、西藏、族群、民族事务。

爬取/入库建议：政策法规页面若转载国家层面法律，要记录原发布机关和原文 URL；同一文件不要因多站转载重复建 chunk。民族概况类按 community_id 建实体，记录适用区域。

### CN-08  新华网

服务知识库：B / D（补充）

入口：https://www.news.cn/

怎么检索：新华网作为 B 级补充源，不建议全站爬。优先用站内/搜索引擎的 site:news.cn 限域检索，或从外交部事件页面中的新华社引用反向定位报道。按“主题 + 年份”检索历史事件。

推荐关键词（宽泛）：中印、印度、关系、边境、边界、外交、会谈、合作、声明、局势、和平、安全。历史回填时再加年份或事件名称。

爬取/入库建议：只抓与 event_id 关联的报道，提取标题、发布时间、来源、正文和引用的官方文件链接。新闻稿用于时间线和背景，不作为条约/法律问题的唯一证据。

### IN-01  印度外交部 MEA（China 页面 + 高级搜索）

服务知识库：A / B / D / G

入口：https://www.mea.gov.in/china-in.htm

怎么检索：第一入口用 China 国家页，固定抓 India-China Relations、Important Documents 等。第二入口用 MEA Advanced Search，可选择 Everything、Speeches & Statements、Press Releases、Media Briefings、Parliament Q&A、Bilateral/Multilateral Documents，并按 Year/Month、Exact Match、Sort by Date 过滤。

推荐关键词（宽泛）：China; India-China; relations; border; boundary; agreement; treaty; cooperation; talks; meeting; statement; peace; security; trade. 具体机制名、缩写和年份仅用于补漏。

爬取/入库建议：China 固定页做历史种子；日常增量从 Advanced Search/Press Releases 按日期抓。保存内容类型和印度官方立场标识 IN_OFFICIAL。Parliament Q&A 单独类型化，问题与答复成对保存。

### IN-02  印度外交部 MEA—Indian Treaties Database

服务知识库：A / G

入口：https://www.mea.gov.in/treatylist-generic.htm

怎么检索：Treaty / Agreement 页面支持 Enter Keyword、Subject、Sub-Subject、Type、Country、Ministry、Year of Signature/Entry into Force 等筛选。推荐先 Country=China + Type/Bilateral（如可选），再用关键词；已知年份时加 Year of Signature。

推荐关键词（宽泛）：China; India-China; bilateral; relations; border; boundary; agreement; treaty; cooperation; talks; peace; security. 已知条约再用正式名称精确检索。

爬取/入库建议：下载/抓取 Treaty 详情及附件，保存 Country、Subject、Type、年份和正式文本。与中方同一协定用 agreement_id 对齐，不把两侧版本覆盖合并。

### IN-03  India Code

服务知识库：C / G

入口：https://www.indiacode.nic.in/?locale=en

怎么检索：首页支持 Search All，并可限定 Acts、Sections、Subordinate Legislations；进一步可选择 Rules、Regulations、Notifications、Orders、Circulars 等。结果页可按 Ministry、Department、Act Year、Short Title 等 facets 过滤。本项目优先 Ministry=Home Affairs。

推荐关键词（宽泛）：border; immigration; foreigners; visa; citizenship; passport; security; protected area; restricted area; land port; Ladakh; Sikkim. 具体法名仅用于精确回查。

爬取/入库建议：优先抓现行 Acts 及其 Sections、Rules/Notifications，保存 Enforcement Date、Ministry、Department、repeal/saving 信息。条文按 Section 切片；旧法不得与现行法混用，必须保留 status 和有效期。

### IN-04  The Gazette of India / eGazette

服务知识库：C

入口：https://egazette.gov.in/

怎么检索：进入 Search Gazette。可按 Gazette ID、Ministry、Gazette Category、Notification Date、Publish Date 等检索；Category 搜索中还可使用 Ministry、Department、Part & Section、Reference No.、Subject、Keyword、日期范围。已知 S.O./G.S.R./Notification No. 时优先按编号搜，准确率最高。

推荐关键词（宽泛）：border; immigration; foreigners; visa; citizenship; security; protected area; restricted area; land port; Ladakh; Sikkim. Ministry、日期和 Gazette 类别优先作为筛选项，而不是堆入关键词。

爬取/入库建议：网站 URL 常带会话参数，不要把 session URL 作为主键；以 Gazette ID + PDF hash 作为稳定标识。抓官方 PDF、Ministry、Subject、Issue/Publish Date、Gazette ID。遇验证码/登录不绕过，转人工或使用公开可下载入口。

### IN-05  Ministry of Home Affairs (MHA)

服务知识库：C / B

入口：https://www.mha.gov.in/

怎么检索：不依赖首页泛搜，优先固定抓 Divisions of MHA：Border Management-I Division、Foreigners Division、Foreigners II Division、Jammu & Kashmir and Ladakh Affairs；同时抓 Parliamentary Questions、Press Release、Acts/Rules/Notifications。Foreigners Division 内有 Acts, Rules and Regulations、PAP/RAP 等专门入口。

推荐关键词（宽泛）：China; border; border management; immigration; foreigners; visa; citizenship; security; land port; Ladakh; Sikkim; policy.

爬取/入库建议：按 Division 固定页和下载列表增量；PDF 保存标题、日期、文件号。只收公开政策、法律、通知和行政规则，避免将实时部署、警力位置等行动性信息作为知识库内容。

### IN-06  Press Information Bureau (PIB)

服务知识库：B / D（补充）

入口：https://www.pib.gov.in/

怎么检索：“All Releases”可按 Ministry 和日期浏览；“Archives”支持按 Year/Month、Ministry 或关键词检索，历史资料从 1947 起可追溯；“Advance Search/Research Unit”可按 Sector、日期、语言、Title Keyword 搜背景材料。

推荐关键词（宽泛）：China; India-China; border; boundary; relations; government; foreign affairs; home affairs; defence; meeting; cooperation; security.

爬取/入库建议：作为事件背景补充源。按 Ministry+日期增量抓 Press Release；历史事件用 Archives 的年份/月/关键词回填。关键结论回链 MEA/MHA/法令原文，PIB 不替代 A1 证据。

### IN-07  Census of India—Data Catalog

服务知识库：E / F / G

入口：https://censusindia.gov.in/nada/index.php/catalog/

怎么检索：在 Data Catalog 直接按数据表代码 + 地区 + 年份搜索，并用 Year、Data Type、Tags 等过滤。语言重点用 C-16 (Population by mother tongue)，宗教用 C-01 (Population by religious community)，行政/地方资料用 District Census Handbook、PCA、Administrative Atlas。

推荐关键词（宽泛）：language; mother tongue; religion; population; district; state; union territory; Ladakh; Sikkim; Arunachal Pradesh. 数据表代码和年份用于二次筛选，不作为唯一入口。

爬取/入库建议：优先下载表格/结构化文件，不把整张统计表转成一个长文本 chunk。按 geo_id + census_year + table_code 建表；保存原表名、地区层级、统计年份和数据字典。

### IN-08  Ladakh Culture Department

服务知识库：E / G

入口：https://ladakh.gov.in/culture-department/

怎么检索：以固定栏目为主：Culture Department 首页、About Us、Roles and Responsibilities、Orders、Related Documents/Archives，以及 Ladakh Academy of Art, Culture & Languages 相关公开资料。站内搜索不稳定时采用栏目遍历 + 本地关键词过滤。

推荐关键词（宽泛）：Ladakh; culture; language; religion; customs; festival; heritage; literature; community; tradition.

爬取/入库建议：抓官方文化介绍、出版/档案/语言项目、文化机构资料；活动新闻可作背景但低权重。每条文化知识标注适用区域（Leh/Kargil/全 UT）和来源时间，避免把局部习俗泛化为全地区。

### IN-09  Sikkim Culture Department

服务知识库：E / G

入口：https://culture.sikkim.gov.in/

怎么检索：优先抓官网固定板块：Bhutia Community、Lepcha Community、Ethnic Community、Archives、Song and Drama、Museum、News & Press Release、Notification & Circulars。若站内检索不可稳定使用，遍历栏目后本地过滤。

推荐关键词（宽泛）：Sikkim; culture; language; religion; customs; festival; heritage; community; tradition.

爬取/入库建议：社区介绍按 community_id 入库；活动、通知与文化常识分类型。涉及族群/语言名称时同步更新 G 库术语映射；不从旅游商业站补写未被官方材料支持的“禁忌/习俗”。

### IN-10  Survey of India Online Maps Portal

服务知识库：F / G

入口：https://onlinemaps.surveyofindia.gov.in/

怎么检索：首页“Search for Maps/Digital Products”进入 Product Search，按 Location Name 检索；Quick Access 可直接进入 Administrative Boundary Database、Political Map of India、State Maps；另有 Geographical Names 入口。先搜行政区/城市名，再筛产品类型。

推荐关键词（宽泛）：Ladakh; Sikkim; Arunachal Pradesh; Uttarakhand; Himachal Pradesh; map; boundary; district; state; geographical names; administrative. 产品类型优先用门户筛选。

爬取/入库建议：主要抓公开产品元数据、地名、版本和行政层级；公开免费下载产品按许可下载。需要登录/付费/受限的产品遵守规则，不绕过限制。中印有争议的边界/地名必须保留 source_country=IN 和 perspective=IN_OFFICIAL_CARTOGRAPHIC_SOURCE，不与中方地图几何融合。

## 来源适配器的可检查条目

每个入选来源补齐：source_id 与站内稳定主键、允许域及附件域、允许/排除路径、入口与发现策略、分页终止条件、宽泛词与补漏词/排除词、字段定位、公开附件处理、引用定位、更新规则、访问规则核验日期、失败行为、固定样本和至少 10 词测试记录。以上配置清单是本次实施展开，原文未规定全部字段名。

特别检查条约库“边界海洋”领域标签不能当普通自由词，eGazette 不用临时 session URL 作主键，Census 保留 table_code/census_year/geo_id 等统计组织依据，MEA 议会问题与答复成对保存，Survey of India 保留 IN_OFFICIAL_CARTOGRAPHIC_SOURCE 来源视角。S2 的 MHA 条目明确排除实时部署和警力位置等行动性信息，适配器应保留这个来源采集边界。

S2 §4—10 的来源表还列出人民日报/人民网、中国标准地图体系、地方官方门户、项目内部资料等补充输入，不能仅以这 18 个 ID 声称覆盖所有来源。完整来源表见 [S2 转录](sources/S2-transcript.md) B031/B046/B054/B063/B072/B079/B087；未知具体地址不自行编造，内部资料不转成网络来源。

## 七类词包

完整词包以 [S2 B122](sources/S2-transcript.md#b122) 为准；每个来源通常 8—15 个常规主词，具体专名用补漏词。领域验收仍需每来源至少 10 个测试词及预期文档，不把主词数量建议当作已验证的召回结果。当前未执行任何关键词测试。
