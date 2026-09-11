# 有限来源试点卡：CN-08 新华网（NEXT-03）

版本：0.1.0｜日期：2026-09-11｜状态：工程试点已完成一次，正式来源验收仍 WAITING_DECISION。

本卡是 Q12/Q13 的决策材料：给出一个来源可执行的试点参数、已完成的受限工程验证和仍然待决的事项。
它不启用任何正式来源，也不代替 T026 的逐站验收；正式注册表 `src/crawler/config/sources.yaml`
仍只有默认禁用的 DEMO 示例。

## 试点问题

在 CN-08 上，用离线已验证的栏目适配规则（`div.newsTitle a` + `news\.cn/.*\.html$`）和
0.5 req/s、单并发、无重试的预算，能否完成“栏目页发现 → 1 篇文章获取与解析 → 交付校验”闭环？

已有五轮核验只证明入口可达与浅层发现；本轮要验证的是**栏目级规则 + 正式 CLI + 交付校验**在真实来源上闭环，
并记录文章级抽取的缺口。

## 来源卡

| 项 | 取值 | 依据 |
| --- | --- | --- |
| source_id / 来源 | `CN-08` 新华网 | 登记来源（[source-adapters.md](source-adapters.md)） |
| 入口 | `https://www.news.cn/xinhuashe/`（栏目页；正式接入是否同时用首页待 Q12） | 已有原件与核验记录 |
| 允许域 | `news.cn`、`www.news.cn` | 来源配置 |
| 发现策略 | 适配规则：列表链接 `div.newsTitle a`；URL 正则 `news\.cn/.*\.html$`；`max_pages: 1` | 离线复算 15 个链接 → 3 篇文档 |
| 语种 / 类型 | `zh` / 新闻（B 级补充来源） | 来源配置 |
| 日期范围 | 仅当前栏目页可见文章；不做历史回填 | 历史范围属 Q13 |
| 速率 / 并发 | 0.5 req/s；并发 1 | 来源配置与工程保护预算 |
| 重试 / 超时 | `max_retries: 0`；连接 10s、读取 20s | 试点取最保守值 |
| 请求 / 时间上限 | ≤10 个 HTTP 请求（robots、重定向每跳、重试均计入）；≤5 分钟 | [阶段续作说明](continuation.md) 的 DEV-012 预算 |
| 结果上限 | 最多 1 篇文章；不下载附件；不做分页 | 控制试点面 |
| 验收样本 | 栏目页 1 个原件 + 文章 1 个原件；账本、文档、块、日志可追溯 | `crawl check` |

试点配置：[examples/pilot-cn08-sources.yaml](examples/pilot-cn08-sources.yaml)（执行时使用 `data/pilot-cn08-sources.yaml`，内容相同；与正式注册表分开）。关键字段：

```yaml
sources:
  - source_id: CN-08
    allowed_domains: [news.cn, www.news.cn]
    entry_urls: [https://www.news.cn/xinhuashe/]
    adapter:
      list_link_selector: "div.newsTitle a"
      list_link_pattern: "news\\.cn/.*\\.html$"
      max_pages: 1
    request_rate_per_second: 0.5
    max_concurrency: 1
    max_retries: 0
    enabled: true
```

## 离线准备（0 个新请求）

对已保存栏目页原件 `data/raw/CN-08/2026-09-11/html/index.html` 复算：`div.newsTitle a` 命中 3 条，
全部匹配 URL 正则且在允许域内（新华社智库报告、亚太共同体报告、大英图书馆入藏三条）。
通用规则在同一页命中 13 条，其中 10 条是导航——栏目规则的作用被再次证实。

## 在线执行（2026-09-11T20:58+08:00）

```bash
CRAWL_DATA_DIR=/tmp/cn08-pilot uv run --locked --no-python-downloads \
  crawl collect --config data/pilot-cn08-sources.yaml --source CN-08 --max-items 1 --no-attachments
CRAWL_DATA_DIR=/tmp/cn08-pilot uv run --locked --no-python-downloads crawl check
```

实际结果（原始输出见 [logs/t026-pilot-cn08.txt](evidence/logs/t026-pilot-cn08.txt)）：

- 请求 3 个 = robots.txt 1 + 栏目页 1 + 文章页 1，**低于 10 的预算**；用时 6 秒，失败 0、跳过 0；
- robots.txt 允许（1 组 1 规则），未发生重定向或重试；
- 采集文章 `https://www.news.cn/xinhuashe/20260907/b4ef6ed446654d7d94ca3827b256fb45/c.html`
  （10,184 字节，sha256 `31fcae825e5d…`），文档 `parse_status=ok`、语言 `zh`、发布日期 `2026-09-06`、10 个块；
- `crawl check`：六项成果齐全、契约 schema 通过、追溯 documents 1/1、blocks 10/10（100%）。

停止原因：试点问题已被回答且未触及预算或访问边界，按 DEV-012 立即结束，不再追加请求。

## 结论与限制

- 栏目级发现规则、单个文章获取、原件归档、文档/块产出与交付校验在真实来源上闭环成立，
  CN-08 可作为首批候选来源提交 Q12/Q13 决定；
- 文章正文当前使用通用 DOM 抽取（`bs4_lxml_dom`），尾部含“相关阅读”链接（全文 881 字，末尾 2 行是相关文章标题）；
  文章级正文选择器、字段定位（标题/日期）、附件与分页规则仍属 T026，待 Q12/Q13 后按站核验；
- 本试点不改正式启用状态，不构成至少 10 词、歧义验证或 T026 正式验收；历史范围与调度频率仍待 Q13。

## 相关记录

- [试点执行日志](evidence/logs/t026-pilot-cn08.txt)
- [试点证据与任务关系](evidence/T026-pilot-cn08.md)
- [五轮受限核验](evidence/logs/t026-realsite-smoke.txt)
