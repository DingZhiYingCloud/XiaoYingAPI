---
name: kali-trae-connect
description: 把局域网里的 Kali Linux（含 VMware/VirtualBox 虚拟机）接入 Trae Remote SSH，或让 AI 直接通过 ssh 执行 Kali 命令。当用户要连接 Kali、给 Kali 配静态 IP、开 SSH、配免密 sudo 时使用；不适用于普通 Linux 服务器的日常运维。
---

# Kali 接入 Trae

目标：让 Trae（Remote SSH）或 AI 能在 Kali 上执行命令。两条路线，先选一条：

- **A. Trae Remote SSH（推荐）**：连上后 AI 的终端、文件读写**全部在 Kali 上下文**里执行。
- **B. 仅 SSH 桥接（最省事）**：什么都不装，AI 用 `ssh <别名> "命令"` 执行（够用）。

## 目录内容

| 文件 | 用途 |
| --- | --- |
| `scripts/kali_ssh_setup.sh` | **在 Kali 上跑**：开 SSH（持久化）；可选固定静态 IP |
| `scripts/win_connect_kali.ps1` | **在 Trae 所在机器上跑**：写 `~/.ssh/config` 别名 + 装公钥 + 免密验证 |
| `references/troubleshooting.md` | 排障与全部踩坑（连不上、慢、卡住等） |

## 步骤 0：判断虚拟机网络模式（决定能否直连）

| 模式 | 能否从 Trae 机器直连 Kali | 处理 |
| --- | --- | --- |
| 桥接 Bridged | 能 | 直接用 Kali 的局域网 IP |
| NAT | 不能 | ①改成桥接（推荐）；②或在虚拟机软件里做端口转发（宿主端口 → Kali:22），然后连「宿主 IP:端口」 |
| 仅主机 Host-only | 不能 | 改成桥接 |

桥接后 Kali 应拿到与 Trae 机器**同网段**的 IP。
VMware：虚拟机设置 → 网络适配器 → 「桥接模式：直接连接物理网络」。若桥接后拿不到 IP，去「编辑 → 虚拟网络编辑器 → VMnet0」，把「桥接到」选成**正在上网的那张物理网卡**（有线选以太网、WiFi 选无线网卡，别选 VPN/虚拟网卡）。
注意：路由器若开了「AP 隔离」，跨设备会不通。

## 步骤 1：在 Kali 上准备（开 SSH + 可选静态 IP）

把 `scripts/kali_ssh_setup.sh` 放到 Kali 上执行：

```bash
# 只开 SSH（默认，幂等）
bash kali_ssh_setup.sh

# 顺带固定 IP（带安全网：120 秒内网关不通就自动改回 DHCP，不会把自己配失联）
bash kali_ssh_setup.sh --static-ip 192.168.1.240/24 --gateway 192.168.1.1 --dns 192.168.1.1

# 想改回 DHCP
bash kali_ssh_setup.sh --revert
```

脚本会打印 Kali 当前 IP —— 记下来，下一步要用。
（提示：静态 IP 建议选在路由器 DHCP 池**之外**的地址，避免日后被分给别的设备；最稳妥是在路由器上做 DHCP 静态绑定。）

## 步骤 2：在 Trae 所在机器上准备（写别名 + 装公钥）

```powershell
# 先预览，不改任何东西
powershell -ExecutionPolicy Bypass -File win_connect_kali.ps1 -Target <Kali的IP> -User <Kali用户名> -DryRun

# 真正执行（会提示输入一次 Kali 密码，用于把公钥装上去）
powershell -ExecutionPolicy Bypass -File win_connect_kali.ps1 -Target <Kali的IP> -User <Kali用户名>
# NAT + 端口转发的场景：-Target 填宿主机 IP，外加 -Port <转发端口>
```

脚本做的事：确认 22 端口可达 → 生成或复用 ed25519 密钥 → 把 `Host kali` 写进 `~/.ssh/config`（**别名强制小写**）→ 把公钥装到 Kali → 免密验证。
失败时按它的提示走，或查 `references/troubleshooting.md`。

## 步骤 3：在 Trae 里连接

1. `Ctrl+Shift+P` → **`Remote-SSH: Connect to Host`** → 选 `kali`
2. 首次连接会让选远端平台 → 选 **Linux**
3. 首次连接 Trae 会往 Kali 下载约 **300MB** 服务端包并解压约 **1.3GB**，**要等 1~2 分钟**，不是卡死
4. 连上后左下角显示 `SSH: kali`，此时 AI 的命令都在 Kali 里跑

## 步骤 4（可选）：给 Kali 配 sudo 免密

需要 AI 免密码执行 root 命令时，在 Kali 上：

```bash
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$USER > /dev/null
sudo chmod 440 /etc/sudoers.d/$USER
sudo visudo -cf /etc/sudoers.d/$USER     # 必须显示「解析正确」，否则别用
```

⚠️ 这一步会让「免密登录 + 免密提权」叠加：**谁拿到本机私钥就等于拿到 Kali 的 root**。请保护好私钥（别分发、可给私钥加口令）。

## 连上之后怎么用

- 路线 A：Remote SSH 会话里，AI 直接执行命令 / 读写远端文件。
- 路线 B：让 AI 执行 `ssh kali "命令"`（命令放**单引号**里）。

## 硬性约束（务必遵守）

1. **Trae 的 SSH 别名一律小写**（如 `kali`）：含大写主机名会导致 Trae 连接超时。
2. **从 Windows 发 ssh 远程命令时，命令里不要带引号**：Windows OpenSSH 会吞掉引号导致远端报语法错；需要复杂命令就写成脚本文件传，或先 base64 编码再解码执行。
3. 远端 shell 若是 **zsh**：`echo ===` 会被当成特殊语法报 `= not found`，分隔线用 `---`。
4. 静态 IP 只选 DHCP 池外的地址；脚本自带 120 秒自动回退，网关不通会自愈。
5. 首次连接慢是正常现象（见步骤 3 第 3 点）。

## 验证清单

- [ ] Kali：`systemctl is-active ssh` 为 `active`，且 `ss -lntp | grep :22` 有监听
- [ ] Trae 机器：`Test-NetConnection <Kali的IP> -Port 22` 为 `True`
- [ ] Trae 机器：`ssh kali "hostname; whoami"` 免密返回
- [ ] Trae：左下角显示 `SSH: kali`
- [ ] AI 能跑通一条 Kali 命令（如 `ssh kali "nmap --version"`）

## 回滚

- ssh 别名：脚本会先备份 `~/.ssh/config` 为 `config.bak-<时间戳>`，覆盖回去即可。
- 静态 IP：`bash kali_ssh_setup.sh --revert`。
- sudo 免密：`sudo rm /etc/sudoers.d/<用户名>`。
- Trae 服务端：Kali 上删掉 `~/.trae-cn-server`（下次连接会重新下载）。
