# S2 原文结构转录

原件：[ 七类知识库知识来源与采集方案_V1.3_宽泛检索关键词版.docx ](../../../docs/七类知识库知识来源与采集方案_V1.3_宽泛检索关键词版.docx)

此文件按 Word 主文档 XML 顺序转录段落和表格，供定位原文使用；不代替原件的排版、图像或批注。B 编号表示主文档直接子元素的序号，空段落计入编号但不显示。表格中的换行以 HTML 换行标记表示。

## B001

七类知识库知识来源与采集方案

## B002

面向嵌入式开发板部署的领域 RAG 知识资源设计

## B003

结合“166工程”课题实施方案中的 RAG、知识库与边缘部署要求

## B004

版本：V1.3日期：2026-09-07修订说明：主检索关键词调整为宽泛主题词；具体专名、年份和地点仅用于二次补漏。

## B006

1. 建设目标与设计边界

## B007

本方案把项目所需公开知识组织为七类知识库，并对每类知识的内容范围、优先采集来源、建议抓取入口、采集方式、更新频率和入库组织方式进行明确。目标不是“爬完整个互联网”，而是建立一个以官方权威材料为主、可追溯、可版本化、可在边缘设备上裁剪部署的领域知识体系。

## B008

项目实施方案对 RAG 数据源的基本要求包括：权威公开资料、法律法规和条约协议资料、历史案例与任务资料；同时强调来源、版本、生效时间、权限、引用位置等元数据管理，并提出结构化索引、全文索引、向量索引、知识图谱和混合检索的组合方式。

## B009

只把“可公开合法获取”的网页、PDF、表格和公开数据纳入网络爬取；内部任务材料另走受控导入流程。

## B010

优先使用政府、立法机构、外交部门、官方统计和官方地图；官方媒体作为事件背景补充，不与法律/条约同权。

## B011

争议性议题必须保存“来源国家/机构”和“立场属性”，不得在入库阶段自动合并为单一事实。

## B012

采集时遵守站点 robots.txt、使用条款、下载限制和访问控制；对需要登录、验证码或受限地图产品不绕过限制。

## B013

2. 七类知识库总览

## B014

| 知识库 | 主要内容 | 核心采集源 | 证据等级 |
| --- | --- | --- | --- |
| A. 中印双边协定与机制库 | 条约、协定、议定书、联合声明、WMCC、特别代表机制、会晤成果 | 外交部条约数据库/中印关系页；印度外交部 China 页面/双边文件/条约库 | A1 |
| B. 双方政策立场与公开表述库 | 领导人/外交部门公开表态、记者会、问答、联合公报、议会答复 | 中国外交部；印度 MEA；PIB；新华社/人民日报（补充） | A1/A2 |
| C. 法律法规与行政规则库 | 中国法律法规、地方边境/宗教/外事规则；印度法律、通知、边境管理政策 | 国家法律法规数据库、gov.cn、西藏政府；India Code、eGazette、MHA | A1 |
| D. 历史事件与交涉案例库 | 事件时间线、双方表述、依据引用、处置过程、后续影响、相似案例 | MFA/MEA 历史资料、PIB、新华社、议会问答、项目内部案例材料 | A1/A2+内部 |
| E. 文化、宗教与语言知识库 | 民族、宗教、节庆、礼仪、禁忌、地区文化、语言分布 | 西藏外办/民委；Ladakh、Sikkim 等地方政府；Census of India | A2 |
| F. 地理、地名与区域背景库 | 标准地名、别名、行政区、经纬度、地图来源、区域背景 | 中国标准地图/官方行政区资料；Survey of India；Census/地方政府 | A2 |
| G. 中英印多语术语与规范表达库 | 机构名、条约名、法律术语、地名、人名、外交固定表达、术语映射 | 三语正式条约文本；MFA 中英文；MEA 英文/印地语；官方地图/统计 | A1/A2 |

## B016

重要检索口径修正：“边界海洋”是外交部条约数据库的官方“领域”分类标签，1993、1996、2005、2012 等中印陆地边界相关协定都被标为“边界海洋”。因此：高级筛选时可以选择“领域=边界海洋”；但自由文本检索不要把“海洋”作为关键词。自由文本应使用“印度共和国”“中印边境”“实际控制线”“信任措施”“政治指导原则”“边境事务磋商和协调工作机制”等。单独加入“海洋”会引入海运、海关、海洋法等无关结果。

## B017

3. 统一来源分级与入库规则

## B018

| 等级 | 来源类型 | 使用规则 |
| --- | --- | --- |
| A1 | 正式条约/协定、现行法律法规、外交部门正式文件、政府公报 | 可直接作为核心证据；回答关键结论时优先引用 |
| A2 | 政府部门介绍、官方统计、官方地图、地方政府公开资料 | 可作为事实和背景证据；涉及争议边界/立场时必须保留来源视角 |
| B | 新华社、人民日报、PIB 等官方媒体/政府新闻发布汇编 | 用于事件背景、时间线和舆情线索；关键法理结论应回查 A1 原文 |
| C | 百科、商业媒体、论坛、学术二手材料 | 仅用于发现线索或扩充关键词；默认不进入最终证据链 |

## B020

每个文档/知识片段建议至少保留：

## B021

doc_id、chunk_id、title、text、source_name、source_url、source_country、source_authority。

## B022

document_type、topic、publication_date、event_date、effective_from/effective_to、version、is_current。

## B023

language、jurisdiction、stance（CN_OFFICIAL / IN_OFFICIAL / BILATERAL / NEUTRAL）。

## B024

citation_anchor（页码/条款/段落）、content_hash、supersedes/superseded_by、抓取时间。

## B025

V1.3 使用说明：下面每个来源的“采集建议”优先给出宽泛主题关键词。爬虫首轮用这些词做高召回发现，再通过栏目、来源、标题/正文相关度和本地分类规则做二次过滤。具体条约全称、机制名称、事件名称、年份和地点只用于已知资料补漏，不建议放进常规 seed_terms。

## B026

4. A库：中印双边协定与机制库

## B027

定位：本项目最高优先级证据库，回答“依据哪个协定、机制如何规定、双方达成过什么正式共识”等问题。

## B028

双边边界协定、军事领域信任措施、实施议定书、边境事务磋商协调机制（WMCC）文件。

## B029

特别代表会晤、联合声明/联合公报、正式会晤成果、双方共同发布文件。

## B030

同一文件的中文、英文、印地文版本及解释优先级条款。

## B031

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 中国外交部条约数据库 | 双边条约正式文本、多语种版本、签署/生效信息 | treaty.mfa.gov.cn | 检索方式：高级搜索：类别=双边；缔约对象优先“印度共和国”；只查边界类时领域选“边界海洋”（仅分类标签）。主检索词（宽泛）：边界；边境；协议；协定；条约；关系；合作；机制；和平；安全；贸易组合示例：“印度共和国 + 边境”“印度共和国 + 协定”“印度共和国 + 合作”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：搜索结果详情页、正式文本/PDF、签署/生效信息、多语版本；不要把“海洋”当自由文本词。 |
| 中国外交部—中国同印度的关系 | 双边关系概况、重要交往、相关文件 | mfa.gov.cn 中印关系栏目 | 检索方式：固定进入“国家和组织→亚洲→印度”，抓“相关新闻/文件/讲话/发言人有关谈话”等子栏目；站内搜索用于补漏。主检索词（宽泛）：印度；中印；关系；边界；边境；外交；合作；会谈；会晤；访问；声明；文件；和平；安全；贸易组合示例：“中印 + 边境”“印度 + 会谈”“中印 + 合作”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：栏目列表页增量抓取，详情页保存标题、日期、正文、附件、栏目；使用“印度”时排除“印度尼西亚/印尼”。 |
| 中国外交部条约/文件页面 | 1993、1996、2005、2012 等协定/议定书正文 | mfa.gov.cn | 检索方式：对已知正式文件优先使用外交部站内搜索或 site:mfa.gov.cn 限域检索；按正式名称/独特短语建立白名单。主检索词（宽泛）：印度；中印；边界；边境；协定；协议；条约；文件；声明；合作；会谈；机制；和平；安全组合示例：site:mfa.gov.cn “中印 + 协定”；site:mfa.gov.cn “印度 + 边境”；site:mfa.gov.cn “中印 + 声明”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：只抓外交部正式文件正文/附件，条约按条款切片，联合声明按段落/议题切片。 |
| 印度外交部 MEA—China | India-China Relations、Important Documents、访问和联合文件 | mea.gov.in/china-in.htm | 检索方式：先用 MEA China 国家页的 India-China Relations / Important Documents；再用 MEA Advanced Search 按内容类型和年份补漏。主检索词（宽泛）：China；India-China；relations；border；boundary；agreement；treaty；cooperation；talks；meeting；statement；peace；security；trade组合示例：“India-China + border”“China + agreement”“India-China + talks”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：China 页面、Press Release、Statement、Bilateral Document、PDF；LAC 不单独检索，必须与 China/India-China 组合。 |
| 印度外交部 MEA 站点分类 | Bilateral/Multilateral Documents、Indian Treaties Database、Press Releases | mea.gov.in/sitemap.htm | 检索方式：在 sitemap/Advanced Search 中分别限定 Bilateral/Multilateral Documents、Treaties、Press Releases、Media Briefings、Parliament Q&A。主检索词（宽泛）：China；India-China；bilateral；relations；border；boundary；agreement；treaty；documents；talks；meeting；cooperation；statement组合示例：“China + bilateral”“India-China + agreement”“China + talks”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：按内容类型分别入库，条约/双边文件为 A1，新闻稿/议会答复单独标注 document_type 与 IN_OFFICIAL。 |

## B033

首批必采文档建议：

## B034

1993 年中印边境实际控制线地区保持和平与安宁协定

## B035

1996 年中印边境实际控制线地区军事领域建立信任措施协定

## B036

2005 年相关实施议定书及边界问题政治指导原则文件

## B037

2012 年建立中印边境事务磋商和协调工作机制（WMCC）协定

## B038

后续双方正式联合声明、特别代表会晤和 WMCC 成果文件

## B039

组织方式：法律/条约按“文件—章/条—款/项”切片，保留签署日期、生效日期、正式语言、条款号、双方名称和引用锚点；同一协定多语种版本通过 agreement_id 对齐。

## B040

5. B库：双方政策立场与公开表述库

## B041

定位：回答“当前双方如何公开表述某议题、近期会晤释放了什么信息、某次事件后官方口径如何变化”等时效性问题。

## B042

外交部发言人答记者问、例行记者会、官方声明、部长/领导人讲话。

## B043

中印双边会见、WMCC/特别代表会晤新闻稿、联合新闻公报。

## B044

印度议会问答（Lok Sabha / Rajya Sabha）中涉及中国、边境、协定执行的问题。

## B045

官方新闻发布平台用于补充政策发布和事件时间线。

## B046

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 中国外交部 | 发言人答问、部长活动、双边会晤、正式声明 | mfa.gov.cn | 检索方式：固定抓“印度”国家页与发言人/部长活动等栏目，站内搜索按日期补漏。主检索词（宽泛）：印度；中印；关系；边境；边界；外交；会见；会谈；声明；回应；合作；和平；安全；局势组合示例：“中印 + 边境”“印度 + 会谈”“中印 + 声明”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：每日增量；区分正式声明、答记者问、会见消息和背景介绍。 |
| 印度外交部 MEA | Press Releases、Media Briefings、Speeches & Statements、Parliament Q&A | mea.gov.in | 检索方式：Advanced Search 中限定 Press Releases / Media Briefings / Speeches & Statements / Parliament Q&A，并按 Year/Month 过滤。主检索词（宽泛）：China；India-China；relations；border；boundary；talks；meeting；statement；response；cooperation；peace；security；situation组合示例：“India-China + border”“China + talks”“India-China + statement”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：每日增量；保存发布时间、内容类型、发布主体、原始链接和 IN_OFFICIAL 标签。 |
| 印度 PIB | 政府各部门 Press Releases、PMO、政策背景资料 | pib.gov.in | 检索方式：按 Ministry/Department + 日期检索，优先 External Affairs、Home Affairs、Defence、PMO；站内关键词用于跨部门补漏。主检索词（宽泛）：China；India-China；border；relations；government；foreign affairs；home affairs；defence；meeting；cooperation；security组合示例：“China + border”“India-China + government”“China + cooperation”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：只作为 MEA/MHA/PMO 的补充发布源；可回链原部门文件时优先保存原始部门页面。 |
| 新华社 | 中方官方媒体背景、时间线、会晤报道 | news.cn | 检索方式：不做全站镜像；用站内搜索或 site:news.cn 限域，以“主题+年份/事件”回填。主检索词（宽泛）：中印；印度；关系；边境；边界；外交；会谈；合作；声明；局势；和平；安全组合示例：site:news.cn “中印 + 边境”；site:news.cn “印度 + 会谈”；site:news.cn “中印 + 关系”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：只抓与 event_id 或政策表述相关的报道；用于背景/时间线，关键结论回查政府原文。 |
| 人民日报/人民网 | 政策背景、重要讲话报道、评论材料 | people.com.cn | 检索方式：人民网/人民日报站内或 site:people.com.cn 限域检索，优先“中印+事件/机制+年份”。主检索词（宽泛）：中印；印度；关系；边境；边界；外交；会谈；合作；声明；局势；和平；安全组合示例：site:people.com.cn “中印 + 关系”；site:people.com.cn “印度 + 边境”；site:people.com.cn “中印 + 会谈”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：政策背景、领导人讲话报道和事件时间线；评论/社论必须与政府正式表述分字段存储。 |

## B048

关键字段： stance、speaker、organization、event_date、publication_date、issue_tags、related_agreement_ids。对于双方表述不一致的内容分别入库，不做自动“事实合并”。

## B049

6. C库：法律法规与行政规则库

## B050

定位：支撑法理查询、规则解释和合规判断。该库必须以“现行有效性”和“版本沿革”为核心。

## B051

中国：国家法律、行政法规、外交/国界/出入境相关规则、西藏自治区地方性法规与规章。

## B052

印度：Central Acts、Sections、Rules、Regulations、Notifications、Orders、Border Management 政策。

## B053

每条法规记录公布日期、施行日期、时效性、修改/废止关系、条款号。

## B054

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 国家法律法规数据库 | 法律、行政法规、地方法规、司法解释及时效性 | flk.npc.gov.cn | 检索方式：已知法律名用“标题”精确/模糊搜索；主题发现用全文/高级检索，并按法律类型、制定机关、时效性=有效、公布/施行日期筛选。主检索词（宽泛）：国界；边境；口岸；出入境；外国人；国籍；护照；国家安全；民族；宗教；地图；测绘；西藏组合示例：“边境 + 有效”“口岸 + 出入境”“西藏 + 宗教”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：命中主题的现行法律/行政法规/地方法规，保存时效性和原版附件，按章-节-条切片。 |
| 中国政府网政策/行政法规 | 国务院政策、行政法规及政策文件 | gov.cn/zhengce | 检索方式：政策文件库先“搜索全文”发现主题，再“只搜标题”确认；按发布机构、主题、日期过滤。主检索词（宽泛）：边境；口岸；出入境；外国人；跨境；贸易；民族；宗教；地图；测绘；西藏；日喀则；安全组合示例：“边境 + 管理”“西藏 + 口岸”“民族 + 宗教”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：国务院/部门正式文件及必要政策解读；规范性文件与解读分开入库，解读不能替代法规原文。 |
| 西藏自治区人民政府 | 地方性法规、政府规章、政策文件 | xizang.gov.cn | 检索方式：首页站内搜索 + 固定抓“政府规章库/行政规范性文件/信息公开目录”；地方内容用“地区+主题”。主检索词（宽泛）：边境；口岸；外事；贸易；宗教；民族；行政区划；日喀则；条例；办法；规定；通知组合示例：“日喀则 + 边境”“西藏 + 宗教”“口岸 + 通知”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：地方性法规、规章、规范性文件和官方区划资料；保存生效/废止日期。 |
| India Code | Acts、Sections、Rules、Regulations、Notifications、Orders | indiacode.nic.in | 检索方式：Search All，可限定 Acts / Sections / Subordinate Legislations；结果页按 Ministry=Home Affairs、Act Year、Short Title 等 facets 过滤。主检索词（宽泛）：border；immigration；foreigners；visa；citizenship；passport；security；protected area；restricted area；land port；Ladakh；Sikkim组合示例：“border + immigration”“foreigners + visa”“Ladakh + border”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：现行 Acts、Sections、Rules、Notifications、Orders；强制保存 Enforcement Date、repeal/supersede 关系。 |
| eGazette of India | Gazette Notifications、法令/规则/通知原文 | egazette.gov.in | 检索方式：Search Gazette；优先用 Gazette ID/Notification No./S.O./G.S.R. 精确检索，否则按 Ministry、Subject/Keyword、日期范围筛选。主检索词（宽泛）：border；immigration；foreigners；visa；citizenship；security；protected area；restricted area；land port；Ladakh；Sikkim组合示例：“border + notification”“immigration + rules”“Ladakh + notification”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：官方 Gazette PDF 与元数据；以 Gazette ID+PDF hash 去重，不绕过验证码/访问限制。 |
| Ministry of Home Affairs | Border Management I/II、Acts/Rules/Notifications/Policy Guidelines | mha.gov.in | 检索方式：固定抓 Border Management I/II、Acts/Rules/Notifications/Policy Guidelines，再用站内搜索补漏。主检索词（宽泛）：border；border management；China；immigration；foreigners；visa；citizenship；security；land port；Ladakh；Sikkim；policy组合示例：“China + border”“border management + policy”“Ladakh + policy”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：政策指南、通知、边境管理和通行规则的公开文件；保存部门、日期、附件和原始 PDF。 |

## B056

建议关键词集合：陆地国界、边境、口岸、出入境、外国人、国籍、国家安全、外事、民族、宗教、地图/测绘；India 侧对应 border、immigration、foreigners、citizenship、protected/restricted area、land port、security、Ladakh 等。

## B057

7. D库：历史事件与交涉案例库

## B058

定位：不是简单的新闻全文库，而是“事件实体库 + 证据文档库”，用于相似案例检索、事件时间线、处置依据和策略复盘。

## B059

事件基本事实：时间、地点、参与主体、议题、触发因素、后续节点。

## B060

中方公开表述、印方公开表述、双方共同文件分别挂接到同一 event_id。

## B061

与事件相关的协议条款、法律依据、历史先例、后续会晤和机制性处理。

## B062

项目内部历史交涉案例、复盘材料、会议纪要、现场转写等通过离线受控导入，不纳入互联网爬虫。

## B063

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 中国外交部历史页面 | 事件声明、会晤、边境工作机制、答记者问 | mfa.gov.cn | 检索方式：外交部站内/国家页按“事件名或年份+机制+地点”回溯，并固定抓相关新闻、发言人答问、特别代表/WMCC 会晤。主检索词（宽泛）：中印；印度；边境；边界；事件；局势；会谈；磋商；声明；合作；处置；和平；安全组合示例：“中印 + 边境”“印度 + 事件”“中印 + 会谈”；需要历史回填时再加年份补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：每个事件绑定 event_id，优先官方声明、会晤成果和机制文件。 |
| 印度 MEA 历史页面 | Press Releases、Media Briefings、Parliament Q&A、双边文件 | mea.gov.in | 检索方式：MEA Advanced Search 按 Year/Month + Press Release/Media Briefing/Parliament Q&A 回溯；用地点/机制/阶段词组合。主检索词（宽泛）：China；India-China；border；boundary；incident；situation；talks；meeting；statement；consultation；cooperation；peace；security组合示例：“India-China + border”“China + incident”“India-China + talks”；回填时再加年份补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：保留 IN_OFFICIAL；同一事件的声明、议会答复、会晤消息挂到同一 event_id。 |
| PIB | 印度政府部门事件信息和政策说明 | pib.gov.in | 检索方式：PIB 按 Ministry + 时间 + 事件词检索，优先 MEA/MHA/Defence/PMO。主检索词（宽泛）：China；India-China；border；incident；situation；government；defence；meeting；statement；cooperation；security组合示例：“China + border”“India-China + incident”“China + meeting”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：用于补充事件时间线；有 MEA/MHA 原始页面时建立 cross_source_link。 |
| 新华社/人民网 | 公开事件时间线和背景报道 | news.cn / people.com.cn | 检索方式：按“事件/机制/地点+年份”限域检索。主检索词（宽泛）：中印；印度；边境；边界；事件；局势；会谈；声明；合作；和平；安全组合示例：site:news.cn “中印 + 边境”；site:people.com.cn “印度 + 事件”；历史回填再加年份补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：B级背景/时间线，不作为争议事实唯一证据；与官方源交叉关联。 |
| 项目内部资料 | 历史交涉记录、复盘、执勤日志、会议纪要、模拟谈判 | 内部受控导入 | 内部检索标签：年份；任务编号；地点；人员/角色；议题；事件类型；处置方式；结果；风险等级；相关协议；复盘结论。主检索词（宽泛）：边境交涉；谈判；沟通；翻译；文化；法理；案例；策略；风险；处置；结果组合示例：“任务编号 + 议题”“地点 + 事件”“案例 + 风险”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：仅受控离线导入；分类分级、脱敏、权限标签和审计，不经公共爬虫。 |

## B065

推荐事件结构：

## B066

event_id / event_date / location / actors / topic / cn_official_statement_ids / in_official_statement_ids / bilateral_statement_ids / agreements_referenced / followup_event_ids / source_ids / confidence

## B067

8. E库：文化、宗教与语言知识库

## B068

定位：服务跨文化理解、语言语义解释、礼仪与禁忌提示。必须区域化，不把“印度文化”或“西藏文化”做成单一泛化标签。

## B069

民族/族群、语言、宗教与信仰、节庆、礼仪、风俗、禁忌、称谓和文化负载词。

## B070

按区域组织：西藏/日喀则；Ladakh、Sikkim，以及后续视场景扩展的其他边境州。

## B071

人口、语言和宗教分布尽量采用官方统计表而非描述性网页。

## B072

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 西藏自治区外事办公室 | 民族风情、涉外常识、地方文化背景 | wsb.xizang.gov.cn | 检索方式：固定抓“民族风情/西藏今昔/涉外常识/要闻动态”等栏目；站内搜索不稳定时用栏目遍历+本地关键词过滤。主检索词（宽泛）：西藏；日喀则；民族；文化；宗教；信仰；礼仪；民俗；节庆；语言；外事；边境组合示例：“日喀则 + 文化”“西藏 + 民俗”“边境 + 外事”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：官方文化背景与涉外常识；外链内容回到原始权威源，不重复收录。 |
| 西藏自治区民族事务委员会 | 民族宗教政策、民族文化、政策法规 | mw.xizang.gov.cn | 检索方式：固定抓“政策法规/政策解读/民族概况/重要文献”等栏目，采用栏目遍历+本地过滤。主检索词（宽泛）：民族；文化；语言；宗教；风俗；政策；法规；西藏；族群；民族事务组合示例：“民族 + 文化”“西藏 + 语言”“宗教 + 政策”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：政策法规、权威民族概况；转载国家文件时保留原发布机关和原文 URL。 |
| 西藏自治区人民政府/日喀则官方门户 | 地方概况、文化、节庆、非遗、行政区信息 | xizang.gov.cn | 检索方式：西藏/日喀则政府门户按“地区+文化主题”站内检索；优先政府概况、文旅/民宗/地方志类官方页面。主检索词（宽泛）：西藏；日喀则；文化；民俗；节庆；宗教；语言；非遗；地方；民族组合示例：“日喀则 + 文化”“西藏 + 节庆”“日喀则 + 非遗”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：官方地域化背景资料；避免旅游营销和商业转载作为权威证据。 |
| Ladakh Culture Department | Ladakh 语言、文学、民俗、艺术、文化保护资料 | ladakh.gov.in/culture-department | 检索方式：Culture Department 栏目遍历 + 站内/限域搜索，按地域和文化主题组合。主检索词（宽泛）：Ladakh；culture；language；religion；customs；festival；heritage；literature；community；tradition组合示例：“Ladakh + culture”“Ladakh + language”“Ladakh + festival”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：文化部门官方介绍、语言/出版资料、节庆和文化机构信息；按 region_id/community_id 入库。 |
| Sikkim Culture Department | Bhutia、Lepcha 等社区文化、语言与传统 | culture.sikkim.gov.in | 检索方式：Culture Department/Archives/Language 等栏目按社区名与主题检索。主检索词（宽泛）：Sikkim；culture；language；religion；customs；festival；heritage；community；tradition组合示例：“Sikkim + culture”“Sikkim + language”“Sikkim + festival”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：社区文化、语言、档案和节庆资料；记录适用社区和地区，避免泛化到整个印度。 |
| Census of India | Language & Mother Tongue、Religion 等统计表 | censusindia.gov.in | 检索方式：优先按数据表代码/主题检索并下载结构化表；再按 State/UT/District/Sub-district 过滤。主检索词（宽泛）：language；mother tongue；religion；population；district；state；union territory；Ladakh；Sikkim；Arunachal Pradesh组合示例：“language + Ladakh”“religion + Sikkim”“population + district”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：CSV/XLSX/官方表格优先，不转成大段文本；保存表代码、年份、统计层级和地区代码。 |

## B074

组织建议：以“region_id + community_id + topic”组织；对文化解释记录 source_region、source_authority 和适用范围，避免将局部习俗泛化到整个国家/地区。

## B075

9. F库：地理、地名与区域背景库

## B076

定位：支撑地点识别、别名归一、行政区域背景和地图引用。边界与地名存在敏感/争议时，必须保存“地图/地名来源视角”。

## B077

标准地名、别名/历史名称、行政区层级、经纬度、海拔/区域属性（如有）、来源地图版本。

## B078

中国与印度官方地图、行政区和统计地名分别存储；不在数据预处理阶段对争议边界做几何融合。

## B079

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 中国自然资源部门标准地图体系 | 中国侧官方标准地图、行政区划和地名依据 | 自然资源部官网/标准地图服务系统 | 检索方式：在自然资源部/标准地图服务系统按地区名、行政区名称和地图类型查找，不用泛互联网地图替代。主检索词（宽泛）：西藏；日喀则；行政区划；地名；地图；标准地图；区域；县；市；乡；镇组合示例：“日喀则 + 地图”“西藏 + 行政区划”“日喀则 + 地名”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：公开可下载地图/元数据，保存版本、审图/来源、发布日期和适用范围；争议区域不与印方地图自动融合。 |
| 国家/地方行政区资料 | 西藏、日喀则等行政区名称和区划变化 | xizang.gov.cn | 检索方式：政府门户站内搜索“行政区划/地名/概况/区划代码”，并按具体县市检索。主检索词（宽泛）：西藏；日喀则；行政区划；地名；区划；县；乡；镇；调整；概况组合示例：“日喀则 + 行政区划”“西藏 + 地名”“行政区划 + 调整”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：官方区划和概况资料，记录 effective_date、旧称/新称及上级行政区。 |
| Survey of India Online Maps Portal | Open Series Map、Political Map、Administrative Boundary Database 等 | onlinemaps.surveyofindia.gov.in | 检索方式：Online Maps Portal 按 Location Name / Product Type 搜索；产品类型优先 Open Series Map、Political Map、State Map、Administrative Boundary Database。主检索词（宽泛）：Ladakh；Sikkim；Arunachal Pradesh；Uttarakhand；Himachal Pradesh；map；boundary；district；state；geographical names；administrative组合示例：“Ladakh + map”“Sikkim + boundary”“Arunachal Pradesh + district”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：只采公开产品/元数据，保留 Survey of India 官方视角；受限/登录产品遵守访问规则。 |
| Census of India | State/UT/District/Sub-district/Town 标准统计地名 | censusindia.gov.in | 检索方式：按 State/UT/District/Sub-district/Town/Village 和数据产品检索。主检索词（宽泛）：district；sub-district；village；town；directory；census；Ladakh；Sikkim；Arunachal Pradesh组合示例：“district + Ladakh”“village + Sikkim”“census + Arunachal Pradesh”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：用于行政区/统计地名标准化，保存 census year、region code 和层级。 |
| 印度地方政府门户 | Ladakh、Sikkim 等地方行政区、地点背景 | 各州/UT 官方门户 | 检索方式：按实际任务区的地方政府门户，用“地区名+administration/district/village/map/geography”检索。主检索词（宽泛）：Ladakh；Sikkim；Arunachal Pradesh；district；administration；village；geography；map；local government组合示例：“Ladakh + district”“Sikkim + administration”“Arunachal Pradesh + map”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：地方行政区、地点背景和地名变体；作为 A2 背景，须保留来源视角和更新时间。 |

## B081

推荐实体字段： geo_id、canonical_name、aliases、language、lat/lon、admin_level、parent_geo_id、source、source_country、map_version、perspective、valid_from/valid_to。

## B082

10. G库：中英印多语术语与规范表达库

## B083

定位：支撑中文—英文—印地语三语检索、翻译一致性、专名实体归一和跨语言 RAG。它应当是“术语实体库”，而不是普通词典。

## B084

条约/协定名称、机构名称、职务名称、法律术语、外交固定表达。

## B085

地名、人名、族群/宗教名称、历史事件名称、专有缩略语。

## B086

中文/英文/印地语正式写法、别名、音译、旧称、推荐译法和来源。

## B087

| 来源 | 重点内容 | 入口 | 采集建议 |
| --- | --- | --- | --- |
| 中国外交部条约数据库 | 中文/英文/印地文正式协议文本对齐 | treaty.mfa.gov.cn | 检索方式：先按“印度共和国+协定/条约名称”定位同一协议，再抓中文/英文/印地文版本；用 agreement_id 对齐条款。主检索词（宽泛）：印度；中印；边境；边界；协定；条约；关系；合作；China；India-China；agreement；treaty组合示例：“印度共和国 + 协定”“中印 + 条约”“India-China + agreement”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：只采用正式多语文本生成术语对，保存来源条款、语言、版本和正式名称。 |
| 中国外交部中英文页面 | 机构名、外交固定表达、人物职务、事件名称 | mfa.gov.cn | 检索方式：寻找同一外交部公告的中文页和英文页，按标题、发布日期、事件实体对齐。主检索词（宽泛）：中印；印度；关系；外交；机构；职务；会谈；声明；条约；协定；China；India-China；relations；meeting；statement组合示例：“中印 + 声明”与“India-China + statement”按日期匹配补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：抽取机构名、职务、机制、条约名、固定外交表达和专名实体双语映射。 |
| 印度 MEA 英文/印地语内容 | 官方机构名称、外交术语、条约名称、专名 | mea.gov.in | 检索方式：MEA 英文/印地语版本按同一页面/文件 ID 和日期对齐，优先正式 bilateral document、press release、treaty。主检索词（宽泛）：China；India-China；relations；border；boundary；agreement；treaty；ministry；minister；meeting；statement组合示例：“China + agreement”“India-China + meeting”“China + statement”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：建立 en-hi、en-zh 间接对齐；保留原文字符串和 source_url，不用开放词典替换官方译名。 |
| 官方地图/统计资料 | 标准地名、行政区名、语言名、族群名 | Survey of India / Census of India | 检索方式：地图用地名/行政区名搜索，Census 用 State/UT/District + language/mother tongue 检索。主检索词（宽泛）：地名；行政区；语言；人口；地区；map；geographical names；language；district；population；Ladakh；Sikkim组合示例：“Ladakh + map”“Sikkim + language”“district + population”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：抽取标准地名、行政区名、语言名、族群名，与 F/E 库实体 ID 关联。 |
| 法律法规正式文本 | 法条术语、机构名称、法律概念 | flk.npc.gov.cn / indiacode.nic.in | 检索方式：按正式法律名或核心法律概念搜索中国法律法规数据库和 India Code；同一概念建立 jurisdiction 分栏。主检索词（宽泛）：国界；出入境；外国人；国籍；护照；口岸；宗教；border；immigration；foreigners；citizenship；passport；land port；religion组合示例：“出入境 + 外国人”“border + immigration”“citizenship + law”补漏规则：仅在已知具体协议、机制、事件、年份或地点时再用专名补搜，不作为常规主关键词。采集范围：仅采用现行正式法律文本术语，记录法名、条/Section、司法辖区、有效期和来源。 |

## B089

术语记录建议：

## B090

concept_id / zh / en / hi / aliases / entity_type / preferred_translation / source_ids / jurisdiction / valid_from / notes

## B091

11. 爬虫与采集工程建议

## B092

建议采用“站点注册表 + 站点适配器”模式，而不是一个万能爬虫。

## B093

| 采集器类型 | 适用来源 | 主要处理 |
| --- | --- | --- |
| HTML Spider | MFA、MEA、PIB、地方政府网页 | 栏目分页、正文抽取、发布时间/机构/附件链接、增量去重 |
| PDF Fetcher | 条约、法律公报、官方报告 | 文件下载、文本解析、页码保留、哈希去重、版本比对 |
| Table/Data Loader | Census、法规检索结果、可下载表格 | CSV/XLSX/JSON 结构化入库，避免转成大段文本 |
| Map Metadata Loader | 官方地图门户 | 抓公开产品元数据、名称、版本、覆盖范围；受限产品不绕过控制 |
| Controlled Import | 内部案例/纪要/转写 | 脱敏、权限、密级/敏感级、离线导入和审计 |

## B095

建议的 source_registry 字段：

## B096

source_id / source_name / base_domain / country / authority_level

## B097

categories / allowed_paths / blocked_paths / crawl_mode / update_interval

## B098

parser_type / language / stance_default / robots_policy / terms_checked_at

## B099

last_success_at / last_content_hash / error_count / owner

## B100

12. 各库更新频率与首批建设顺序

## B101

| 知识库 | 建议更新频率 | 首批建设优先级 | 说明 |
| --- | --- | --- | --- |
| A 双边协定与机制 | 每周检查；重大文件即时 | P0 | 体量小、权威性最高，先做完整 |
| B 政策立场与表述 | 每日 1 次 | P0 | 时效性最强，需增量抓取 |
| C 法律法规 | 每周 1 次 + 新法触发 | P0 | 重点做版本/时效性 |
| D 历史事件案例 | 每日增量 + 首次历史回填 | P1 | 先建近年事件，再逐步回溯 |
| E 文化宗教语言 | 每月/季度 | P1 | 更新慢，以权威性和区域化为主 |
| F 地理地名 | 季度 + 区划变化触发 | P1 | 地图/行政区版本管理很重要 |
| G 多语术语 | 随 A/B/C/F 增量同步 | P0 | 作为跨语言检索基础，应早期建立 |

## B103

推荐首轮上线范围：

## B104

先完成 A+C+G：形成“条约/法律/术语”高可信知识底座。

## B105

同时上线 B 的每日增量抓取：形成当前政策口径库。

## B106

随后建设 D：把官方材料按 event_id 组织成历史事件链。

## B107

E+F 作为跨文化和地理增强，按任务区域逐步扩展。

## B108

附录：建议首批接入的公开站点清单

## B109

| ID | 站点 | URL | 主要服务库 |
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

## B111

核验说明：上述站点均按当前公开入口整理。具体栏目路径、反爬策略、下载权限可能随网站改版变化，开发时应由 source_registry 统一维护，并对每个站点单独记录 robots/使用条款核验结果。

## B112

13. 检索关键词设计与歧义消除规则

## B113

本节用于统一“人工检索”和“爬虫检索”的关键词口径。总体原则是“宽泛主题词做首轮召回，具体专名做二次补漏”，并结合固定栏目、结构化筛选和本地内容分类降低误召回。

## B114

主 seed_terms 应以国家/地区、边境边界、外交关系、法律规则、文化语言、地理行政等宽泛主题词为主；每个来源通常控制在 8-15 个核心词，不把长文件名或完整机制名作为常规主词。

## B115

外交部条约数据库中的“边界海洋”只作为官方领域筛选条件，不作为自由文本关键词；自由文本以“边界、边境、协定、条约、合作、关系”等宽泛词为主。

## B116

英文站点首轮覆盖 China / India-China / border / boundary / relations / agreement / talks / cooperation 等通用词；具体缩写、机制名和专名放到补漏词典中。

## B117

建议采用两阶段检索：第一阶段用宽泛词发现候选 URL；第二阶段根据标题、正文、栏目、日期、实体和来源等级判断是否入库。

## B118

组合检索尽量简单，通常只组合“国家/地区 + 主题”或“主题 + 文档类型”两个维度；年份、地点、具体机制名只在历史回填或定位已知材料时追加。

## B119

固定栏目和结构化筛选优先于关键词。例如条约库先按“国家=印度/类别=双边”筛选，法规库先按有效性/部门/类型筛选，再配合宽泛主题词检索。

## B120

爬虫召回后做二次过滤：标题和正文主题相关度优先；只在导航、页脚或推荐链接出现关键词的页面不入库；误召回较高的泛词再配置排除词。

## B121

14. 七类知识库的检索词包（Seed Keywords）

## B122

| 知识库 | 推荐检索词包 |
| --- | --- |
| A 双边协定与机制库 | 中：印度、中印、关系、边境、边界、协定、协议、条约、机制、会谈、合作、和平、安全、贸易。英：China; India-China; relations; border; boundary; agreement; treaty; talks; meeting; cooperation; peace; security; trade. |
| B 政策立场与公开表述库 | 中：印度、中印、关系、边境、边界、外交、会见、会谈、声明、回应、合作、局势、和平、安全。英：China; India-China; relations; border; boundary; diplomacy; talks; meeting; statement; response; cooperation; situation; peace; security. |
| C 法律法规与行政规则库 | 中：国界、边境、口岸、出入境、外国人、国籍、护照、国家安全、民族、宗教、地图、测绘、西藏。英：border; immigration; foreigners; visa; citizenship; passport; security; protected area; restricted area; land port; religion; Ladakh; Sikkim. |
| D 历史事件与交涉案例库 | 中：中印、印度、边境、边界、事件、局势、会谈、磋商、声明、处置、合作、和平、安全。英：China; India-China; border; boundary; incident; situation; talks; meeting; consultation; statement; response; cooperation; peace; security. |
| E 文化、宗教与语言库 | 中：西藏、日喀则、民族、文化、宗教、信仰、礼仪、民俗、节庆、语言、风俗、边境。英：Ladakh; Sikkim; culture; language; religion; customs; festival; heritage; community; tradition; population. |
| F 地理、地名与区域背景库 | 中：西藏、日喀则、行政区划、地名、地图、区域、县、市、乡、镇。英：Ladakh; Sikkim; Arunachal Pradesh; map; boundary; district; state; village; geographical names; administrative. |
| G 中英印多语术语库 | 中：中印、印度、外交、机构、职务、条约、协定、法律、地名、民族、语言、翻译。英：China; India-China; diplomacy; ministry; minister; agreement; treaty; law; place name; language; translation; terminology. |

## B123

15. 逐站点检索与爬取操作手册

## B124

以下按“来源站点”逐一说明：从哪里进入、如何检索、推荐关键词、哪些页面应抓、哪些页面不应抓。站点结构核验日期：2026-09-07。网站改版后以 source_registry 更新为准。

## B125

CN-01  中华人民共和国外交部（MFA）

## B126

服务知识库：A / B / D / G

## B127

入口：https://www.mfa.gov.cn/

## B128

怎么检索：优先不用全站关键词盲搜，而是进入“国家和组织 → 国家（地区） → 亚洲 → 印度”，固定抓取“相关新闻、发言人有关谈话、讲话、文件、驻外报道”等子栏目；全站搜索仅用于补漏。对边界类正式资料，另进入“外交部 → 组织机构 → 边界与海洋事务司 → 边海国际条约/边海声明公报/相关新闻”。

## B129

推荐关键词（宽泛）：印度；中印；关系；边境；边界；外交；合作；会谈；会晤；声明；文件；和平；安全；贸易。具体机制名、事件名和年份仅在补漏时追加。

## B130

爬取/入库建议：首选抓固定国家页和栏目列表页，按发布日期增量；详情页提取标题、日期、来源、正文、附件和栏目。不要把首页推荐、页脚“相关链接”当正文。正式文件和新闻表述分不同 document_type。

## B131

CN-02  外交部条约数据库

## B132

服务知识库：A / G

## B133

入口：https://treaty.mfa.gov.cn/

## B134

怎么检索：进入首页“高级搜索”。第一步：类别=双边；第二步：缔约对象/关键词优先输入“印度共和国”（比“印度”更精准）；第三步：如只查边界类，可把“领域”筛选为“边界海洋”；第四步再用条约名称片段补搜。已知条约可直接按完整名称检索。

## B135

推荐关键词（宽泛）：在“缔约对象=印度共和国、类别=双边”等结构化条件下，主要使用边界、边境、协定、协议、条约、关系、合作、机制、和平、安全、贸易。具体条约全称只用于已知文件回查；“边界海洋”仅作领域筛选。

## B136

爬取/入库建议：抓搜索结果中的 detail1.jsp 详情页及中文/英文/印地文正式文本/PDF，保存条约名称、类别、领域、签署时间、生效时间、签署地点和多语文本链接。以 objid/条约唯一标识去重，同一协定多语版本用 agreement_id 对齐。

## B137

CN-03  国家法律法规数据库

## B138

服务知识库：C / G

## B139

入口：https://flk.npc.gov.cn/search

## B140

怎么检索：搜索页支持“标题”精确/模糊检索，并可用高级检索筛选法律法规分类、制定机关、时效性、公布/施行日期。已知法律名时先精确搜；主题发现时用模糊搜。地方规则优先筛“地方法规 → 西藏”，并把时效性优先设为“有效”。

## B141

推荐关键词（宽泛）：国界、边境、口岸、出入境、外国人、国籍、护照、国家安全、民族、宗教、地图、测绘、西藏。具体法律名称只用于精确回查。

## B142

爬取/入库建议：只抓命中主题的法律详情，不全库镜像。保存法律效力位阶、制定机关、时效性、公布日期、施行日期、网页版/公报原版下载链接；条文按“章-节-条”切片，版本变更通过相关文件和时效性字段管理。

## B143

CN-04  中国政府网—国务院政策文件库

## B144

服务知识库：C / B

## B145

入口：https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?t=zhengcelibrary

## B146

怎么检索：使用政策文件库搜索框；优先“搜索全文”发现主题，再切换“只搜标题”确认高相关文件。可按发布机构、主题分类、日期过滤，并按相关度/时间排序。对本项目重点关注外交部、公安/移民、国家民族事务委员会、自然资源等发布机构。

## B147

推荐关键词（宽泛）：边境、口岸、出入境、外国人、跨境、贸易、民族、宗教、地图、测绘、西藏、日喀则、安全。

## B148

爬取/入库建议：优先抓国务院文件、国务院部门文件和政策解读的详情页；保存发文机关、文号、成文/发布日期、正文和附件。政策解读与规范性文件分开标记，解读不能替代法规原文。

## B149

CN-05  西藏自治区人民政府

## B150

服务知识库：C / E / F

## B151

入口：https://www.xizang.gov.cn/

## B152

怎么检索：首页有站内搜索框“请输入您想要搜索的内容”。法律规则类同时固定抓“政府信息公开 → 政府规章库、行政规范性文件、信息公开目录”；地方背景类按“日喀则/地区 + 主题”搜索。

## B153

推荐关键词（宽泛）：边境、口岸、外事、贸易、宗教、民族、文化、行政区划、日喀则、条例、办法、规定、通知。具体县名可在区域补漏时添加。

## B154

爬取/入库建议：法规和规范性文件按栏目增量，不依赖全文搜索结果作为唯一入口；文化/地理信息只抓政府正式介绍和公开数据。对行政区划变化保存 effective_date；避免抓旅游营销转载作为高权威证据。

## B155

CN-06  西藏自治区外事办公室

## B156

服务知识库：E / B

## B157

入口：https://wsb.xizang.gov.cn/

## B158

怎么检索：当前站点以栏目导航为主，建议固定抓“民族风情、涉外常识、要闻动态、西藏新闻、信息公开目录”等栏目；如站内搜索不可稳定调用，不依赖搜索接口，而在抓取后的标题/正文中本地过滤。

## B159

推荐关键词（宽泛）：西藏、日喀则、民族、文化、宗教、信仰、礼仪、民俗、节庆、语言、外事、边境。

## B160

爬取/入库建议：按栏目分页抓标题、日期、正文；“海外预警”等外链栏目若跳转外交部/公众号，只保存原始权威来源链接，不重复入库。文化条目作为 A2 背景证据，不作为法律/政策结论依据。

## B161

CN-07  西藏自治区民族事务委员会

## B162

服务知识库：E / C

## B163

入口：https://mw.xizang.gov.cn/

## B164

怎么检索：固定抓“政策法规、政策解读、民族概况、重要文献、最新公开”等栏目。若站内搜索不稳定，采用栏目遍历 + 本地关键词过滤，并沿“国家民委/自治区政府”权威外链回查原文。

## B165

推荐关键词（宽泛）：民族、文化、语言、宗教、风俗、政策、法规、西藏、族群、民族事务。

## B166

爬取/入库建议：政策法规页面若转载国家层面法律，要记录原发布机关和原文 URL；同一文件不要因多站转载重复建 chunk。民族概况类按 community_id 建实体，记录适用区域。

## B167

CN-08  新华网

## B168

服务知识库：B / D（补充）

## B169

入口：https://www.news.cn/

## B170

怎么检索：新华网作为 B 级补充源，不建议全站爬。优先用站内/搜索引擎的 site:news.cn 限域检索，或从外交部事件页面中的新华社引用反向定位报道。按“主题 + 年份”检索历史事件。

## B171

推荐关键词（宽泛）：中印、印度、关系、边境、边界、外交、会谈、合作、声明、局势、和平、安全。历史回填时再加年份或事件名称。

## B172

爬取/入库建议：只抓与 event_id 关联的报道，提取标题、发布时间、来源、正文和引用的官方文件链接。新闻稿用于时间线和背景，不作为条约/法律问题的唯一证据。

## B173

IN-01  印度外交部 MEA（China 页面 + 高级搜索）

## B174

服务知识库：A / B / D / G

## B175

入口：https://www.mea.gov.in/china-in.htm

## B176

怎么检索：第一入口用 China 国家页，固定抓 India-China Relations、Important Documents 等。第二入口用 MEA Advanced Search，可选择 Everything、Speeches & Statements、Press Releases、Media Briefings、Parliament Q&A、Bilateral/Multilateral Documents，并按 Year/Month、Exact Match、Sort by Date 过滤。

## B177

推荐关键词（宽泛）：China; India-China; relations; border; boundary; agreement; treaty; cooperation; talks; meeting; statement; peace; security; trade. 具体机制名、缩写和年份仅用于补漏。

## B178

爬取/入库建议：China 固定页做历史种子；日常增量从 Advanced Search/Press Releases 按日期抓。保存内容类型和印度官方立场标识 IN_OFFICIAL。Parliament Q&A 单独类型化，问题与答复成对保存。

## B179

IN-02  印度外交部 MEA—Indian Treaties Database

## B180

服务知识库：A / G

## B181

入口：https://www.mea.gov.in/treatylist-generic.htm

## B182

怎么检索：Treaty / Agreement 页面支持 Enter Keyword、Subject、Sub-Subject、Type、Country、Ministry、Year of Signature/Entry into Force 等筛选。推荐先 Country=China + Type/Bilateral（如可选），再用关键词；已知年份时加 Year of Signature。

## B183

推荐关键词（宽泛）：China; India-China; bilateral; relations; border; boundary; agreement; treaty; cooperation; talks; peace; security. 已知条约再用正式名称精确检索。

## B184

爬取/入库建议：下载/抓取 Treaty 详情及附件，保存 Country、Subject、Type、年份和正式文本。与中方同一协定用 agreement_id 对齐，不把两侧版本覆盖合并。

## B185

IN-03  India Code

## B186

服务知识库：C / G

## B187

入口：https://www.indiacode.nic.in/?locale=en

## B188

怎么检索：首页支持 Search All，并可限定 Acts、Sections、Subordinate Legislations；进一步可选择 Rules、Regulations、Notifications、Orders、Circulars 等。结果页可按 Ministry、Department、Act Year、Short Title 等 facets 过滤。本项目优先 Ministry=Home Affairs。

## B189

推荐关键词（宽泛）：border; immigration; foreigners; visa; citizenship; passport; security; protected area; restricted area; land port; Ladakh; Sikkim. 具体法名仅用于精确回查。

## B190

爬取/入库建议：优先抓现行 Acts 及其 Sections、Rules/Notifications，保存 Enforcement Date、Ministry、Department、repeal/saving 信息。条文按 Section 切片；旧法不得与现行法混用，必须保留 status 和有效期。

## B191

IN-04  The Gazette of India / eGazette

## B192

服务知识库：C

## B193

入口：https://egazette.gov.in/

## B194

怎么检索：进入 Search Gazette。可按 Gazette ID、Ministry、Gazette Category、Notification Date、Publish Date 等检索；Category 搜索中还可使用 Ministry、Department、Part & Section、Reference No.、Subject、Keyword、日期范围。已知 S.O./G.S.R./Notification No. 时优先按编号搜，准确率最高。

## B195

推荐关键词（宽泛）：border; immigration; foreigners; visa; citizenship; security; protected area; restricted area; land port; Ladakh; Sikkim. Ministry、日期和 Gazette 类别优先作为筛选项，而不是堆入关键词。

## B196

爬取/入库建议：网站 URL 常带会话参数，不要把 session URL 作为主键；以 Gazette ID + PDF hash 作为稳定标识。抓官方 PDF、Ministry、Subject、Issue/Publish Date、Gazette ID。遇验证码/登录不绕过，转人工或使用公开可下载入口。

## B197

IN-05  Ministry of Home Affairs (MHA)

## B198

服务知识库：C / B

## B199

入口：https://www.mha.gov.in/

## B200

怎么检索：不依赖首页泛搜，优先固定抓 Divisions of MHA：Border Management-I Division、Foreigners Division、Foreigners II Division、Jammu & Kashmir and Ladakh Affairs；同时抓 Parliamentary Questions、Press Release、Acts/Rules/Notifications。Foreigners Division 内有 Acts, Rules and Regulations、PAP/RAP 等专门入口。

## B201

推荐关键词（宽泛）：China; border; border management; immigration; foreigners; visa; citizenship; security; land port; Ladakh; Sikkim; policy.

## B202

爬取/入库建议：按 Division 固定页和下载列表增量；PDF 保存标题、日期、文件号。只收公开政策、法律、通知和行政规则，避免将实时部署、警力位置等行动性信息作为知识库内容。

## B203

IN-06  Press Information Bureau (PIB)

## B204

服务知识库：B / D（补充）

## B205

入口：https://www.pib.gov.in/

## B206

怎么检索：“All Releases”可按 Ministry 和日期浏览；“Archives”支持按 Year/Month、Ministry 或关键词检索，历史资料从 1947 起可追溯；“Advance Search/Research Unit”可按 Sector、日期、语言、Title Keyword 搜背景材料。

## B207

推荐关键词（宽泛）：China; India-China; border; boundary; relations; government; foreign affairs; home affairs; defence; meeting; cooperation; security.

## B208

爬取/入库建议：作为事件背景补充源。按 Ministry+日期增量抓 Press Release；历史事件用 Archives 的年份/月/关键词回填。关键结论回链 MEA/MHA/法令原文，PIB 不替代 A1 证据。

## B209

IN-07  Census of India—Data Catalog

## B210

服务知识库：E / F / G

## B211

入口：https://censusindia.gov.in/nada/index.php/catalog/

## B212

怎么检索：在 Data Catalog 直接按数据表代码 + 地区 + 年份搜索，并用 Year、Data Type、Tags 等过滤。语言重点用 C-16 (Population by mother tongue)，宗教用 C-01 (Population by religious community)，行政/地方资料用 District Census Handbook、PCA、Administrative Atlas。

## B213

推荐关键词（宽泛）：language; mother tongue; religion; population; district; state; union territory; Ladakh; Sikkim; Arunachal Pradesh. 数据表代码和年份用于二次筛选，不作为唯一入口。

## B214

爬取/入库建议：优先下载表格/结构化文件，不把整张统计表转成一个长文本 chunk。按 geo_id + census_year + table_code 建表；保存原表名、地区层级、统计年份和数据字典。

## B215

IN-08  Ladakh Culture Department

## B216

服务知识库：E / G

## B217

入口：https://ladakh.gov.in/culture-department/

## B218

怎么检索：以固定栏目为主：Culture Department 首页、About Us、Roles and Responsibilities、Orders、Related Documents/Archives，以及 Ladakh Academy of Art, Culture & Languages 相关公开资料。站内搜索不稳定时采用栏目遍历 + 本地关键词过滤。

## B219

推荐关键词（宽泛）：Ladakh; culture; language; religion; customs; festival; heritage; literature; community; tradition.

## B220

爬取/入库建议：抓官方文化介绍、出版/档案/语言项目、文化机构资料；活动新闻可作背景但低权重。每条文化知识标注适用区域（Leh/Kargil/全 UT）和来源时间，避免把局部习俗泛化为全地区。

## B221

IN-09  Sikkim Culture Department

## B222

服务知识库：E / G

## B223

入口：https://culture.sikkim.gov.in/

## B224

怎么检索：优先抓官网固定板块：Bhutia Community、Lepcha Community、Ethnic Community、Archives、Song and Drama、Museum、News & Press Release、Notification & Circulars。若站内检索不可稳定使用，遍历栏目后本地过滤。

## B225

推荐关键词（宽泛）：Sikkim; culture; language; religion; customs; festival; heritage; community; tradition.

## B226

爬取/入库建议：社区介绍按 community_id 入库；活动、通知与文化常识分类型。涉及族群/语言名称时同步更新 G 库术语映射；不从旅游商业站补写未被官方材料支持的“禁忌/习俗”。

## B227

IN-10  Survey of India Online Maps Portal

## B228

服务知识库：F / G

## B229

入口：https://onlinemaps.surveyofindia.gov.in/

## B230

怎么检索：首页“Search for Maps/Digital Products”进入 Product Search，按 Location Name 检索；Quick Access 可直接进入 Administrative Boundary Database、Political Map of India、State Maps；另有 Geographical Names 入口。先搜行政区/城市名，再筛产品类型。

## B231

推荐关键词（宽泛）：Ladakh; Sikkim; Arunachal Pradesh; Uttarakhand; Himachal Pradesh; map; boundary; district; state; geographical names; administrative. 产品类型优先用门户筛选。

## B232

爬取/入库建议：主要抓公开产品元数据、地名、版本和行政层级；公开免费下载产品按许可下载。需要登录/付费/受限的产品遵守规则，不绕过限制。中印有争议的边界/地名必须保留 source_country=IN 和 perspective=IN_OFFICIAL_CARTOGRAPHIC_SOURCE，不与中方地图几何融合。

## B233

16. 七类库的来源—检索—入库对应关系

## B234

| 知识库 | 主要来源 | 检索策略 | 入库组织 |
| --- | --- | --- | --- |
| A 中印双边协定与机制库 | CN-02 外交部条约数据库；CN-01 外交部印度“文件/相关新闻”；IN-01 MEA China；IN-02 MEA Treaty | 先用“印度/中印 + 边境/边界/协定/条约/合作/会谈”等宽泛词发现材料；具体协定名和机制名只做补漏。 | 条约按条款切片，多语版本按 agreement_id 对齐，A1 最高证据。 |
| B 双方政策立场与公开表述库 | CN-01 MFA；IN-01 MEA；IN-05 MHA；IN-06 PIB；CN-08 新华网补充 | 先用“印度/中印 + 关系/边境/外交/会谈/声明/局势”等宽泛词做增量；必要时再加日期或具体事件名。 | 按立场分 CN_OFFICIAL / IN_OFFICIAL，不自动合并争议陈述。 |
| C 法律法规与行政规则库 | CN-03 国家法律法规数据库；CN-04 中国政府网；CN-05 西藏政府；IN-03 India Code；IN-04 eGazette；IN-05 MHA | 先用“边境/口岸/出入境/外国人/国籍/安全/民族/宗教”等主题词，并叠加有效性、部门和法律类型筛选；正式法名用于精确回查。 | 按章条/Section 切片，版本、时效、废止关系强制保存。 |
| D 历史事件与交涉案例库 | CN-01 MFA 历史页；IN-01 MEA；IN-06 PIB；CN-08 新华网；内部受控资料 | 先用“中印/印度 + 边境/事件/局势/会谈/声明”等宽泛词回填，再按年份、地点或具体事件做二次定位。 | 建立 event_id，将双方官方陈述、依据协定和后续节点挂到事件上。 |
| E 文化、宗教与语言库 | CN-06 西藏外办；CN-07 西藏民委；CN-05 西藏政府；IN-07 Census；IN-08 Ladakh；IN-09 Sikkim | 按“地区 + 文化/民族/语言/宗教/风俗/节庆”等宽泛主题检索；统计站点优先用地区和数据主题筛选。 | region_id + community_id + topic；文化结论限定适用区域。 |
| F 地理、地名与区域背景库 | CN-05 西藏政府/中国官方地图体系；IN-07 Census；IN-10 Survey of India | 按“地区/行政区 + 地名/地图/行政区划/边界”等宽泛主题检索；具体县市和地图产品名用于定位和补漏。 | 保留地图来源视角；争议边界不做自动融合。 |
| G 中英印术语与规范表达库 | CN-02 多语条约；CN-01 MFA 中英文；IN-01/02 MEA；IN-03 India Code；IN-07 Census；IN-10 Survey | 优先从正式多语文本中按“外交/机构/职务/条约/法律/地名/语言”等宽泛类别抽取术语；专名在抽取阶段归一，不依赖长关键词搜索。 | concept_id 对齐 zh/en/hi、别名、旧称、正式译法、来源。 |

## B235

17. 爬虫实施时的检索优先级

## B236

建议所有采集器统一执行下面的优先级，以减少“搜索结果不稳定”和“关键词漏召回”问题：

## B237

P1 固定权威栏目：国家页、条约库、法规库、Division/Department 页面，先完整遍历目录和分页。

## B238

P2 站内结构化搜索：利用 Country、Ministry、Year、Type、Validity、Category 等过滤器缩小范围。

## B239

P3 站内自由文本：用本文给出的 seed keywords，按同义词/缩写扩展检索。

## B240

P4 限域补漏：仅在站内搜索不可用或历史页难找时使用 site:domain + 关键词发现 URL，抓取后仍要求目标 URL 属于权威域名。

## B241

P5 本地二次筛选：标题、正文、栏目、实体词典、日期和立场联合打分；只在推荐链接/导航出现关键词的页面丢弃。

## B242

18. 采集结果最小验收清单

## B243

每个来源至少验证 10 个种子关键词能召回预期文档，并记录无结果/误召回案例。

## B244

A/C 库必须能回溯到正式原文或官方 PDF；B/D 库必须保留发布机构、发布时间和立场。

## B245

条约/法律文档必须保留版本和生效信息；搜索到历史旧版本时不能覆盖现行版本。

## B246

每个 chunk 必须带 source_url、citation_anchor、content_hash、crawl_time；PDF 还要保留页码。

## B247

对“印度/印度尼西亚”“LAC/其他缩写”等歧义词建立负面词和上下文约束。

## B248

eGazette 等会话型站点以稳定 Gazette ID/文号/PDF hash 作为主键，不依赖临时会话 URL。
