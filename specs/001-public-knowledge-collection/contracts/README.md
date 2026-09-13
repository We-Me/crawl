# 文件数据契约与使用规则

版本：0.1.0｜日期：2026-09-11｜状态：评审草案，尚未批准为实施基线

本目录提供六份 JSON Schema 评审草案。manifest/document/block 的主要必填字段来自 S1，failure 的至少信息项来自 S1；附件对象和来源注册表整体是设计候选。新增字段、非空、类型细化、URL 与相对路径规则均为本次契约化建议，不代表两原文都已明确规定。

## 契约清单

| 契约 | 对象 | 状态与检查方式 |
| --- | --- | --- |
| [manifest.schema.json](manifest.schema.json) | crawl_manifest 每行 | S1 §5 的基础字段；search 时必须有 keyword |
| [document.schema.json](document.schema.json) | documents 每行 | S1 §6 的必填层级；扩展字段不擅自提升为必填 |
| [block.schema.json](block.schema.json) | blocks 每行 | S1 §7；表格 text 例外的候选表达 |
| [failure.schema.json](failure.schema.json) | failed_records 每行 | S1 §12 信息项的候选类型表达 |
| [attachment.schema.json](attachment.schema.json) | document.attachments 每项 | 单独校验 Q07 候选，不强制混进 S1 基础文档 schema |
| [source-registry.schema.json](source-registry.schema.json) | 来源配置条目 | S1/S2 相关字段的设计整合，示例 enabled=false |

Schema 方言采用 [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)。format 在标准中有注解和断言区分，正式验收必须选择支持日期/时间/URI 格式断言的校验器或另做格式检查。还必须执行跨文件校验，不能仅凭 Schema 结果宣布验收完成。

## 编码与路径

交付 JSONL 使用 UTF-8，一行一对象，换行在 JSON 字符串中转义；零条记录允许空文件。候选路径使用 / 分隔，相对配置的数据根（开发默认项目根下 data/），不允许 ..、盘符、绝对路径或 Windows 反斜杠。相对根按用户补充的 [项目起步说明](../project-startup.md) 确定，记录不带 data/ 前缀，运行目录变更无需重写 raw_path；此约定不追溯为原文要求。时间示例使用 +08:00；实际要求为带时区时间，不限中国时区。

所有 schema 使用 additionalProperties=true，保留 S1 正文以及 S2 领域中尚未完整进入字段表的信息。它不等于允许任意修改已有字段含义。可选字段一般省略；只有明确声明 null 的字段接受 null。未知时不得填猜测值。

## 样例

[examples/data](../examples/data/) 是完全虚构的本地教学样例，域名 example.invalid 不用于实际网络请求。内含两个 HTML 原件、两条账本、两份文档、三块、一个失败记录和 logs，演示母页与成功附件关系。原件哈希由文件字节实际计算，但它们不是任何真实机构文档或采集成果。

样例选择 order=0、document.crawl_ids 和原件 sha256，仅用于验证候选 ADR-002/003 的可表达性，不表示 Q 项已解决。raw_path 相对 examples/data/。失败记录说明另一个下载失败 URL，不为其伪造成功账本。source-registry 示例独立存放，不计入 S1 六项成果。

## 必须额外检查的关系

1. manifest 指向的原件存在、字节哈希一致；示例中的 document.sha256 按已选示例语义指向主原件。
2. doc_id、block_id、crawl_id 唯一，block.doc_id 和候选 crawl_ids 存在。
3. 每文档 order 递增且无重复，起点遵循所选契约；全文和结构块可对照原件。
4. 附件成功记录有独立原件及账本；失败有失败账，关联语义见 Q07。
5. 版本、引用、实体、立场及内容完整性按数据模型和 acceptance 验证；JSON Schema 无法证明这些业务事实。

评审顺序：先确认 [待决事项](../clarifications.md)，再决定基础 schema 和候选扩展的正式组合及版本；然后用实际采集夹具验收。这里的样例检查仅证明文档和示例契约可用。

## 当前分块边界（2026-09-13）

现有 blocks 契约保持原始结构块含义；跨段语篇组合尚未确认，不据此修改现有字段或 JSON Schema。本轮不包含 RAG，候选派生单元须先明确规则与原块追溯关系，见 [当前范围与分块](../scope-and-blocking.md)。
