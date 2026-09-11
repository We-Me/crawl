# T002 选型验证记录（环境与依赖部分）

日期：2026-09-11｜执行：Codex（Agent 工程决策，属 DEV-004 授权范围，不代表用户已指定框架）｜
状态：当前模块所选能力已验证；业务契约冻结仍待 T001，PDF、OCR、Office 解析选型留在后续任务。

## 环境与工具

| 项 | 值 | 证据 |
| --- | --- | --- |
| 目标平台 | Linux x86_64（WSL2 内核 6.6.114.1-microsoft-standard-WSL2），uv 平台标签 `linux-x86_64-gnu` | `uname -srm` |
| uv | 0.11.28 (`x86_64-unknown-linux-gnu`) | `uv --version` |
| 解释器 | CPython 3.9.25，由用户指定的 `uv python install 3.9` 安装并交给 uv 管理；来源是 uv 内置默认解释器源 `github.com/astral-sh/python-build-standalone`（未配置 UV_PYTHON_INSTALL_MIRROR），与 PyPI 包镜像无关；重复执行报 already installed | [t002-python-install.txt](logs/t002-python-install.txt) |
| 包源 | 清华镜像 `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/`，`default = true`，保留 `first-index` | pyproject.toml、uv.lock、[镜像证据](logs/t002-mirror-provenance.txt) |
| 选型工程 | `/tmp/t002-select`（隔离工程，不随仓库交付），独立空缓存 `/tmp/t002-select/uv-cache` | 见 logs |

镜像来源证据：`uv.lock` 中 18 条 registry 来源全部为登记镜像，115 条制品 URL 主机全部为
`mirrors.tuna.tsinghua.edu.cn`，解析日志 72 条索引引用同一主机；缓存为空时新建（31MB）。
没有出现官方 PyPI 回退。

## 技术决定

| 编号 | 适用模块 | 选择与版本约束 | 未采用方案 | 决策要点 |
| --- | --- | --- | --- | --- |
| TD-01 | 全部业务代码 | Python 3.9.25（`requires-python = ">=3.9,<3.10"`） | 3.10/3.11/3.12 等 | 3.9 下完整解析、安装、导入与样本测试通过，无需按次版本升级；后续加入 PDF/OCR 等若冲突再按规则重开 |
| TD-03 | 构建与打包 | hatchling，`src/crawler` 包发现 | setuptools、flit-core、pdm-backend | PyPA 指南认可的现代后端，配置小、支持 src 布局与可编辑安装；实际构建 wheel 与普通安装通过 |
| TD-04 | 测试 | pytest `>=8.4,<9`（解析为 8.4.2） | unittest（标准库） | 需求含固定样本、故障夹具与多模块测试；unittest 可用但夹具参数化和报告能力不足，选定成熟稳定的 pytest |
| TD-05 | HTTP 获取（T006） | requests `>=2.32,<3`（解析为 2.32.5，urllib3 2.6.3） | httpx、标准库 urllib | 同步采集管线；需要超时、流式下载、逐跳重定向控制与可配置退避；requests 接口长期稳定、使用积累最大，urllib3 提供 Retry。异步/HTTP2 当前范围不需要，若 Q13 明确高并发再评估重开 |
| TD-06 | HTML 解析（T008/T010） | beautifulsoup4 `>=4.13,<5`（4.15.0）+ lxml `>=5.3,<7`（6.1.3） | 标准库 html.parser、html5lib、selectolax | 需要容错解析、DOM 定位与结构顺序；bs4 接口稳定，lxml 提供快速解析与常见区块表达；cp39 manylinux wheel 实际安装成功，无需编译器。html5lib 较慢，selectolax 生态较新 |
| TD-07 | 来源配置（T004） | PyYAML `>=6.0.2,<7`（6.0.3） | 自写解析、ruamel.yaml | 只读结构化来源配置；PyYAML 成熟稳定，仅用 `safe_load`；ruamel.yaml 的往返注释能力当前不需要 |
| TD-08 | PDF/OCR/Office（T011/T012） | OPEN，按任务分批选型 | — | 候选：PDF 文本与定位（pypdf、pdfminer.six、pdfplumber、PyMuPDF）、OCR（Tesseract+pytesseract、RapidOCR、PaddleOCR）、Office（python-docx、openpyxl、LibreOffice 转换旧格式）。需在该任务内核查许可证、系统组件与目标平台后再定 |

已解析的直接/传递版本：requests 2.32.5、beautifulsoup4 4.15.0、lxml 6.1.3、PyYAML 6.0.3、
pytest 8.4.2、urllib3 2.6.3、certifi 2026.7.22、charset-normalizer 3.5.1、idna 3.19、soupsieve 2.8.4、
tomli 2.4.1、exceptiongroup 1.3.1、iniconfig 2.1.0、packaging 26.3、pluggy 1.6.0、pygments 2.21.0、
typing-extensions 4.16.0、colorama 0.4.6。

## 固定样本与验证命令

隔离工程使用本地回环 HTTP 服务（不请求真实站点）、虚构 HTML、CSV 附件与来源 YAML：

```bash
cd /tmp/t002-select
UV_CACHE_DIR=/tmp/t002-select/uv-cache uv lock --python 3.9 --no-python-downloads -v
UV_CACHE_DIR=/tmp/t002-select/uv-cache uv sync --locked --no-python-downloads -v
UV_CACHE_DIR=/tmp/t002-select/uv-cache uv run --locked --no-python-downloads pytest -q
```

结果：11 项样本检查全部通过，见 [t002-pytest.txt](logs/t002-pytest.txt)。覆盖：

- 逐跳重定向检查（`allow_redirects=False` + 域白名单）与最终 200；
- 流式附件下载字节与源文件 SHA-256 一致；
- 404 与成功可区分；
- HTML 标题、标题层级、段落、列表、表格行列与附件链接顺序正确；
- YAML `safe_load` 读出来源条目的 `source_id`、`enabled` 等字段。

已知行为：回环样本未声明 charset 时 requests 按 ISO-8859-1 回退解码，测试改为按字节 UTF-8 解码；
后续解析模块必须依据响应头或文档声明的字符集处理，不能直接信任 `response.text`。

## 已知限制与后续动作

- 成熟度判断结合发布与使用积累，以及本次在 3.9 上的实际解析安装结果；未逐库查阅官网声明，若后续评审需要官方页引用再补充。
- TD-05、TD-06、TD-07 的包尚未写入业务项目的 `dependencies`：按 DEV-007 在对应任务实现时引入，避免当前锁定未使用依赖；引入时只做本模块相关的最小变更。
- TD-01 的“完整环境”按当前已选范围判定；T011/T012 加入解析与 OCR 能力后如有冲突，按 3.9 → 3.10 → … 规则重开并记录。
- 业务契约（Q03—Q09 等）未冻结，本记录不改变这些 OPEN 状态。
