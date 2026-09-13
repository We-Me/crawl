# NEXT-04：WSL 组件就绪记录

记录日期：2026-09-13。来源：用户提供的目标 WSL 终端输出；本轮 Agent 未在该 WSL 中重跑命令。项目位置为用户报告的 ~/workspaces/crawl，仅为证据位置，不是可移植路径契约。

```text
$ command -v soffice
/usr/bin/soffice
$ soffice --version
LibreOffice 24.2.7.2 420(Build:2)
$ uv run --locked --no-python-downloads python -c "from crawler.parser.legacy_parser import find_soffice; print(find_soffice())"
/usr/bin/soffice
```

用户明确确认安装成功；以上将消息中 Markdown 转义的下划线恢复为实际 Python 标识符。结论：目标 WSL 中组件可用且现有项目解析器可发现，历史“缺组件、待安装”阻塞解除。NEXT-04 状态为 READY_FOR_VALIDATION，真实 DOC/XLS 成功转换、结构完整性与原件追溯仍未验证，T012 不自动勾选，第四阶段整体仍未完成。

无需重新安装或再次请求安装授权；下一 Agent 在同一 WSL 项目复用已选 Python、uv 和锁文件，开展真实 OLE2 DOC/XLS 各一份的转换与管线验证。其他主机不能直接继承此环境结论。旧环境日志作为历史记录保留，最新状态以本证据为准。
