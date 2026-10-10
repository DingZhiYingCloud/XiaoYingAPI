# 排障与踩坑（Kali ↔ Trae）

按症状查。每条都给「怎么判定 / 怎么修」。

## 1. 从 Trae 机器连不上 Kali（ping 通但 22 连不上，或干脆 ping 不通）

按顺序排查：

| 检查 | 命令（在 Trae 机器上执行） | 结论 |
| --- | --- | --- |
| 端口通不通 | `Test-NetConnection <KaliIP> -Port 22` | `TcpTestSucceeded: True` 才算通 |
| 网段对不对 | `Get-NetIPAddress -AddressFamily IPv4 \| ? {$_.IPAddress -notlike '127.*'}` | 若与 Kali **不同网段**，说明是 NAT/仅主机 |
| Kali 是否开了 SSH | 在 Kali：`systemctl status ssh` | 没开就 `sudo systemctl enable --now ssh` |

常见原因：
- **虚拟机是 NAT/仅主机**：Trae 机器根本路由不到 Kali。→ 改「桥接」（见 SKILL.md 步骤 0），或做端口转发后连「宿主 IP:转发端口」。
- **桥接桥错网卡**：VMware「虚拟网络编辑器 → VMnet0 → 桥接到」选成了 VPN/虚拟网卡。→ 选**正在上网的那张物理网卡**。
- **拿不到 IP**：桥接后 Kali 里 `ip a` 没有 192.168.x.x。→ 检查上面的桥接网卡；或 Kali 里 `sudo dhclient -v` 手动要一次地址。
- **路由器 AP 隔离**：同一 WiFi 下设备互访被拦（表现为 ping 不通）。→ 关掉 AP 隔离，或把 Kali 所在电脑改接有线。
- **防火墙**：Kali 若开了 ufw，`sudo ufw allow 22`。

## 2. Trae 一直显示「Downloading and installing remote server...」很久

**这是正常的首次开销，不是卡死**。Trae 会往 Kali 下载约 **300MB** 服务端包（`vscode-server.<版本>.tar.xz`），再解包约 **1.3GB**。
- 实测 8 核虚拟机约 **84 秒**（`install_remote_server` 步骤）。
- 可用客户端日志确认进度：`%APPDATA%\Trae CN\logs\<时间戳>\window*\exthost\cloudide.icube-remote-ssh\Remote - SSH(TRAE).log`，搜 `install_remote_server` / `completed successfully`。
- Kali 侧可看下载与解包：`ls -la ~/.trae-cn-server/bin/*/`，`pgrep -a tar`。
- **只有第一次慢**；服务端装好后，之后连接通常几秒。若每次重连都重下 300MB，多半是 Trae 客户端升级导致服务端版本变了。

## 3. Trae 连接超时（明明 SSH 能连）

- **主机名含大写**：`~/.ssh/config` 里 `Host` 名必须全小写（Trae 已知 bug）。把 `Host Kali` 改成 `Host kali`。
- 别名冲突/配置没生效：`ssh -G kali | head` 看实际解析出的 HostName/User/Port。

## 4. Kali 上 SSH 默认是关的

Kali 预装了 `openssh-server` 但**服务默认不启动**：
```bash
sudo systemctl enable --now ssh     # 开机自启 + 立即启动
```

## 5. ⚠️ Windows 的 ssh 会吞掉远程命令里的引号（最容易踩）

从 Windows 执行 `ssh host "带引号的命令"` 时，**引号可能被剥掉**，远端报 `syntax error near unexpected token` 之类。

**规则：远程命令里不要出现引号**，改用别的写法：

```powershell
# ✗ 可能被吞引号
ssh kali "find /tmp -name 'a b' -printf '%s %p\n'"

# ✓ 不带引号（用无空格、无特殊字符的写法）
ssh kali "ls -la /tmp"

# ✓ 复杂命令：写到文件再执行
ssh kali "cat /tmp/x.sh | bash"

# ✓ 或者 base64 传（彻底避开引号）
$b = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cmd))
ssh kali "echo $b | base64 -d | bash"
```

## 6. 远端是 zsh：`echo ===` 会报错

zsh 把 `=word` 当特殊展开，`echo ===` 会报 `zsh:1: == not found`。
- 分隔线用 `---`，不要用 `===`。
- 需要 root 时 zsh 下用 `sudo -n`（已配免密时）。

## 7. 配静态 IP 后失联

- 脚本自带**安全网**：应用后 120 秒内网关不可达，会自动 `ipv4.method auto` 改回 DHCP。
- 若真失联：到虚拟机**控制台**执行 `sudo nmcli con mod "<连接名>" ipv4.method auto && sudo nmcli con up "<连接名>"`，或直接 `bash kali_ssh_setup.sh --revert`。
- 静态地址要**选在路由器 DHCP 池之外**，否则日后可能被分给别的设备造成冲突。

## 8. 行尾与编码（同步脚本时注意）

- 在 Windows 上编辑的 `.sh`，传到 Linux 前要转成 **LF**：`sed -i 's/\r$//' xxx.sh`。
- 含中文的脚本/配置用 **UTF-8 无 BOM**；别让 PowerShell 的 `Set-Content -Encoding utf8` 写入 BOM（PS 5.1 会写 BOM）。用 `[IO.File]::WriteAllText()` 更稳。
- 复制到 Kali 前可用 `bash -n xxx.sh` 先做语法检查。

## 9. 常用排障命令速查

**在 Trae 机器上：**
```powershell
Test-NetConnection <KaliIP> -Port 22          # 端口可达性
ssh -v kali "echo ok"                         # 带调试的登录（看认证过程）
ssh -o BatchMode=yes kali "echo ok"           # 只测免密是否生效
ssh -G kali                                   # 查看别名解析结果
```

**在 Kali 上：**
```bash
systemctl is-active ssh; ss -lntp | grep :22  # SSH 状态
ip -4 -o addr show scope global               # 当前 IP
nmcli device status                           # 网卡/连接状态
nmcli -t -f UUID,NAME,DEVICE con show         # 连接清单（拿 UUID 用）
ping -c2 <网关>                                # 网关可达性
lastb | head                                  # 近期失败登录（看有没有爆破）
journalctl -u ssh -n 50 --no-pager            # sshd 日志
```

**在 Kali 上查 Trae 服务端：**
```bash
ls -la ~/.trae-cn-server/                     # 服务端安装目录
ls -la ~/.trae-cn-server/manager-logs/        # 每次连接的日志
ps -eo pid,args | grep -F .trae-cn-server     # 服务端进程是否在跑
```
