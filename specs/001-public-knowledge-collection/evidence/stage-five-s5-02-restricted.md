# 阶段五 S5-02：受限来源分因处理证据（2026-09-13）

范围：`stage-five.md` S5-02（受限来源分因处理，对应 T004/T026）。本文件只记录**诊断与分因**，
不把任何来源改为“可采集”，不用 `verify=False`、`curl -k`、换 UA 或私有端点绕过限制。
逐站状态见 [T026 十八来源状态](t026-eighteen-sources.md)；Q12 需要的输入见
[decision-requests.md](../decision-requests.md)。

本轮取证由 Agent 按 DEV-012 登记后执行，登记/结果原始输出：

- [第 49 轮 IN-03 别名核实](logs/stage-five-round49-in03-alias.txt)（2 个 HTTP 请求）
- [第 50 轮 TLS 环境诊断](logs/stage-five-round50-tls-diagnostics.txt)（0 个页面请求 + 2 次 TLS 握手）
- [第 51 轮 IN-03 主体域核实](logs/stage-five-round51-in03-primary.txt)（1 个 HTTP 请求）
- [WSL 环境诊断原始输出](logs/stage-five-s5-02-wsl-diagnostics.txt)

## 1. 本机环境先被排除（WSL）

| 检查项 | 结果 | 结论 |
| --- | --- | --- |
| 时钟 | `date` 与 `date -u` 相差正好 8 小时且与实际日期一致；`/etc/localtime` → `Asia/Shanghai` | 时钟正确，不是证书时间校验失败的原因（`timedatectl` 报 bus 错误是 WSL 无 systemd bus，不是时钟故障） |
| 代理环境变量 | 用 `env` 过滤 proxy、git/apt 代理配置均为空 | 失败不来自 WSL 内显式代理配置 |
| CA 信任库 | `/etc/ssl/certs` 244 项、`ca-certificates.crt` 182 KB 存在；Python ssl 指向同一目录 | 标准信任库在位且未缺失 |
| 工具链 | curl 8.5.0（OpenSSL 3.0.13）；Python 3.9.25（OpenSSL 3.5.4）；LibreOffice 24.2.7.2 可用 | 工具链本身可完成 TLS 与文档转换 |
| DNS/路由 | `/etc/resolv.conf` nameserver `10.255.255.254`；默认路由 `172.26.224.1`（WSL 网关） | 解析全部经 Windows 侧转发 |

对照实验：`openssl s_client` 到 `www.gov.cn:443` 得到完整 CFCA 链（`*.www.gov.cn` ←
`CFCA OV OCA` ← `CFCA EV ROOT`，verify 0）；同一命令到 `ladakh.gov.in:443` 显示
`CONNECTED` 后 **`no peer certificate available`**（连接被切断，服务端证书根本没到达客户端）。

## 2. IN-04/07/08/09：TLS 失败的本地根因（代理/分流，非 WSL 信任库）

第 49 轮 DNS 解析给出直接线索：

```
$ getent hosts indiacode.gov.in www.indiacode.gov.in www.indiacode.nic.in
198.18.0.122 indiacode.gov.in
198.18.0.123 www.indiacode.gov.in
198.18.0.124 www.indiacode.nic.in
```

`198.18.0.0/15` 是 RFC 2544 保留段，也是 Windows 侧 Clash/Mihomo 等代理客户端的典型
**fake-IP/TUN 分配范围**；即 WSL 的 DNS 已被 Windows 侧代理接管，流量按分流规则进出。

据此重新解释第 37 轮记录（当时写作“本机信任库无法验证证书链”）：

| 来源 | 第 37 轮现象 | 第 50 轮复核 | 新的分因结论 |
| --- | --- | --- | --- |
| IN-04 egazette.gov.in | `SSLZeroReturnError`；curl exit=60/verify=20 | 同类连接被切断（ladakh 对照） | 本地代理链路在 TLS 阶段切断，站点证书未送达；**不是** WSL 缺 CA |
| IN-07 censusindia.gov.in | `CERTIFICATE_VERIFY_FAILED`；curl exit=35/verify=1 | 同上 | 同上（fake-IP 下得到的是代理侧证书/无证书） |
| IN-08 ladakh.gov.in | `SSLZeroReturnError` | `s_client`：CONNECTED → no peer certificate | 同上（本轮直接复现） |
| IN-09 culture.sikkim.gov.in | `SSLZeroReturnError` | 同上 | 同上 |

结论：IN-04/07/08/09 的失败**不能**作为“站点禁止访问”的证据，也没有证据说明 WSL 证书库有问题；
当前可行动的方向是本地代理分流规则。需要用户/管理员执行的具体步骤：

1. 在 Windows 侧代理客户端（Clash/Mihomo/v2rayN 等，凡使用 fake-IP/DNS 接管者）为以下域名
   增加“直连/bypass”或修正分流规则（含 `www.` 与 apex）：
   `egazette.gov.in`、`censusindia.gov.in`、`ladakh.gov.in`、`culture.sikkim.gov.in`、
   `indiacode.gov.in`、`indiacode.nic.in`（后者用于核对别名 robots）。
2. 保持证书校验开启；如果贵司网络对上述域名使用组织级代理，请提供该代理的 CA 说明
   （安装方式+原因），不采用跳过校验的临时方案。
3. 调整后按一次性、低预算复核（每来源 ≤2 个请求，只取 robots.txt）并记录，不借此扩大采集。

## 3. IN-03：域名别名归属已核实，但新域 robots 不可用（维持受限）

| 轮次 | 事实 | 证据 |
| --- | --- | --- |
| 51 | 主体域 `https://www.indiacode.nic.in/`（2009 B）是**官方迁移公告页**：`<title>India Code - Site Migration</title>`、`meta refresh 3;url=https://indiacode.gov.in` + 脚本跳转；页面自述“The India Code website has been migrated from https://www.indiacode.nic.in to https://indiacode.gov.in”；除迁移目标外无其他链接 | [round51](logs/stage-five-round51-in03-primary.txt) |
| 49 | 新域根页响应 200、2338 B，是 Angular SPA 壳（`<ds-app>` + 构建脚本），无静态链接 | [round49](logs/stage-five-round49-in03-alias.txt) |
| 49 | 新域 `robots.txt` 返回 **HTTP 502**（nginx，150 B） | 同上 |

判定：别名归属已由站点自身公告确认（不再是“归属待定”）；但新域 robots.txt 5xx，按
`src/crawler/fetch/robots.py::rules_for_unavailable`（5xx → 保守拒绝）**不启用新域**，
也不把 `indiacode.gov.in` 加入 `allowed_domains`。旧域虽 robots 404（无规则），但已无内容。
需要的输入（见 Q12）：站点侧 robots 恢复可用并允许采集，或站点许可/公开接口；若 502 由
本地代理链路引入，先按第 2 节步骤调整后再复核。

## 4. CN-05/06/07：robots HTTP 508（无新线索，复用第 37 轮证据）

第 37 轮以每来源 1 次运行、≤2 请求复核，`www.xizang.gov.cn`、`wsb.xizang.gov.cn`、
`mw.xizang.gov.cn` 的 robots.txt 均稳定返回 508，管线按不可用保守拒绝、未请求页面。
508 状态码本身不能认定为唯一原因或永久禁止，本轮无新的外部线索，不重复探测。
需要的输入：站点/网络侧说明或允许的访问方式（Q12）。

## 5. CN-03：robots `Disallow /`（规则拒绝，不变）

2026-09-11 核验：`flk.npc.gov.cn/robots.txt` 1 组 4 规则，命中 `Disallow /`，只取 robots.txt
即停。属明确规则拒绝，需要站点许可或公开接口，不反复探测（详见 T026 表）。

## 6. 本轮请求账（DEV-012 口径）

| 轮次 | HTTP 页面/robots 请求 | TLS 握手 | 说明 |
| --- | --- | --- | --- |
| 49 | 2 | 0 | 别名胜任 robots + 根页各 1 次（定性取证） |
| 50 | 0 | 2 | ladakh 失败复现 + gov.cn 对照；只读本机网络配置 |
| 51 | 1 | 0 | 主体域根页 1 次 |
| 合计 | **3** | 2 | 未发生登录/验证码/拒绝绕过；未请求别名域页面（除第 49 轮的 1 次定性取证） |

## 7. 复跑命令（受限来源复核，先按 DEV-012 登记）

```bash
# 每来源 ≤2 请求，只取 robots.txt（示例 IN-08）
UV_CACHE_DIR=/tmp/uv-cache uv run --locked --no-python-downloads python -m crawler.cli collect \
  --config src/crawler/config/sources.yaml --source IN-08 \
  --max-requests 2 --deadline-seconds 30
```

```bash
# 第 49/50/51 轮的等价手工诊断（需网络，单次请求、不重试）
curl -sS -i --max-time 20 https://indiacode.gov.in/robots.txt
curl -L --max-time 30 -A Mozilla/5.0 -sS https://www.indiacode.nic.in/ -o /tmp/in03_primary_root.html
openssl s_client -connect ladakh.gov.in:443 -servername ladakh.gov.in -showcerts </dev/null
```
