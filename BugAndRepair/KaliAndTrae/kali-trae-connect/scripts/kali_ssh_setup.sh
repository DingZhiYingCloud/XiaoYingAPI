#!/usr/bin/env bash
# Kali 侧一键准备：开启并持久化 SSH；可选把当前网卡改成静态 IP。
#
# 设计要点：
#   1. 幂等：重复执行不会重复添加任何东西，可放心重跑。
#   2. 静态 IP 带「安全网」：应用后若网关不可达，120 秒后自动改回 DHCP，
#      避免配错网段后彻底失联（虚拟机虽有控制台可救，能自愈更省事）。
#   3. 需要 root：脚本会自己 `sudo` 自己，只在第一次提示输一次密码。
#
# 该脚本在 Kali 上运行（终端或 `ssh <用户>@<IP> 'sudo bash -s' < kali_ssh_setup.sh`）。
set -euo pipefail

usage() {
  cat <<'EOF'
用法: bash kali_ssh_setup.sh [选项]

  (无选项)            只开启并持久化 SSH（systemd enable --now）
  --static-ip <CIDR>  固定 IPv4，例如 192.168.1.240/24
  --gateway <IP>      网关，例如 192.168.1.1（不填则取当前默认网关）
  --dns <IP>          DNS（不填则用网关）
  --revert            把当前网卡改回 DHCP
  -h, --help          显示本帮助

示例:
  bash kali_ssh_setup.sh
  bash kali_ssh_setup.sh --static-ip 192.168.1.240/24 --gateway 192.168.1.1 --dns 192.168.1.1
  bash kali_ssh_setup.sh --revert
EOF
}

STATIC_IP=""; GATEWAY=""; DNS=""; REVERT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --static-ip) STATIC_IP="${2:-}"; shift 2 ;;
    --gateway)   GATEWAY="${2:-}";   shift 2 ;;
    --dns)       DNS="${2:-}";       shift 2 ;;
    --revert)    REVERT=1;           shift ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "未知参数：$1" >&2; usage; exit 2 ;;
  esac
done

# —— 需要 root：以 sudo 重新执行自己（保留原参数）——
if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi
LOGIN_USER="${SUDO_USER:-$(id -un)}"

# —— 找到承载出网的活动连接（NetworkManager 连接名）——
CON="$(nmcli -t -f NAME,DEVICE connection show --active | awk -F: '$2 != "lo" {print $1; exit}')"
if [ -z "${CON}" ]; then
  echo "错误：找不到活动的 NetworkManager 连接，请确认网卡已连上。" >&2
  exit 1
fi

echo "==> 使用连接：$CON"

# —— 1) 开启并持久化 SSH（幂等）——
systemctl enable --now ssh
echo "==> SSH 服务：$(systemctl is-active ssh)（已设为开机自启）"

# —— 2) 改回 DHCP（可选）——
if [ "$REVERT" -eq 1 ]; then
  rm -f /tmp/kali_staticip.cancel
  nmcli con mod "$CON" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
  nmcli con up "$CON"
  sleep 2
  echo "==> 已改回 DHCP"
fi

# —— 3) 固定静态 IP（可选，带自动回退安全网）——
if [ -n "$STATIC_IP" ]; then
  if [ -z "$GATEWAY" ]; then
    GATEWAY="$(ip route | awk '/^default/{print $3; exit}')"
  fi
  if [ -z "$GATEWAY" ]; then
    echo "错误：拿不到默认网关，请用 --gateway 指定。" >&2
    exit 1
  fi
  [ -n "$DNS" ] || DNS="$GATEWAY"

  CANCEL=/tmp/kali_staticip.cancel
  rm -f "$CANCEL"
  # 把「回退脚本」写到临时文件再 setsid 后台跑，避免嵌套引号出错
  cat > /tmp/kali_staticip_revert.sh <<EOF
#!/usr/bin/env bash
sleep 120
[ -f $CANCEL ] && exit 0
nmcli con mod "$CON" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
nmcli con up "$CON"
EOF
  chmod +x /tmp/kali_staticip_revert.sh
  setsid /tmp/kali_staticip_revert.sh </dev/null >/tmp/kali_staticip_revert.log 2>&1 &

  echo "==> 应用静态 IP：$STATIC_IP（网关 $GATEWAY / DNS $DNS）"
  nmcli con mod "$CON" ipv4.method manual ipv4.addresses "$STATIC_IP" ipv4.gateway "$GATEWAY" ipv4.dns "$DNS"
  nmcli con up "$CON"
  sleep 3

  if ping -c1 -W3 "$GATEWAY" >/dev/null 2>&1; then
    touch "$CANCEL"          # 网关可达 → 取消自动回退，保留静态 IP
    echo "==> 静态 IP 生效且网关可达，已取消自动回退（长期保留）"
  else
    echo "警告：网关 $GATEWAY 不可达，120 秒后将自动回退 DHCP。" >&2
    exit 1
  fi
fi

# —— 4) 输出结果与下一步 ——
echo
echo "--- 当前 IPv4 ---"
ip -4 -o addr show scope global | awk '{print "  " $2 "  " $4}'
echo "--- SSH 监听 ---"
ss -lntp 2>/dev/null | grep -F ':22 ' || echo "  （未见 22 端口监听，请检查 ssh 服务）"
echo
echo "--- 下一步：在 Trae 所在的机器上执行 ---"
echo "  powershell -ExecutionPolicy Bypass -File win_connect_kali.ps1 -Target <上面的IP> -User $LOGIN_USER"
