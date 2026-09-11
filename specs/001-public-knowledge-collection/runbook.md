# Linux 运行说明（正式 CLI）

版本：0.1.0｜日期：2026-09-11｜状态：本阶段交付的运行手册。原始阶段二命令在 Linux 环境执行；本轮按源码更正安装与配置传递说明，未重新执行全部示例。历史原始输出见
[证据日志](evidence/logs/t027-cli.txt)；命令只包装既有采集管线，不改变来源边界、robots、限速或质量阈值。

正式入口是已安装的控制台命令 `crawl`（源码 `src/crawler/cli.py`，等价入口 `python -m crawler`）。
`tools/realsite_smoke.py` 是开发核验工具，不是业务入口，不写入运行流程。

## 1. 适用范围与当前状态

已交付：来源配置校验、按来源采集、失败补抓、交付校验四类命令；单元与端到端夹具闭环见
[NEXT-01 证据](evidence/T027-cli-runbook.md)。

未交付：真实来源启用名单与时间范围（Q12/Q13 未决）、后台调度/守护进程、并发采集；
随包来源注册表只有默认禁用的 DEMO 示例。使用 `--config` 指向的站点配置仍是候选配置，
不等于该站已获准正式接入。

## 2. 环境要求

| 项 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Linux（x86_64 已验证） | 证据日志记录 `uname` |
| Python | CPython 3.9.25，由 uv 管理 | `.python-version` 固定；不由系统 Python 替代 |
| uv | 0.11.28（已验证；更高稳定版应同时复核） | uv 自身安装来源不属于 PyPI 镜像 |
| 网络 | 首次安装需可访问登记的清华镜像 | 镜像配置见 [uv 模板说明](uv-template.md)；失败先排查，禁止回退官方 PyPI |

解释器与系统组件来源单独核验（DEV-009）：`uv python install` 使用 uv 的解释器源，与 Python 包镜像不是同一件事。

## 3. 安装

从交付副本（含 `pyproject.toml`、`uv.lock`、`.python-version`、`src/`、`tests/`、`specs/`）开始：

```bash
uv python install 3.9.25                    # 仅缺少已固定解释器时；先确认解释器获取方式
# 保留仓库 .python-version，不执行 uv python pin 3.9 改写固定补丁版本
uv sync --locked --no-python-downloads        # 复现锁定依赖并安装 crawl 命令
test -e .env || cp .env.example .env          # 只复制样例，不覆盖已有 .env
uv run --locked --no-python-downloads crawl --help
```

首次生成的 `uv.lock` 只用于新工程；已有锁文件时 `uv sync --locked` 不重新解析依赖。
安装后 `crawl` 位于项目虚拟环境（`uv run` 会自动使用），无需激活 `.venv`。

## 4. 配置

| 变量 | 取值 | 规则 |
| --- | --- | --- |
| `CRAWL_ENV` | `development`（默认）或 `production` | 其他值、显式空值报配置错误 |
| `CRAWL_DATA_DIR` | 开发：默认工程根 `data/`；生产：必须显式绝对路径 | 显式空值报错；相对路径按工程根解析；生产缺路径或非绝对路径启动即失败，不静默回退 |

优先级：进程环境变量 > uv 显式加载的 `.env` > 应用默认值。开发用 `--env-file .env` 加载本机配置：

```bash
uv run --locked --no-python-downloads --env-file .env crawl sources
```

来源注册表：默认读取随包的 `src/crawler/config/sources.yaml`（仅含禁用的 DEMO）；采集其他来源时用 `--config PATH` 指定 YAML。
字段语义与访问边界见 [来源适配输入](source-adapters.md)，配置在加载期校验（域、路径、速率、超时、选择器正则）。

## 5. 命令与退出码

退出码：`0` 成功；`1` 运行完成但仍有失败或交付校验不通过；`2` 配置、参数或环境错误。

```bash
crawl sources [--config PATH] [--json]          # 校验来源配置并列出来源
crawl collect --source ID [--config PATH]       # 指定来源采集
    [--entry-url URL ...] [--keyword WORD ...] [--sitemap URL ...] [--api URL ...]
    [--max-items N] [--no-attachments] [--json]
crawl plan [--source ID] [--config PATH] [--ready-only] [--json]    # 补抓计划（只读）
crawl resume --source ID [--config PATH] [--max-tasks N]            # 执行补抓
    [--respect-backoff] [--max-attempts N] [--base-delay-seconds S] [--max-delay-seconds S] [--json]
crawl check [--require-nonempty] [--json]       # 交付校验（六项成果、schema、追溯）
```

补抓默认立即执行计划中的任务；加 `--respect-backoff` 只处理退避已到的任务，其余记入 `待人工`/`退避等待`。

## 6. 运行数据与成果

所有命令共用 `CRAWL_DATA_DIR` 一个数据根，六项成果与运行记录如下：

```text
数据根/
├── raw/<source_id>/<YYYY-MM-DD>/<kind>/   原件（HTML、附件等）
├── manifests/crawl_manifest.jsonl          抓取账本
├── manifests/failed_records.jsonl          失败账（只追加，含处置行）
├── normalized/documents.jsonl              完整文档
├── normalized/blocks.jsonl                 原始结构块
└── logs/crawler.log, metrics.json, metrics_history.jsonl   运行日志与计数
```

`crawl check` 校验包含 logs/ 在内的六项成果是否齐全、契约字段是否合法、documents/blocks 是否 100% 可追溯到原件，并拒绝数据根内出现采集阶段禁止的派生成果（切片、向量、索引等）。

## 7. 常见操作

开发数据根（示例为 `.env` 中的相对路径）：

```bash
uv run --locked --no-python-downloads --env-file .env crawl sources --config specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml
uv run --locked --no-python-downloads --env-file .env crawl plan --source CN-08 --config specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml
uv run --locked --no-python-downloads --env-file .env crawl check
```

生产数据根（由服务或调度器注入环境变量，绝对路径）：

```bash
CRAWL_ENV=production CRAWL_DATA_DIR=/var/lib/crawl-data \
  uv run --locked --no-python-downloads crawl check --require-nonempty
```

## 8. 故障处理

| 现象 | 含义与处理 |
| --- | --- |
| 退出码 2，`配置错误` | 环境变量、来源配置或域名/路径不合法；按提示修正，不要绕过校验 |
| 退出码 2，`来源未启用` | 该来源 `enabled: false`；启用属业务决定（Q12/Q13） |
| 命令输出 `跳过 robots_disallowed` | robots.txt 拒绝，按策略跳过并记原因；不绕过、不换代理 |
| 失败账 `error_type=http_error` | 网络阶段失败；`crawl plan` 给 `refetch`，`crawl resume` 重新获取 |
| 失败账 `adapter_selector_miss` | 逐来源正文选择器未命中：修复 `adapter.content_selector` 后 `crawl resume` 本地重解析，不重复下载 |
| 计划中 `action=manual` | 永久 4xx、重试耗尽或缺少原件；需人工确认后调整来源配置 |
| 429 / `Retry-After` | 客户端按站点要求退避；等待会超出本次运行预算时结束本轮，不高频探测 |
| 镜像连接失败 | 排查网络/DNS 或有记录地更换登记镜像；不退回官方 PyPI，不据此升级 Python |
| `check` 报缺失或契约错误 | 按提示定位：缺文件、越界 `raw_path`、字段不符或追溯悬挂引用 |
| 同日重复运行 | 账本按来源与日期续号，`crawl_id` 不复用；失败补抓按 `crawl_id` 定位原件 |

## 9. 已知限制
- `crawl sources` 的契约校验和 `crawl check` 需要工程源码树中的 `specs/001-public-knowledge-collection/contracts/`；仅安装 wheel、没有源码树时，命令以退出码 2 报“无法从源码位置识别工程根，不能定位 contracts/”，这是有意的显式失败，不静默跳过契约校验。
- 随包来源注册表只有禁用的 DEMO；真实来源接入待 Q12/Q13。
- 无后台调度/守护进程与并发采集，CLI 为单进程同步执行；旧式 DOC/XLS 转换需要系统 LibreOffice（本机尚未安装，见 NEXT-04 记录）。

## 10. 证据与验证

- 命令面与本机闭环（帮助、配置校验、采集、计划、补抓、交付检查、退出码）：[t027-cli.txt](evidence/logs/t027-cli.txt)
- 交付校验读取开发数据根（已保存原件，离线）：同上日志末节，manifest=10、documents=10、blocks=489、schema 通过、追溯 100%
- 环境与镜像复现历史证据：[t019-lock-provenance.txt](evidence/logs/t019-lock-provenance.txt)、[T003 环境验证](evidence/T003-environment.md)
- 测试：`uv run --locked --no-python-downloads pytest -q tests/test_cli.py` → 14 passed（见证据日志）

本说明不把工程夹具通过当作正式业务验收；业务用例状态与来源启用范围仍以
[验收规范](acceptance.md)、[待决事项](clarifications.md) 和 [阶段续作说明](continuation.md) 为准。

## 本轮更正与阶段三限制

上述 sources/plan 为读取配置和失败计划，不发起站点请求；check 需要数据根已有成果，空新目录不应宣称交付通过。CN-08 配置只供工程试点。collect 与 resume 必须传入与 plan 同一份 --config 和同一数据根；不能省略配置让默认 DEMO 注册表处理 CN-08。正文缺口和正式启用范围尚未解决。

当前 max-items/max-tasks 不限制全部 HTTP 请求或运行时间，CLI 尚无统一预算参数；runbook 的 Retry-After 超预算停止是后续要求，不能当作现有功能。按 stage-three.md NEXT-06 实现并验证后，再将真实参数和完整在线命令更新到这里。在此之前不照抄历史试点命令扩大线上运行。

契约资源仍依赖源码根，至少 sources（调用 load_contract）和 check（调用 validate_delivery）受影响；当前请使用完整源码交付副本。wheel 元数据存在不代表这些命令在源码外可用，NEXT-08 将补齐随包契约。运行期只允许一个写进程使用同一数据根；跨进程序号续接不等于多进程写入互斥。
