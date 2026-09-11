# NEXT-08 随包契约与源码外安装（2026-09-11）

本记录对应 [阶段三计划](../stage-three.md) NEXT-08（GAP-04），关联 T003/T019/T027。
它证明分发态命令不再依赖源码树，不改变 T019/T027 的正式验收状态。

## 变更

- 运行契约随包交付：`src/crawler/contracts/*.schema.json`（6 个），与
  `specs/001-public-knowledge-collection/contracts/` 的规格契约**逐字节一致**。
- 运行读取改为标准库 `importlib.resources` 的包资源路径：
  `crawler.validate.schema.load_contract` / `contracts_dir` 不再用 `detect_project_root()` 找源码树，
  也不再猜测或回退到开发机器路径；资源缺失或 JSON 损坏时抛 `SchemaConfigError`，CLI 以退出码 2 明确失败。
- 同步与漂移校验：`tools/sync_contracts.py`（默认写入随包副本，`--check` 只校验并在漂移时退出码 1）。
  一致性测试 `tests/test_contract_resources.py` 覆盖「规格 → 随包」逐字节一致、规格目录新增 schema 未同步失败、
  源码外目录加载、资源缺失/损坏/未知契约的失败语义。
- 构建产物：wheel 自带 `crawler/contracts/*.schema.json` 与 `crawler/config/sources.yaml`。

## 验证

命令与原始输出：[logs/next08-installed-wheel.txt](logs/next08-installed-wheel.txt)

1. `uv build`（构建后端 hatchling 来自登记清华镜像）→ wheel/sdist 构建成功；
   wheel 内容列出 6 个契约资源与 `entry_points.txt`。
2. `uv venv --clear --python 3.9 /tmp/next08-venv` + `uv pip install <wheel>`：
   独立 venv 普通安装，33 个依赖来自登记镜像（无官方 PyPI 回退），`crawl` 入口可用。
3. 源码外执行（`cwd=/tmp/next08-run`，解释器 `/tmp/next08-venv/bin/python`，
   包位置 `site-packages/crawler`，数据根为离线交付样本 `data/` 的副本、显式绝对路径）：
   `crawl sources` 退出码 0；`crawl check` 退出码 0（manifest=10、documents=10、blocks=489、
   schema 通过、documents/blocks 追溯 100%）。
4. 负向检查：临时移出 `site-packages/crawler/contracts` 后，`sources` 与 `check` 均以退出码 2
   报「随包契约文件缺失：crawler/contracts/…」；恢复后 `check` 再次退出码 0。
5. 一致性：`python tools/sync_contracts.py --check` → `契约一致：6 个文件`；
   阶段候选全量回归 345 passed，见 [阶段三完整回归](logs/stage-three-full-pytest.txt)。

## 限制

- “普通安装”验证用独立 venv + 本地 wheel（含依赖来自登记镜像）；未在无网络机器上复验。
- 正式启用来源、调度与运维交接（Q12/Q13、Q14）仍待业务决定；
  T019/T027 的正式验收与 T012 的 LibreOffice 转换属其他子项，不因本记录改变状态。
