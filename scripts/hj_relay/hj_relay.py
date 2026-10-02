#!/usr/bin/env python3
"""海角自动注册 —— 国内中转出口（HTTP CONNECT 转发器）

**为什么需要它**

51代理 的「提取接口」能靠国内 nginx 中转走通，但**提取出来的代理 IP:端口只在国内网络
可达**：生产服务器（美国）直连这些 IP 一律 TCP 超时（实测 0/5），于是海角取码请求
3 次重试各 20s 全部失败。本服务跑在**国内**机器上，由这台机器去连 51代理，
再把海角的响应原样回传，链路变成::

    小影API（美国） --HTTP 代理隧道--> 本服务（国内） --> 51代理（国内） --> 海角

对海角而言仍是**端到端 TLS**：本服务只做字节透传，**看不到任何明文**
（Cookie / 验证码图片 / 令牌都不落地），也不需要懂海角接口。

**协议（标准 HTTP 代理，客户端发 CONNECT）**::

    CONNECT <海角域名>:443 HTTP/1.1
    Host: <海角域名>:443
    Proxy-Authorization: Basic base64("<会话键>:<密钥>")

- 本服务按**会话键**把同一条 51代理 出口粘住（TTL 内复用），保证「取注册验证码」与
  「提交注册」走同一个出口 IP —— 源站按 captchaId 校验出口，IP 不一致会 302 掉图片。
- 换一个会话键就换一条新出口（客户端每次重试都会换键，坏出口不会拖死整批）。

**安全边界**（缺一不可）

1. 只接受 ``HJ_RELAY_ALLOW_IPS`` 里列出的来源 IP（默认只放行生产服务器）；
2. 必须带正确的密钥（``HJ_RELAY_SECRET``）；
3. **只允许 CONNECT 到 443** —— 杜绝本服务被当成通用跳板 / SSRF 出口。

**部署**（在国内中转机上执行，root）

1. 建目录并放两个文件::

       mkdir -p /www/XiaoYing/hj-relay
       cp hj_relay.py hj_relay.env /www/XiaoYing/hj-relay/
       chmod 600 /www/XiaoYing/hj-relay/hj_relay.env

2. 编辑 ``hj_relay.env``：密钥自己起一个（``python3 -c "import secrets;print(secrets.token_urlsafe(24))"``），
   51代理 四项凭据与生产服务器 ``.env`` 保持一致（同一账号）。

3. 装 systemd 单元::

       cp hj-relay.service /etc/systemd/system/
       systemctl daemon-reload && systemctl enable --now hj-relay

4. 自检（在本机执行，密钥填自己的）::

       curl -sv -x 'http://probe:<密钥>@127.0.0.1:17890' https://www.baidu.com -o /dev/null

5. 放行端口：只对生产服务器开放（本服务自身也会再校验一次来源 IP）。输出链若有 DROP，
   需要加一条 ``iptables -I INPUT -p tcp --dport 17890 -s <生产服务器> -j ACCEPT``。

**注意**：本文件是**独立部署件**，跑在中转机上、不带项目代码，故 51代理 的提取逻辑是
按 ``SpiderServices/ProxyIp/ProxyIP_51daili`` 的口径**自成一份**（参数名与默认值保持一致）。
两边若调整 51代理 的接口口径，需同步这里。
"""
import base64
import json
import logging
import os
import secrets
import socket
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, 'hj_relay.env')
HEADER_LIMIT = 16 * 1024          # 请求头最大字节数（防内存滥用）
RECV_SIZE = 65536
TUNNEL_IDLE_TIMEOUT = 300         # 隧道空闲超时（秒），到点关闭，避免线程泄漏


def _load_env(path):
    """读同目录的 KEY=VALUE 配置文件（支持 # 注释与行内空行），已存在的环境变量优先"""
    values = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in values.items():
        os.environ.setdefault(key, value)


_load_env(ENV_FILE)


def _cfg(key, default=''):
    return (os.getenv(key, '') or default).strip()


# ---------------- 本服务配置 ----------------
LISTEN_HOST, _, LISTEN_PORT = _cfg('HJ_RELAY_LISTEN', '0.0.0.0:17890').partition(':')
LISTEN_PORT = int(LISTEN_PORT or 17890)
ALLOW_IPS = {ip.strip() for ip in _cfg('HJ_RELAY_ALLOW_IPS').split(',') if ip.strip()}
SECRET = _cfg('HJ_RELAY_SECRET')
UPSTREAM_TTL = int(_cfg('HJ_RELAY_UPSTREAM_TTL', '600') or 600)
CONNECT_TIMEOUT = int(_cfg('HJ_RELAY_CONNECT_TIMEOUT', '20') or 20)

# ---------------- 51代理 提取配置（与项目 .env 同名同义） ----------------
# 路径为「不限量套餐」提取接口；2026-10-02 由旧的 /getapi2 换过来（旧路径对新套餐回
# 「套餐类型不存在」），并新增必填参数 pid（不限量套餐 ID）。
API_BASE = (_cfg('PROXY_51DAILI_API_BASE', 'http://bapi.51daili.com')
            or 'http://bapi.51daili.com').rstrip('/')
API_URL = f'{API_BASE}/unlimitedip/getip'
UID = _cfg('PROXY_51DAILI_UID')
ACCESS_NAME = _cfg('PROXY_51DAILI_ACCESS_NAME')
ACCESS_PASSWORD = _cfg('PROXY_51DAILI_ACCESS_PASSWORD')
PACKID = _cfg('PROXY_51DAILI_PACKID')
PID = _cfg('PROXY_51DAILI_PID')
RID = _cfg('PROXY_51DAILI_RID')
EXTRACT_TIMEOUT = int(_cfg('HJ_RELAY_EXTRACT_TIMEOUT', '15') or 15)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('hj-relay')

# 会话键 -> (ip, port, 过期时间)；加锁读写
_upstreams = {}
_upstream_lock = threading.Lock()


def fetch_upstream():
    """从 51代理 提取一条动态代理，返回 (ip, port)

    与项目里 ProxyIP51Daili 的口径一致：参数名、默认值与返回值结构都照抄，
    仅去掉调用方覆盖能力（本服务只服务这一条链路）。
    """
    missing = [name for name, value in (
        ('PROXY_51DAILI_UID', UID), ('PROXY_51DAILI_ACCESS_NAME', ACCESS_NAME),
        ('PROXY_51DAILI_ACCESS_PASSWORD', ACCESS_PASSWORD),
        ('PROXY_51DAILI_PACKID', PACKID), ('PROXY_51DAILI_PID', PID)) if not value]
    if missing:
        raise RuntimeError(f'51代理 凭据未配置：{", ".join(missing)}')

    params = {
        'uid': UID,
        'accessName': ACCESS_NAME,
        'accessPassword': ACCESS_PASSWORD,
        'packid': PACKID,
        'pid': PID,              # 不限量套餐 ID（上游必填）
        'time': '2',             # 稳定使用时长（照抄控制台提取链接）
        'qty': '1',
        'port': '1',             # 1=HTTP/HTTPS
        'format': 'json',
        'field': 'ipport,expiretime,regioncode,isptype',
        'linePoolIndex': '-1',
    }
    if RID:
        params['rid'] = RID

    with urllib.request.urlopen(f'{API_URL}?{urllib.parse.urlencode(params)}',
                                timeout=EXTRACT_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode('utf-8', 'replace'))

    if not isinstance(payload, dict):
        raise RuntimeError(f'51代理 响应格式无法识别：{type(payload).__name__}')
    # success 是字符串 "true"/"false"，不能直接用真值判断（"false" 也是真）
    if payload.get('code') != 0 or str(payload.get('success')).lower() != 'true':
        # 平台两种失败字段名都用过：常见 msg，「地域不符」那类用 message
        reason = payload.get('msg') or payload.get('message') or f'错误码 {payload.get("code")}'
        raise RuntimeError(f'51代理 提取失败：{reason}')

    items = payload.get('data')
    if not isinstance(items, list) or not items:
        raise RuntimeError(f'51代理 未返回可用代理：{str(payload)[:200]}')

    # 形状口径与项目爬虫层一致：field 含 ipport 时 ip 就是 "ip:port"，
    # 不含时 ip / port 分成两个字段
    item = items[0]
    if not isinstance(item, dict):
        raise RuntimeError(f'51代理 返回条目格式无法识别：{item!r}')
    raw_ip = str(item.get('ip') or '').strip()
    if item.get('port'):
        ip, port = raw_ip, str(item.get('port')).strip()
    elif ':' in raw_ip:
        ip, _, port = raw_ip.partition(':')
        ip, port = ip.strip(), port.strip()
    else:
        ip, port = '', ''
    if not ip or not port.isdigit() or not 0 < int(port) < 65536:
        raise RuntimeError(f'51代理 返回的条目缺少合法的 ip / 端口：{item!r}')
    return ip, int(port)


def get_upstream(key):
    """取该会话键绑定的出口（TTL 内复用同一条，保证取码与提交同 IP）"""
    now = time.time()
    with _upstream_lock:
        item = _upstreams.get(key)
        if item and item[2] > now:
            return item[0], item[1]
        # 顺手清掉过期项，避免字典无限增长
        for expired in [k for k, v in _upstreams.items() if v[2] <= now]:
            _upstreams.pop(expired, None)
    ip, port = fetch_upstream()
    with _upstream_lock:
        _upstreams[key] = (ip, port, now + UPSTREAM_TTL)
    return ip, port


def drop_upstream(key):
    """出口连不上时丢弃缓存，下次请求换一条新的"""
    with _upstream_lock:
        _upstreams.pop(key, None)


def read_head(conn):
    """读到请求头结束（\\r\\n\\r\\n），返回 (头部文本, 之后的残留字节)"""
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            return None, b''
        buf += chunk
        if len(buf) > HEADER_LIMIT:
            return None, b''
    head, _, rest = buf.partition(b'\r\n\r\n')
    return head.decode('latin-1'), rest


def parse_head(head):
    """解析请求行与请求头（返回 (method, target, headers)）"""
    lines = head.split('\r\n')
    parts = lines[0].split()
    if len(parts) != 3:
        return None, None, {}
    headers = {}
    for line in lines[1:]:
        if ':' in line:
            name, _, value = line.partition(':')
            headers[name.strip().lower()] = value.strip()
    return parts[0], parts[1], headers


def basic_credentials(headers):
    """取 Basic 认证里的 `用户名:密码`（没有 / 解不开返回 None）"""
    raw = headers.get('proxy-authorization', '')
    if not raw.lower().startswith('basic '):
        return None
    try:
        decoded = base64.b64decode(raw.split(None, 1)[1]).decode('utf-8')
    except Exception:                                   # noqa: BLE001 - 任何解不开都当没带
        return None
    user, _, password = decoded.partition(':')
    return user, password


def reply(conn, status, reason):
    body = f'{status} {reason}'
    conn.sendall(f'HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\n'
                 f'Connection: close\r\n\r\n{body}'.encode())


def open_tunnel(ip, port, target):
    """连上 51代理 出口，并向它发起 CONNECT；成功返回 (套接字, 残留字节)"""
    upstream = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT)
    try:
        cred = base64.b64encode(f'{ACCESS_NAME}:{ACCESS_PASSWORD}'.encode()).decode()
        upstream.sendall(
            f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n'
            f'Proxy-Authorization: Basic {cred}\r\n\r\n'.encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = upstream.recv(4096)
            if not chunk:
                raise RuntimeError('出口在 CONNECT 阶段断开')
            buf += chunk
            if len(buf) > HEADER_LIMIT:
                raise RuntimeError('出口 CONNECT 响应异常（头部过长）')
        status = buf.split(b'\r\n', 1)[0].decode('latin-1')
        if ' 200' not in status:
            raise RuntimeError(f'出口拒绝 CONNECT：{status}')
        return upstream, buf.partition(b'\r\n\r\n')[2]
    except Exception:
        upstream.close()
        raise


def pipe(src, dst):
    """单向透传，任一端断开即收尾（半关闭写端，让另一端把剩余数据发完）"""
    try:
        src.settimeout(TUNNEL_IDLE_TIMEOUT)
        while True:
            data = src.recv(RECV_SIZE)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def serve(conn, peer):
    """处理一条客户端连接（线程内执行）"""
    try:
        conn.settimeout(CONNECT_TIMEOUT)
        head, leftover = read_head(conn)
        if head is None:
            return
        method, target, headers = parse_head(head)

        if method != 'CONNECT':
            # 只做 CONNECT 隧道：普通 HTTP 代理请求一律拒绝，避免被当通用跳板
            reply(conn, 405, 'Method Not Allowed')
            return

        host, _, port = target.rpartition(':')
        if port != '443':
            reply(conn, 403, 'Forbidden')
            return

        creds = basic_credentials(headers)
        if not creds or not secrets.compare_digest(creds[1], SECRET):
            log.warning('密钥校验失败 peer=%s', peer)
            reply(conn, 407, 'Proxy Authentication Required')
            return

        key = creds[0] or 'default'
        upstream = None
        leftover_up = b''
        for attempt in (1, 2):
            ip, up_port = get_upstream(key)
            t0 = time.monotonic()
            try:
                upstream, leftover_up = open_tunnel(ip, up_port, target)
                log.info('隧道建立 key=%s 出口=%s:%s 目标=%s 耗时=%.2fs%s',
                         key, ip, up_port, target, time.monotonic() - t0,
                         '' if attempt == 1 else '（已换出口重试）')
                break
            except Exception as exc:                    # noqa: BLE001 - 换一条出口再试一次
                log.warning('出口不可用 key=%s 出口=%s:%s 原因=%s', key, ip, up_port, exc)
                drop_upstream(key)
                if attempt == 2:
                    reply(conn, 502, 'Bad Gateway')
                    return

        conn.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
        conn.settimeout(None)
        if leftover:                                    # 客户端可能已经抢跑发了数据
            upstream.sendall(leftover)
        if leftover_up:
            conn.sendall(leftover_up)

        back = threading.Thread(target=pipe, args=(upstream, conn), daemon=True)
        back.start()
        pipe(conn, upstream)
        back.join(timeout=5)
        upstream.close()
    except Exception:                                   # noqa: BLE001 - 单连接出错不影响服务
        log.exception('连接处理异常 peer=%s', peer)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    """启动转发器"""
    if not SECRET:
        raise SystemExit('HJ_RELAY_SECRET 未配置，拒绝启动（否则会变成无认证代理）')
    if not ALLOW_IPS:
        raise SystemExit('HJ_RELAY_ALLOW_IPS 未配置，拒绝启动（否则会对全网开放）')

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST or '0.0.0.0', LISTEN_PORT))
    server.listen(128)
    log.info('已启动：监听 %s:%s，放行来源 %s，出口=51代理(%s)，粘性 TTL=%ss',
             LISTEN_HOST or '0.0.0.0', LISTEN_PORT, ','.join(sorted(ALLOW_IPS)),
             '经国内中转' if API_BASE != 'http://bapi.51daili.com' else '直连', UPSTREAM_TTL)

    while True:
        conn, addr = server.accept()
        peer = addr[0]
        if ALLOW_IPS and peer not in ALLOW_IPS:
            log.warning('拒绝非白名单来源 peer=%s', peer)
            conn.close()
            continue
        threading.Thread(target=serve, args=(conn, peer), daemon=True).start()


if __name__ == '__main__':
    main()
