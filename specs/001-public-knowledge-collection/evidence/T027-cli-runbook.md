# T027 子项：正式 CLI、运行说明与缺陷修复（2026-09-11）

本记录覆盖 NEXT-01 与 NEXT-02：正式业务入口 `crawl`、Linux 运行说明、以及闭环中发现并修复的
一个真实缺陷。它不把 T027 标成完成：总体验收（T019/T026 正式收口、来源决定）仍未进行。

## 交付物

| 交付 | 位置 | 说明 |
| --- | --- | --- |
| 正式 CLI | `src/crawler/cli.py`、`src/crawler/__main__.py` | 子命令 `sources`/`collect`/`plan`/`resume`/`check`；退出码 0/1/2 |
| 控制台入口 | `pyproject.toml` 的 `[project.scripts]` `crawl = "crawler.cli:main"` | 由 `uv sync --locked` 安装，未新增依赖 |
| 运行说明 | [runbook.md](../runbook.md) | Linux 安装、配置、采集/补抓/校验、成果位置、故障处理、已知限制 |
| CLI 用例 | `tests/test_cli.py` | 14 项：帮助、配置校验、契约不符、闭环采集、交付检查、计划与补抓、退出码 |

CLI 只调用既有模块（`load_settings`、`SourceRegistry`、`CrawlPipeline`、`inspect_delivery`、
`validate_delivery`、`trace_delivery`），不复制解析或校验逻辑，也不放宽来源边界与阈值。

## 闭环中发现并修复的缺陷

本机闭环第一次执行时暴露：**同一来源同一天分两次运行，`crawl_id` 从 `0001` 重新计数**，
账本出现重复主键；失败账按 `crawl_id` 取原件时命中上一次运行的文件，重解析使用错误原件
（日志中 `detail_adapter.html` 的失败被解析为 `detail_1.html`）。

- 根因：`CrawlPipeline._sequence` 是实例内计数，跨进程不延续；
- 修复：`_next_crawl_id` 从账本中同来源同日期前缀的最大序号续号（`_max_crawl_sequence`），
  序号只来自已落盘记录，跨进程运行保持唯一；
- 回归：`tests/test_pipeline.py::test_crawl_ids_continue_across_runs`
  （两次运行编号不同，且失败计划的 `raw_path` 指向本次运行的原件）。

## 验证

命令均在本机 Linux 实际执行，原始输出见 [logs/t027-cli.txt](logs/t027-cli.txt)
（`uv run --locked --no-python-downloads`，本地回环夹具站点，无外部站点请求）：

```text
uv run --locked --no-python-downloads crawl --help/--version     # 0
uv run --locked --no-python-downloads crawl sources              # 随包注册表（DEMO 禁用，契约校验通过）
uv run --locked --no-python-downloads crawl sources --config ... # 0；缺文件/非法条目 → 2
uv run --locked --no-python-downloads crawl collect --source NOPE # 2（未登记）
uv run --locked --no-python-downloads crawl collect --source TESTSRC --max-items 1  # 0
uv run --locked --no-python-downloads crawl check                # 0（schema 通过、追溯 100%）
uv run --locked --no-python-downloads crawl collect（选择器未命中） # 1（失败账 stage=parse）
uv run --locked --no-python-downloads crawl plan --json          # 0（reparse 计划）
uv run --locked --no-python-downloads crawl resume               # 恢复 1；永久 4xx 保持待人工 → 1
uv run --locked --no-python-downloads pytest -q tests/test_cli.py # 14 passed
```

运行说明中的 `.env` 命令另以开发数据根核验（离线读取已保存原件）：
`crawl sources`、`crawl plan`（0 项）、`crawl check`（manifest=10、documents=10、blocks=489、
契约通过、追溯 100%）→ 退出码 0。

## 限制与未完成

- 真实来源未启用（Q12/Q13）；随包注册表只有禁用的 DEMO 示例；
- 无后台调度/守护进程与并发采集；CLI 是单进程同步执行；
- T012 的 LibreOffice 转换缺口、T019/T026/T027 正式验收仍待处理，见
  [阶段续作说明](../continuation.md)。
