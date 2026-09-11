# 证据：T015 资料类型增量、条件请求与七类频率

日期：2026-09-11。目标平台：当前 Linux。对应需求：FR-016、KR-012；完成标准“304 不产生虚假文档；
新闻、法规、统计和类别更新按配置运行”。

## 实现

- `src/crawler/schedule/policy.py`：KR-012 七类建议频率登记为候选策略表（A 7 天 + major_document、
  B 1 天、C 7 天 + new_law、D 1 天 + historical_backfill、E 30 天、F 90 天 + boundary_change、
  G 随 A/B/C/F 取最短周期，A/B/C/G 标 P0）。表内每条都带来源行，`is_periodic_due` 在周期无法确定时
  返回 None（例如 G 类缺少同步对象），不猜测、不自动调度。启用哪些类别与真实周期仍属 Q01/Q13 待决。
- `src/crawler/schedule/incremental.py`：按资料类型给出增量动作——news 按发布时间增量
  （`is_newer_publication` 只比较可验证的 ISO 日期）、law 检查状态与哈希（条件请求）、statistics 按
  版本/年份（`CHECK_VERSION`）、general 通用条件请求；`conditional_headers` 由 ETag/Last-Modified 生成
  If-None-Match / If-Modified-Since，不做其他猜测。
- `src/crawler/schedule/state.py`：`manifests/incremental_state.json` 原子保存每个 URL 的
  ETag/Last-Modified/sha256/content_hash/crawl_id/发布日期/版本与最近 304 关联；文件位于账本目录内，
  不新增交付类别，也不复制文档内容。
- `src/crawler/fetch/http_client.py`：`open/get` 接受 `conditional` 头并原样透传；304 不进重试集合，
  由调用方决定复用既有原件。
- `src/crawler/pipeline.py`：抓取详情前读取状态并生成增量计划；收到 304 时记录状态
  （`not_modified_crawl_id` 指向前次成功 crawl_id）、计入 `RunCounters.not_modified` 与 skipped 原因，
  不写账本、不写原件、不生成文档；成功后写入状态（含 content_hash，与 Q04 候选一致）。
- `src/crawler/config/registry.py` + `sources.yaml`：新增可选 `resource_kind` 与 `update_policy`
  （key/period_days/triggers），配置校验拒绝未知类别、未知触发事件与非正周期；DEMO 虚构来源按 B 类示例
  登记，真实来源仍需 Q13 决定后启用。契约 `contracts/source-registry.schema.json` 同步登记这两个
  T015 候选扩展（`additionalProperties` 本就为 true）。

## 验收命令与结果

```bash
UV_CACHE_DIR=/tmp/crawl-uv-cache uv run --locked --no-python-downloads pytest -q
# 195 passed（其中 tests/test_schedule.py 7 项）
python3 tools/verify_sdd_documents.py
# PASS
```

关键用例：

| 用例 | 结果 |
| --- | --- |
| 七类频率表与 KR-012 对照 | A/B/C/D/E/F/G 周期、触发与 P0 标记逐项一致 |
| 周期到期与触发判定 | 8 天前成功判 A 到期、3 天前判未到期；G 无同步配置返回 None；未知事件报错 |
| 增量计划 | news→discover_new、law→conditional、statistics→check_version、无状态→fetch_always |
| 状态文件 | 记录成功校验信息；304 后保留 ETag 并把 `not_modified_crawl_id` 指向此前 crawl_id |
| 端到端 304 | 夹具 ETag 端点两次采集：第二次 documents=0、not_modified=1、resources=0，账本/文档/raw 字节不变 |
| 三类资料端到端增量（2026-09-11 补强） | 同一夹具站点分别按 news/law/statistics 运行：news 列表新增一条后只有新条目产生文档、旧条目 304 且只留一份；law 未改 documents=0、not_modified=1；statistics 换年份才更新（同址出现第 2 条记录且正文含 2026） |
| 条件头透传 | HttpClient 实际发送 If-None-Match |

本页 `195 passed` 是 T015 完成时的历史记录；AT 子句补强、真实页面缺陷修复与 T026 适配规则与配置/契约漂移用例之后当前全量为 310 passed（见
[t019-pytest.txt](logs/t019-pytest.txt)），其中 T015 相关验收在
[test_collection_acceptance.py](../../../tests/acceptance/test_collection_acceptance.py) 的 AT-016 内。

## 限制与待办

- 未引入调度框架或常驻进程；本任务是“按配置决定何时抓/是否条件抓”的机制，真实排期由 Q13 决定。
- 触发关系（重大文件、新法、区划变更）目前是配置与判定接口，事件源的接入属真实来源任务（T026）。
- 状态文件是运行状态，不作为交付成果；T018 组织交付目录时按此区分。
