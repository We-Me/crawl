# NEXT-07 CN-08 正文边界修复与原件差异证据（2026-09-11）

本记录对应 [阶段三计划](../stage-three.md) NEXT-07（GAP-03），关联 T008/T013/T026。
修复在工程试点范围内完成，不启用正式来源、不改变 T026 的正式验收状态。

## 缺陷与定位

- 现象：CN-08 试点文章（`https://www.news.cn/xinhuashe/20260907/b4ef6ed446654d7d94ca3827b256fb45/c.html`）
  使用通用 DOM 抽取，10 个块中尾部 2 个是「新闻链接」相关阅读条目，另有两块重复标题；
  正文 881 字含无关内容。
- 原件核对：试点数据根 `/tmp/cn08-pilot` 仍在，文章原件
  `raw/CN-08/2026-09-11/html/c.html` sha256 `31fcae825e5d0c555b9abd7935f673102f6c746c3fb30e35f0bea6e384b4841b`
  与账本记录一致（10,184 字节），**无需重新抓取**。
- 排版依据：正文在 `<span id="detailContent">`；「新闻链接」相关阅读在容器外的
  `<div class="columBox relatedNews">`；标题 `<h1>` 在正文容器之外（PC 与移动各一处，
  通用抽取因此出现重复标题块）。

## 变更

1. `src/crawler/parser/html_parser.py`：使用正文选择器时，若容器内没有 h1/h2，
   按文档范围回退取标题（再退回 `<title>`）。标题在容器外时不再退化到带站点后缀的标题；
   容器内已有标题的既有来源行为不变。
2. CN-08 试点配置（`specs/001-public-knowledge-collection/examples/pilot-cn08-sources.yaml`）：
   `adapter.content_selector: "#detailContent"`。
3. 回归用例：`tests/test_html_parser.py::test_content_selector_excludes_related_reading_and_keeps_outer_title`
   与夹具 `tests/fixtures/site/detail_selector_title.html`（复现「标题在容器外 + 相关阅读在容器外」结构）。

## 证据（全部离线，0 个网络请求）

- 前后差异与原件哈希：[logs/next07-cn08-offline-diff.txt](logs/next07-cn08-offline-diff.txt)
  - 修复前：10 块 / 881 字（通用抽取）；修复后：6 块 / 751 字（`bs4_lxml_selector`）；
  - 6 个正文段落**逐字全部保留**；被移除的只有 2 个重复标题块与 2 个相关阅读 `list_item`；
  - 标题与容器外 h1 一致，已归档文档标题未被改动。
- 端到端离线重解析（`crawl resume` 本地重解析 + `crawl check`）：
  [logs/next07-cn08-reparse.txt](logs/next07-cn08-reparse.txt)
  - 用修复后的选择器重放同一原件：0 个请求、1 个文档（6 块）、失败账按 `recovered` 关闭；
  - `crawl check`：六项成果齐全、契约 schema 通过、documents 2/2、blocks 16/16（100%）。
    旧文档行与旧块保留（只追加），原件与 sha256 不变。
- 回归：`tests/test_html_parser.py` 16 passed；阶段候选全量回归 345 passed，见
  [阶段三完整回归](logs/stage-three-full-pytest.txt)。

## 限制与后续

- 本修复只覆盖 CN-08 当前文章模板；字段定位（标题/日期）、附件、分页规则与至少 10 词验证仍属 T026，
  待 Q12/Q13。
- 未做新的线上核验（原件完整且哈希一致，按 DEV-012/continuation.md 不重复请求）。
- 正式启用该来源与选择器版本冻结仍属业务决定，工程证据不代替 T026 验收。
