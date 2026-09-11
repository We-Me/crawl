# T003 工程初始化与配置验证记录

日期：2026-09-11｜执行：Codex｜状态：工程初始化、构建配置、固定样本与 CFG-01—CFG-05、CFG-09 已完成；
T004 的来源注册表与访问边界部分未开始。tasks.md 的 T002/T003 仍未勾选：T001 的业务契约冻结未完成，
本记录只覆盖工程环境部分。

## 交付物

| 路径 | 说明 |
| --- | --- |
| `pyproject.toml` | 由 [uv 模板](../../../templates/uv/pyproject.toml) 合并而来；移除 `package = false`；`hatchling` 构建后端与 `src/crawler` 包发现 |
| `.python-version` | `3.9.25`（实测补丁版本） |
| `uv.lock` | 锁定 9 个 registry 包，全部登记镜像来源；项目自身为本地可编辑安装 |
| `src/crawler/config/settings.py` | `load_settings(environ, project_root=None)` 统一配置入口 |
| `tests/test_settings.py`、`tests/test_fixtures.py` | 配置契约与夹具完整性测试，共 38 项通过 |
| `tests/fixtures/` | 网页、附件、OCR、表格、失败、版本固定样本，见 [夹具说明](../../../tests/fixtures/README.md) |
| `tools/make_fixture_binaries.py` | 确定性生成二进制夹具；与 SDD 文档生成脚本无关 |

配置要点：`requires-python = ">=3.9,<3.10"`；`[tool.uv] prerelease = "disallow"`、`index-strategy = "first-index"`；
登记清华索引 `default = true`，无官方 PyPI 回退；开发依赖组 `dev = ["pytest>=8.4,<9"]`，
当前无运行依赖（按 DEV-007 在对应模块实现时引入）。

## 命令与结果

```bash
uv python pin 3.9.25
UV_CACHE_DIR=/tmp/crawl-uv-cache uv lock --no-python-downloads -v
UV_CACHE_DIR=/tmp/crawl-uv-cache uv sync --locked --no-python-downloads -v
uv run --locked --no-python-downloads python --version     # Python 3.9.25
uv run --locked --no-python-downloads pytest -q            # 38 passed
```

锁定与同步证据见 [t003-lock-sync.txt](logs/t003-lock-sync.txt)：`uv.lock` 中 9 条 registry 来源与
27 条制品 URL 全部指向 `mirrors.tuna.tsinghua.edu.cn`；首次解析使用独立空缓存 `/tmp/crawl-uv-cache`。
上述数字对应 T003 当时的空运行依赖 + dev 组；T010—T013 扩充 PDF/OCR/Office 运行依赖后的交付态来源核查与干净复现见 [t019-lock-provenance.txt](logs/t019-lock-provenance.txt)。

## CFG 场景结果

| 编号 | 操作 | 结果 | 证据 |
| --- | --- | --- | --- |
| CFG-01 | 开发源码工程，未设置目录变量 | PASS：`data_dir=/home/zhou/workspaces/crawl/data`，与 `src/` 同级，`default=True` | [t003-cfg-01-05.txt](logs/t003-cfg-01-05.txt) |
| CFG-02 | `.env` 为 `./data`，进程变量为 `/tmp/cfg02-process` | PASS：解析为 `/tmp/cfg02-process`，进程变量优先；`.env` 注入检查显示 `CRAWL_DATA_DIR='./data'` | 同上 |
| CFG-03 | 从 `/tmp` 执行，变量为 `./data` | PASS：`cwd=/tmp`，`data_dir` 仍为工程根下 `data/`，不随工作目录或 `.env` 位置改变 | 同上 |
| CFG-04 | 生产缺少目录、显式空、相对路径 | PASS：三种情况均抛出 `ConfigurationError`，不回退开发目录；绝对路径正常通过 | 同上 |
| CFG-05 | 有效新目录、路径是文件、父目录无写权限 | PASS：有效目录自动创建；文件与无权限父目录均明确失败 | 同上 |
| CFG-09 | 可编辑安装与 wheel 普通安装后从工程外导入 | PASS：可编辑导入解析到 `src/crawler/`；wheel 安装到全新 venv 后解析到 `site-packages`，均不依赖 `PYTHONPATH` 或源码 cwd | [t003-cfg-09.txt](logs/t003-cfg-09.txt) |
| CFG-06 | 生产绝对目录位于工程外、无源码树 | 未执行：属 T018/T019 | — |
| CFG-07 | 原数据搬迁后重设变量 | 未执行：属 T019 | — |
| CFG-08 | 越界 `raw_path` 与根外符号链接 | 未执行：属 T019 | — |

## 固定样本

`tests/fixtures/` 全部为虚构内容，链接只用 `example.invalid`，不用于真实请求：

- 详情页（标题、元数据、正文、列表、表格、成功/失败附件链接）与表格页；
- 附件样本：`notice.csv`、文本层 `notice.pdf`；
- OCR 样本：`ocr/scanned_notice.png` 与仅含图像的 `ocr/scanned_notice.pdf`（无文本层）；
- 失败样本 `manifests/failed_records.jsonl`（字段对齐 failure.schema.json）；
- 版本样本 `version_v1.html` / `version_v2.html`（同文档不同条款文本）。

2026-09-11 复核：`tools/make_fixture_binaries.py` 重跑后五个二进制夹具 SHA-256 与重建前逐字节一致
（确定性声明成立），且 `uv run --locked --env-file .env` 的变量注入与 ./data 解析符合 CFG-02/CFG-03，
见 [logs/t003-repro-checks.txt](logs/t003-repro-checks.txt)。

## 未完成范围

- T004 的来源注册、配置校验与访问边界未实现，CFG-01—CFG-05 的 settings 部分已通过，但整任务未完成。
- CFG-06—CFG-08 与真实站点验收仍属后续任务；acceptance.md 的 37 项 AT 用例保持 NOT RUN。
- 业务待决 Q 项未被本记录关闭；`.env` 为本地文件，不随仓库交付。
