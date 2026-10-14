#!/usr/bin/env bash
# ============================================================================
# pack-agent.sh —— 把「开发版」明文 ai-agent 打包成「生产版」（加固）
#
# 用法：
#   bash tools/pack-agent.sh ai-agent                          # 内嵌口令（旧模式）
#   bash tools/pack-agent.sh ai-agent --online --brain https://大脑域名/ai-brain
#                                                              # ★ 在线取口令（推荐）
#   bash tools/pack-agent.sh ai-agent -o dist/a --key 'pass'
#
#   1) 瘦身：删掉注释与空行（注释不进生产版）
#   2) 压缩：gzip 后再加密，解出来也不是能直接读的脚本
#   3) 加密：AES-256-CBC + PBKDF2（默认 60 万次迭代，随机 salt）
#   4) 口令不整存：--online 时**文件里根本不存口令**，运行时凭「注册口令」向大脑
#      POST /agent/key 换（换到后缓存在 ~/.ai-agent/agent.conf 供 systemd 启动复用）
#   5) 密文打散：base64 密文切成 4 段、各藏进随机变量名，运行时再拼回
#   6) 去特征：命令名/算法名在运行时拼装（文件里搜不到 openssl/base64/gzip/
#             aes-256-cbc/pbkdf2 等字样），变量名每次随机，报错信息通用化
#   7) 轮换友好：大脑可同时下发「当前口令 + 过渡旧口令」；密文先按当前口令校验，
#             不匹配再退旧口令 —— 所以轮换后还没升级的老文件仍能启动，不会整片失联
#
# 边界（说到做到）：不做反调试 / 沙箱检测 / 伪装进程 / 隐藏 /proc。
# 老实说：--online 能挡住"拷走文件"，但本机拿到 root 的人仍可从运行中的进程取到明文。
# ============================================================================
set -uo pipefail

SRC=""; OUT=""; KEY=""; ITER=600000; ONLINE=0; BRAIN=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--out) OUT=${2:-}; shift 2 ;;
        --key)    KEY=${2:-}; shift 2 ;;
        --iter)   ITER=${2:-}; shift 2 ;;
        --online) ONLINE=1; shift ;;
        --brain)  BRAIN=${2:-}; shift 2 ;;
        -h|--help) awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
        *) SRC=$1; shift ;;
    esac
done
if [ -z "$SRC" ] || [ ! -f "$SRC" ]; then
    echo "用法：bash pack-agent.sh <明文ai-agent> [-o 输出] [--key 口令] [--online --brain https://域名/路径]"
    exit 1
fi
for c in openssl base64 gzip sed od tr mktemp; do
    command -v "$c" >/dev/null 2>&1 || { echo "需要 $c"; exit 1; }
done

TOOLS=$(cd "$(dirname "$0")" && pwd)
[ -n "$OUT" ] || OUT="$TOOLS/dist/ai-agent"
mkdir -p "$(dirname "$OUT")"

# 口令：
#   --online：使用大脑上的 PACK_KEY（这里从 brain.conf 读，方便本地打包；也可 --key 指定）
#   否则    ：优先 --key；其次/生成 tools/pack.key（600）
KEYFILE="$TOOLS/pack.key"
if [ "$ONLINE" = "1" ]; then
    [ -n "$BRAIN" ] || { echo "✗ --online 必须给 --brain（如 https://大脑域名/ai-brain）"; exit 1; }
    if [ -z "$KEY" ]; then
        KEY=$(python3 - "$TOOLS/../../brainlib/conf.py" <<'PY' 2>/dev/null
import os, sys
p = os.path.abspath(sys.argv[1])
# 从大脑的 brain.conf 里取 PACK_KEY（只在本机打包时用；不写进产出）
home = os.environ.get('BRAIN_HOME') or os.path.join(os.path.expanduser('~'), '.ai-brain')
try:
    for line in open(os.path.join(home, 'brain.conf'), encoding='utf-8', errors='replace'):
        if line.startswith('PACK_KEY='):
            print(line.split('=', 1)[1].strip()); break
except OSError:
    pass
PY
)
        [ -n "$KEY" ] || { echo "✗ 读不到大脑的 PACK_KEY：请先 brain init，或用 --key 指定"; exit 1; }
    fi
elif [ -z "$KEY" ]; then
    if [ -f "$KEYFILE" ]; then KEY=$(cat "$KEYFILE"); else
        KEY=$(openssl rand -base64 32 | tr -d '\n' | cut -c1-36)
        ( umask 077; printf '%s' "$KEY" > "$KEYFILE" )
        echo "已生成打包口令 → $KEYFILE（请保管好）"
    fi
fi

# ---------- 1) 瘦身：删注释与空行 ----------
tmp=$(mktemp) || exit 1
trap 'rm -f "$tmp"' EXIT
sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$SRC" > "$tmp"
if ! bash -n "$tmp"; then echo "✗ 瘦身后语法不过，已放弃（源文件有问题？）"; exit 1; fi

# ---------- 2) 压缩 + 3) 加密（密文去掉换行，便于打散） ----------
blob=$(gzip -c "$tmp" | openssl enc -aes-256-cbc -pbkdf2 -iter "$ITER" -salt -pass pass:"$KEY" | base64 | tr -d '\n')
MAC=$(printf '%s' "$blob" | openssl dgst -sha256 -hmac "$KEY" | awk '{print $NF}')

# ---------- 4) 口令拆 3 段（仅内嵌模式用） ----------
n=${#KEY}
a=$((n / 3)); k1=${KEY:0:a}; k2=${KEY:a:a}; k3=${KEY:$((a + a))}
S1=$(printf '%s' "$k1" | base64 | tr -d '\n')
S2=$(printf '%s' "$k2" | tr 'a-zA-Z' 'n-za-mN-ZA-M' | base64 | tr -d '\n')
S3=$(printf '%s' "$k3" | tr 'a-zA-Z' 'n-za-mN-ZA-M' | base64 | tr -d '\n')

# ---------- 5) 密文切 4 段 ----------
L=${#blob}; q=$(( (L + 3) / 4 ))
C1=${blob:0:q}; C2=${blob:q:q}; C3=${blob:$((2 * q)):q}; C4=${blob:$((3 * q))}

# ---------- 6) 随机变量名 + 运行时拼装命令名 ----------
rn() { printf '_%s' "$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"; }
a1=$(rn); a2=$(rn); b1=$(rn); b2=$(rn); c1=$(rn); c2=$(rn)
d1=$(rn); d2=$(rn); e1=$(rn); e2=$(rn); f1=$(rn); f2=$(rn)
nB=$(rn); nO=$(rn); nZ=$(rn); nR=$(rn); nC=$(rn); nP=$(rn); nI=$(rn)
h1=$(rn); h2=$(rn); h3=$(rn); h4=$(rn); DEC=$(rn)
y1=$(rn); y2=$(rn); y3=$(rn); r1=$(rn); r2=$(rn); r3=$(rn)
DECV=$(openssl rand -base64 24 | tr -d '\n')

COMMON=$(cat <<'STUB'
#!/usr/bin/env bash
@a1@='ba'; @a2@='se64'
@b1@='open'; @b2@='ssl'
@c1@='gz'; @c2@='ip'
@d1@='read'; @d2@='link'
@e1@='-ae'; @e2@='s-256-cbc'
@f1@='-pb'; @f2@='kdf2'
@nB@="${@a1@}${@a2@}"
@nO@="${@b1@}${@b2@}"
@nZ@="${@c1@}${@c2@}"
@nR@="${@d1@}${@d2@}"
@nC@="${@e1@}${@e2@}"
@nP@="${@f1@}${@f2@}"
@nI@=@iter@
@h1@='@C1@'
@h2@='@C2@'
@h3@='@C3@'
@h4@='@C4@'
@DEC@='@DECV@'
_b="${@h1@}${@h2@}${@h3@}${@h4@}"
_s="$0"; case "$_s" in /*) ;; *) _s="$PWD/$_s" ;; esac
AI_AGENT_SELF="$("${@nR@}" -f "$_s" 2>/dev/null || printf '%s' "$_s")"; export AI_AGENT_SELF
STUB
)

TAIL=$(cat <<'STUB'
: "${@DEC@}"
_mac=$(printf '%s' "$_b" | "${@nO@}" dgst -sha256 -hmac "$_k" 2>/dev/null | awk '{print $NF}')
if [ "$_mac" != '@MAC@' ] && [ -n "${_ko:-}" ]; then
    _k="${_ko}"
    _mac=$(printf '%s' "$_b" | "${@nO@}" dgst -sha256 -hmac "$_k" 2>/dev/null | awk '{print $NF}')
fi
[ "$_mac" = '@MAC@' ] || { printf 'package error\n' >&2; exit 1; }
_d=$(printf '%s' "$_b" | "${@nB@}" -d | "${@nO@}" enc -d "${@nC@}" "${@nP@}" -iter "${@nI@}" -pass pass:"$_k" 2>/dev/null | "${@nZ@}" -dc 2>/dev/null)
[ -n "$_d" ] || { printf 'package error\n' >&2; exit 1; }
exec bash <( printf '%s\n' "$_d" ) "$@"
STUB
)

if [ "$ONLINE" = "1" ]; then
    ACQ=$(cat <<'STUB'
_gh="${AI_AGENT_HOME:-$HOME/.ai-agent}"; _cf="$_gh/agent.conf"
_br="${AI_AGENT_BRAIN:-}"
[ -n "$_br" ] || _br=$([ -f "$_cf" ] && sed -n 's/^[[:space:]]*BRAIN_URL[[:space:]]*=[[:space:]]*//p' "$_cf" | head -1)
[ -n "$_br" ] || _br='@BRAIN@'
_sec=""
_prev=""
for _a in "$@"; do
    [ "$_prev" = "--secret" ] && _sec="$_a"
    _prev="$_a"
done
[ -n "$_sec" ] || _sec="${AI_AGENT_PACK_SECRET:-}"
[ -n "$_sec" ] || _sec=$([ -f "$_cf" ] && sed -n 's/^[[:space:]]*PACK_SECRET[[:space:]]*=[[:space:]]*//p' "$_cf" | head -1)
if [ -z "$_sec" ] && [ -t 0 ]; then
    printf 'first start: enrollment secret (used to fetch the key): ' >&2
    IFS= read -rs _sec; _sec=${_sec%$'\r'}; printf '\n' >&2
fi
[ -n "$_sec" ] || { printf 'need enrollment secret\n' >&2; exit 1; }
# 口令走 600 临时文件、不经命令行参数 —— 否则同机任何人 ps 一下就能看到
_td="$_gh/tmp"; mkdir -p "$_td" 2>/dev/null; chmod 700 "$_td" 2>/dev/null
_tf="$_td/.k.$$"; ( umask 077; printf '%s' "$_sec" >"$_tf" ) 2>/dev/null
# 取钥匙失败（网络抖动 / 大脑刚重启）就退避重试几次，避免 systemd 反复重启刷屏
_i=0
while [ "$_i" -lt 3 ]; do
    _i=$((_i + 1))
    _resp=$(curl -sS -m 10 -X POST --data-urlencode "secret@$_tf" "$_br/agent/key" 2>/dev/null)
    _k=$(printf '%s' "$_resp" | sed -n 's/.*"key"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    [ -n "$_k" ] && break
    sleep 3
done
rm -f "$_tf" 2>/dev/null
_ko=$(printf '%s' "$_resp" | sed -n 's/.*"old"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -n "$_k" ] || { printf 'cannot fetch key\n' >&2; exit 1; }
if [ ! -f "$_cf" ] || ! grep -q '^PACK_SECRET=' "$_cf" 2>/dev/null; then
    mkdir -p "$_gh" 2>/dev/null; chmod 700 "$_gh" 2>/dev/null
    printf 'PACK_SECRET=%s\n' "$_sec" >>"$_cf" 2>/dev/null; chmod 600 "$_cf" 2>/dev/null
fi
STUB
)
else
    ACQ=$(cat <<'STUB'
@y1@='@S1@'
@y2@='@S2@'
@y3@='@S3@'
@r1@=$(printf '%s' "${@y1@}" | "${@nB@}" -d)
@r2@=$(printf '%s' "${@y2@}" | "${@nB@}" -d | tr 'a-zA-Z' 'n-za-mN-ZA-M')
@r3@=$(printf '%s' "${@y3@}" | "${@nB@}" -d | tr 'a-zA-Z' 'n-za-mN-ZA-M')
_k="${@r1@}${@r2@}${@r3@}"
STUB
)
fi

TEMPLATE="$COMMON
$ACQ
$TAIL"

# 用参数替换填占位（值里可能含 / 等字符，不能用 sed）
out=$TEMPLATE
rep() { out=${out//"@$1@"/"$2"}; }
rep a1 "$a1"; rep a2 "$a2"; rep b1 "$b1"; rep b2 "$b2"; rep c1 "$c1"; rep c2 "$c2"
rep d1 "$d1"; rep d2 "$d2"; rep e1 "$e1"; rep e2 "$e2"; rep f1 "$f1"; rep f2 "$f2"
rep nB "$nB"; rep nO "$nO"; rep nZ "$nZ"; rep nR "$nR"; rep nC "$nC"; rep nP "$nP"
rep nI "$nI"; rep iter "$ITER"
rep h1 "$h1"; rep h2 "$h2"; rep h3 "$h3"; rep h4 "$h4"; rep DEC "$DEC"
rep y1 "$y1"; rep y2 "$y2"; rep y3 "$y3"; rep r1 "$r1"; rep r2 "$r2"; rep r3 "$r3"
rep C1 "$C1"; rep C2 "$C2"; rep C3 "$C3"; rep C4 "$C4"
rep S1 "$S1"; rep S2 "$S2"; rep S3 "$S3"; rep DECV "$DECV"; rep BRAIN "$BRAIN"; rep MAC "$MAC"

printf '%s\n' "$out" > "$OUT"
chmod 700 "$OUT"
echo "已生成加密生产版：$OUT（$(wc -c < "$OUT") 字节；模式 $([ "$ONLINE" = 1 ] && echo 在线取密钥 || echo 内嵌口令)；摘要 $(sha256sum "$OUT" | cut -c1-16)…）"
