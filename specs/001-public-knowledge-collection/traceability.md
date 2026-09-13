# 需求来源与实施验收追踪矩阵

## 最新用户决定（2026-09-13，六项确认）

用户已明确：全部 18 来源、运行时起始时间、按站适配抽象类、独立结构块与 div 空行分块的最小 dummy 实现；当前优先 raw 完整正确与追溯，后处理优化及最终发布暂缓。原文基础数据格式保持，扩展差异见 [结构对照](structure-comparison.md)。当前开发按 [raw 优先决定](raw-first-development.md) 推进；本文件下方早期“等待分块选择/首批来源/发布方式”按历史理解，不再阻塞已授权工作。NEXT-04/T012 已完成；新抽象接口、时间参数及 18 站逐站实现仍待开发。

## 最新环境状态

2026-09-13 用户已提供目标 WSL 安装成功证据：/usr/bin/soffice，LibreOffice 24.2.7.2 420(Build:2)，uv run 下 find_soffice() 同样返回 /usr/bin/soffice。NEXT-04 已用该组件完成真实 OLE2 DOC/XLS 转换、结构保留、失败路径与原件追溯验证，T012 勾选完成，见 [NEXT-04 证据](evidence/next04-legacy-office.md)；受限沙箱内 5 项依赖组件的用例按能力探测 skip，已于 2026-09-13 在目标 Linux 正常 shell 复跑，13 项全部通过（详见证据文件）。第四阶段整体仍未完成（T019/T026/T027 与正式业务待决）。下文早期缺组件/权限记录按历史时点理解，不再作为等待安装的理由。

版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

一行映射一条需求到原文、场景、设计模块、主要任务和验收用例。公共前置任务及最终收口见 tasks.md。范围待定不等于漏项，条件需求仍保留追踪。2026-09-11：采集闭环 T003—T009、多格式解析 T010—T013、去重与版本 T014、增量调度 T015、失败补抓 T016 、运行日志/计数对账 T017、交付目录组织 T018 与采集验收 T019 已完成夹具级验证，记录见 [evidence/T004-T009-collection.md](evidence/T004-T009-collection.md)、[evidence/T010-T013-parsers.md](evidence/T010-T013-parsers.md)、[evidence/T014-dedup-versioning.md](evidence/T014-dedup-versioning.md)、[evidence/T015-schedule.md](evidence/T015-schedule.md)、[evidence/T016-recovery.md](evidence/T016-recovery.md) 、[evidence/T017-logs-metrics.md](evidence/T017-logs-metrics.md) 、[evidence/T018-delivery.md](evidence/T018-delivery.md) 与 [evidence/T019-acceptance.md](evidence/T019-acceptance.md)；同日按 FR-001/S3 C02 补上 robots.txt 规则执行（Disallow/Allow 最长匹配、不可用保守策略，见 [evidence/T004-T009-collection.md](evidence/T004-T009-collection.md)），夹具验收报告见 [evidence/logs/t019-acceptance-report.json](evidence/logs/t019-acceptance-report.json)，AT-014/AT-024 因 Q11 保持 blocked；附件在管线中的独立文档化随 Q07 处理。2026-09-11 另按 FR-005 补上正文分页与接口正文还原（内容区 rel=next/翻页文案、JSON alternate 正文端点；部分失败标 partial 并写失败账），见 [evidence/T004-T009-collection.md](evidence/T004-T009-collection.md)；同日按用户许可对 CN-01/CN-03/IN-01/IN-06 做了一轮最小请求量真实站点核验（14 个请求，遵守 robots 与来源限速），并对 CN-01/IN-01 做第二轮回访确认条件请求在真实站点退化为完整获取，第三轮以栏目页入口核验发现行为（IN-01 栏目页可访问但通用发现选中首页，CN-01 栏目页 75 条链接指向旧域或子域），记录见 [evidence/logs/t026-realsite-smoke.txt](evidence/logs/t026-realsite-smoke.txt)；同日第四轮对另外 9 个权威来源做浅层可达性核验（CN-05/06/07 的 robots 508 与 IN-04 及部分主机的 robots 获取失败均按保守拒绝处理、IN-03 链接指向别名域、CN-02 无可发现站内链接），并据此修复真实页面暴露的空标题块解析缺陷与补抓来源过滤缺陷（新增 2 项回归用例，见 [evidence/logs/t008-cn04-defect-fix.txt](evidence/logs/t008-cn04-defect-fix.txt)）；同日实现 T026 机制部分：逐来源适配规则（列表链接选择器/正则、分页终止条件、正文范围选择器，未命中显式记录、不静默回退），在固定夹具与真实原件上验证（CN-08 栏目发现 13→3、CN-04 正文 145→2），并以契约 schema 校验随包来源配置防漂移，全量 310 passed，见 [evidence/logs/t026-adapter-mechanism.txt](evidence/logs/t026-adapter-mechanism.txt)；第五轮补齐 CN-08/IN-07—IN-10，18 个登记来源均完成浅层可达性/robots 核验（IN-07/08/09 获取失败与 CN-05/06/07 的 508 保守拒绝、IN-10 空正文按 partial 记录）；完整真实来源验收（Q12/Q13）、T026 适配器与领域任务仍未执行。

| 需求 | 原文定位 | 场景 | 模块 | 主要任务 | 验收 | 待决 |
| --- | --- | --- | --- | --- | --- | --- |
| FR-001 公开访问与域名边界 | S1 §3.4；S2 §1；S3 C02 | US1 | M01 | T004 | AT-001 | Q13 |
| FR-002 来源配置与适配器 | S1 §14；S2 §11；S3 C13/C14 | US1 | M01 | T004 | AT-002 | Q10 Q13 |
| FR-003 页面发现策略 | S1 §3.1；S2 §17；S3 C03 | US1 | M02 | T005 | AT-003 | Q12 |
| FR-004 宽泛关键词与候选标签 | S1 §3.2/§6；S2 §13—14；S3 C04/C05 | US1 | M02 | T005 | AT-004 | Q02 |
| FR-005 详情页与正文完整获取 | S1 §3.3/§9；S4 二 §3.3 | US1 | M03 | T006 | AT-005 | Q06 |
| FR-006 附件独立下载与关系 | S1 §3.3/§6；S4 一 §1.2 附件 | US1 | M03 | T006 | AT-006 | Q05 Q07 |
| FR-007 原始资源保真归档 | S1 §4/§13；S2 §18；S3 C07 | US1 | M03 | T007 | AT-007 | Q05 |
| FR-008 抓取账本 | S1 §5；S4 二 五 | US1 | M03 | T007 | AT-008 | Q03 Q15 |
| FR-009 完整文档数据 | S1 §6；S3 C06 | US1 | M05 | T009 | AT-009 | Q03 Q04 Q06 Q08 Q09 |
| FR-010 原始结构块 | S1 §7/§9；S3 C08 | US2 | M04 | T010 | AT-010 | Q09 |
| FR-011 PDF 与 OCR 定位 | S1 §7—9/§13；S2 §18；S3 C08 | US2 | M04 | T011 | AT-011 | Q04 Q11 |
| FR-012 Office 与结构数据解析 | S1 §8/§10；S2 §11 Table/Data Loader；S3 C09 | US2 | M04 | T012 | AT-012 | Q08 |
| FR-013 保真清洗与标准化 | S1 §9；S4 二 九 | US2 | M05 | T013 | AT-013 | Q06 |
| FR-014 去重与来源关系 | S1 §3.3/§11；S2 §11；S3 C10 | US3 | M06 | T014 | AT-014 | Q04 Q05 Q11 |
| FR-015 历史版本与失效记录 | S1 §11/§13；S2 §6/§18；S3 C11 | US3 | M06 | T014 | AT-015 | Q04 Q09 |
| FR-016 分类增量更新 | S1 §11；S2 §12；S3 C12 | US3 | M07 | T015 | AT-016 | Q13 Q15 |
| FR-017 失败记录与补抓 | S1 §12/§13；S3 C15 | US3 | M07 | T016 | AT-017 | Q15 |
| FR-018 运行日志与交付对账 | S1 §2/§12—14；S4 一 §1.3 logs | US3 | M08 | T017 | AT-018 | Q11 Q15 |
| FR-019 采集成果文件交付 | S1 §2/§4.2/§15；S4 二 最终交付物 | US4 | M08 | T018 | AT-019 | Q01 Q14 |
| FR-020 采集阶段边界 | S1 §1.2/§7.1/§15；S2 §1/§4/§16/§18；S4 一 §1.1 | US4 | M08 | T018 | AT-020 | Q01 |
| NFR-001 端到端可追溯 | S1 §13；S2 §18；S3 C01/C16 | US4 | M08 | T019 | AT-021 | Q03 |
| NFR-002 JSONL 与字段约束 | S1 §13；S4 二 十三 | US4 | M08 | T019 | AT-022 | Q06 Q08 Q09 |
| NFR-003 请求控制参数 | S1 §3.4；S4 一 §1.3 运行参数 | US1 | M03 | T006 | AT-023 | Q13 |
| NFR-004 内容与结构质量 | S1 §13；S2 §18；S3 C16 | US4 | M08 | T019 | AT-024 | Q11 |
| KR-001 来源等级与立场 | S2 §1—3/§5/§18；S4 一 §1.2 | US5 | M09 | T020 | AT-025 | Q01 Q10 |
| KR-002 协定与机制组织 | S2 §4/§16 A | US5 | M09 | T021 | AT-026 | Q01 Q02 Q04 Q09 |
| KR-003 政策立场与表述组织 | S2 §5/§16 B/§18 | US5 | M09 | T021 | AT-027 | Q01 Q02 Q10 |
| KR-004 法律法规组织 | S2 §6/§16 C/§18 | US5 | M09 | T021 | AT-028 | Q01 Q02 Q04 |
| KR-005 事件与证据关联 | S2 §7/§16 D | US6 | M10 | T022 | AT-029 | Q01 Q02 Q09 |
| KR-006 内部材料受控导入 | S2 §1/§7/§11 Controlled Import；S4 一 §1.1 | US6 | M10 | T022 | AT-030 | Q01 Q16 |
| KR-007 文化知识区域化 | S2 §8/§16 E | US6 | M10 | T023 | AT-031 | Q01 Q02 Q09 |
| KR-008 地名地图与来源视角 | S2 §9/§16 F；§15 IN-10 | US6 | M10 | T023 | AT-032 | Q01 Q02 Q09 Q10 |
| KR-009 多语术语实体 | S2 §10/§16 G | US5 | M09 | T024 | AT-033 | Q01 Q02 Q09 |
| KR-010 领域切片与检索交接 | S2 §1/§3/§16/§18；S4 一 §1.1 | US5 | M09 | T025 | AT-034 | Q01 Q02 Q04 Q17 |
| KR-011 关键词验证与歧义控制 | S2 §13/§18；S4 一 §1.3 | US4 | M02 | T026 | AT-035 | Q11 Q12 Q13 |
| KR-012 七类更新与建设顺序 | S2 §12；S4 三 §12 | US5 | M07 | T015 | AT-036 | Q01 Q13 |
| KR-013 来源专属规则保留 | S2 §4—10/附录/§15/§18；S4 四 §4.1 | US4 | M02 | T026 | AT-037 | Q12 Q13 |

## S3 共同要求覆盖

| 原审查编号 | 本规格需求 |
| --- | --- |
| C01 | FR-007 FR-008 FR-009 NFR-001 |
| C02 | FR-001 |
| C03 | FR-003 |
| C04 | FR-004 |
| C05 | FR-004 KR-011 |
| C06 | FR-009 KR-001 |
| C07 | FR-007 NFR-001 |
| C08 | FR-010 FR-011 KR-010 |
| C09 | FR-012 |
| C10 | FR-014 |
| C11 | FR-015 KR-004 |
| C12 | FR-016 KR-012 |
| C13 | FR-002 FR-011 FR-012 |
| C14 | FR-002 |
| C15 | FR-017 FR-018 |
| C16 | NFR-001 NFR-002 NFR-004 KR-011 |
| C17 | FR-004 KR-002 KR-003 KR-004 KR-005 KR-007 KR-008 KR-009 |

## S4 差异审查覆盖

阶段和领域差异对应 Q01/Q02/Q16/Q17；字段差异对应 Q03—Q10；交付与验收口径对应 Q05/Q11/Q13/Q14/Q15；发现和站点排除说明对应 Q12/Q13。S4 已排除的专站内容在 sources/S2-transcript.md 完整转录，并在 source-adapters.md 登记适配输入，未冒充共同要求。此前新增目录、发布文件及分类审批流程未被写成已确认需求。

## 开发约束独立追踪

用户后续目录指令 → DEV-008 → [项目起步说明](project-startup.md) → T003/T004/T018/T019 → CFG-01—CFG-09（已全部执行：CFG-01—CFG-05、CFG-09 见 [evidence/T003-environment.md](evidence/T003-environment.md)，CFG-06—CFG-08 见 [evidence/T019-acceptance.md](evidence/T019-acceptance.md) 与 [logs/t019-cfg.txt](evidence/logs/t019-cfg.txt)）。业务来源的 37 条需求及 AT 映射保持不变；Q14 目录部分已明确，仓库和发布策略仍 OPEN。

DEV-009：用户镜像要求 → [uv 模板说明](uv-template.md) 与 templates/uv/pyproject.toml → T002/T003 → 镜像来源及环境复现验收（起步环境已执行，见 [evidence/T002-selection.md](evidence/T002-selection.md)；新增运行依赖时按同一流程复核）。

## 后续工程约束追踪

DEV-010 测试停止规则、DEV-011 有限续作、DEV-012 守规线上测试 → [阶段续作说明](continuation.md) → T012/T019/T026/T027 对应子项。保留原有业务需求及 AT 编号，T012/T019 状态更正不删除已执行证据。

## 阶段二复核后的续作入口

阶段三基线为阶段二提交 4f07c6f 之后的续作：NEXT-06—NEXT-08 已完成工程交付（统一请求预算与停止报告、CN-08 正文边界修复、随包契约与源码外安装），阶段候选一次全量回归 345 passed，证据见 [阶段三计划](stage-three.md) 与 [NEXT-06](evidence/next06-budget.md)、[NEXT-07](evidence/next07-cn08-body.md)、[NEXT-08](evidence/next08-packaged-contracts.md)。NEXT-04 仍受 Linux 组件权限阻塞，NEXT-05 仍待业务决定；不重复 NEXT-01/02 或全量测试来消耗等待时间。T012/T019/T026/T027 保留部分完成状态。

## 阶段三后的当前入口

NEXT-06/07/08 已由阶段三提交 d39bdc0 完成工程交付，历史候选回归 345 passed。NEXT-09 工程交付清单（[delivery-inventory.md](delivery-inventory.md)）与 NEXT-05A 决策确认栏（[decision-requests.md](decision-requests.md)）已交付，按 [阶段四交付收口](stage-four.md) 等待业务确认与 Linux 组件条件；保留 NEXT-04 环境阻塞及正式业务待决，T012/T019/T026/T027 不自动勾选完成。无新变更不重复测试或扩站。

## 2026-09-13 当前范围与续作

以 [当前范围与分块](scope-and-blocking.md) 为本轮入口：NEXT-09/NEXT-05A 已完成，NEXT-10 仅澄清原始结构分块与跨段语篇组合的差异。本轮不安排 RAG，T025 保留为范围外追踪且不勾选完成；T020—T024 为未选条件范围。原始业务需求和历史 AT 记录不删除，KR-010/AT-034 的检索部分不作为本轮验收门槛，来源相关 KR-011—KR-013 仍按已选范围处理。正式采集质量、来源与旧格式组件缺口继续保留，不因范围收敛自动通过。
