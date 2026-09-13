# 阶段四收口与阶段五计划（正式验收与交付收口）

## 本轮输入（2026-09-13）

用户要求加入阶段五：在阶段四 raw 优先开发（可执行部分已完成）之后，进入正式验收与交付收口的规划与执行。
本文件登记阶段五的目标、前置决定、工作项与退出条件，不代替 Q11/Q12/Q13/Q14 等业务决定；
未确认前不启动对应工作项，也不另造准备性任务或重复回归来延长时间。

## 阶段四基线（复用，不重做）

- 能力：按站发现抽象、`crawl collect --start-date`、最小结构分块；18 来源逐站适配（入口、发现、日期、附件）。
- 状态：18 来源 9 已实现并验证 / 0 实现待验证 / 9 访问受限 / 0 未完成，见
  [逐站状态](evidence/t026-eighteen-sources.md)。
- 证据：第 6—41 轮线上合计 171 请求、0 失败、0 绕过（1 次截止停止如实记录）；交付基线 406 passed、
  `crawl check` 追溯 100%，见 [续作记录](continuation.md) 的“2026-09-13 收口记录（第 42 轮）”。
- 未完成：T019/T026/T027 正式验收、受限来源处置、CN-04 分页/检索、后处理质量与发布（Q11/Q12/Q13/Q14）。

## 阶段五目标

按已确认的来源启用名单、访问方式与验收窗口，把阶段四的 raw 采集能力推进到**正式全范围验收**：

- 已实现来源做全范围（非有限样本）运行，逐项记录发现目标、成功留存、失败、跳过与未处理数量；
- 受限来源按决定落实允许的访问方式，或维持“访问受限”结论并更新证据；
- 完成后按验收规范记录 T019/T026/T027 的分母与实际结果，输出交付报告（工程版本、限制与剩余事项）。

## 前置决定（未确认不启动对应工作项）

| 决定 | 影响的工作项 | 确认后动作 |
| --- | --- | --- |
| Q12 来源启用名单与受限来源访问方式 | S5-01、S5-02、S5-03 | 冻结来源清单与访问规则，登记别名/许可方式 |
| Q13 域名别名归属（IN-03、CN-01 旧域） | S5-02 | 决定是否纳入边界，相应更新配置与边界用例 |
| 验收窗口与规模（起始日/回溯范围/每来源上限） | S5-01 | 写入验收运行登记，作为正式运行的统一窗口 |
| Q11 后处理质量阈值（若启用） | S5-05 | 冻结正文精抽取/OCR/近似去重阈值后做抽样评估 |
| Q01／NEXT-10 分块含义 | S5-06（T027 交付范围） | 选 A 复用 `blocks.jsonl` 纳入验收；选 B 先冻结规则再实施 |
| Q14 发布与交接方式 | S5-07 | 按确认方式构建交付物与运维交接 |

## 工作项

| 编号 | 工作项 | 依赖 | 交付与退出条件 |
| --- | --- | --- | --- |
| S5-01 | 正式验收运行（已实现 9 来源，全范围） | 启用名单、访问方式、验收窗口 | 逐来源运行记录与账本对账：发现目标/成功留存/失败/跳过/未处理计数齐全；raw 哈希与原件路径核对；documents/blocks 追溯 100%；失败账清零或有处置行 |
| S5-02 | 受限来源处置（9 个） | Q12/Q13 | 每个来源落实允许的访问方式并做有限核验，或维持“访问受限”并更新证据；不绕过 robots/登录/验证码 |
| S5-03 | CN-04 列表分页与检索通道 | Q12 | 实现允许的列表分页/检索通道，或记录不可行结论与替代入口 |
| S5-04 | 附件专项（按验收范围启用） | S5-01 范围 | 需要附件的来源逐条核对 sha256、`referrer_url` 与 attachment 契约 |
| S5-05 | 后处理质量（仅 Q11 启用时） | Q11 阈值 | 阈值冻结 + 抽样评估报告；未启用则保持 deferred，不降低 raw 标准 |
| S5-06 | T019/T026/T027 正式验收与交付报告 | S5-01—S5-05 | 按 [验收规范](acceptance.md) 记录分母与实际结果；满足完整完成标准才勾选任务 |
| S5-07 | 发布与交接 | Q14 | 构建产物、安装复现与运维交接按确认方式交付 |

## 边界与规则

- 不重做阶段四已完成的能力与验证；不把有限样本改名成正式验收；无新证据不重跑已适用回归。
- 正式运行遵守 DEV-012：先登记目的/来源/窗口/预算，显式使用 `--max-requests`/`--deadline-seconds`；
  遇登录、验证码或明确拒绝停止，不绕过；预算停止如实记录（不入补抓队列，继续方式为重跑该来源 collect）。
- raw 优先：原件、哈希、账本、失败对账与追溯是验收重点；零文档不得以空分母宣称通过。
- 后处理质量未启用时保持 deferred；不删除旧要求、不降低 raw 标准。

## 复现命令

与阶段四共用（运行说明见 [runbook.md](runbook.md)，收口记录见 [continuation.md](continuation.md)）：

```bash
# 离线（基线回归、契约、文档与已归档原件复算）
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads python -m crawler.cli check
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads python tools/sync_contracts.py --check
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads python tools/verify_sdd_documents.py
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads python tools/offline_replay.py \
  --config src/crawler/config/sources.yaml --data-dir data --start-date 2026-09-06

# 线上（先按 DEV-012 登记目的/来源/窗口/预算；示例为已实现来源）
UV_CACHE_DIR=/tmp/crawl-uv-cache timeout 200 uv run --locked --no-python-downloads python -m crawler.cli collect \
  --config src/crawler/config/sources.yaml --source CN-01 \
  --start-date 2026-09-06 --max-items 2 --max-requests 8 --deadline-seconds 240
```
