"""国内中转出口（`scripts/hj_relay`）的客户端封装

**为什么需要它**：51代理 的**节点只从中国内地网络可达** —— 海外服务器拿正确账密直连
也是一律 TCP 超时（实测从美服连 5 个节点 0/5 可用，而国内 5/5、同一台机上的巨量 4/5）。
所以国内那台机器上常驻一个 CONNECT 转发器（部署见 `scripts/hj_relay/hj_relay.py`），
由它去连 51代理 节点，调用方只连转发器::

    调用方 --HTTP 代理隧道--> 中转机 hj_relay --> 51代理 节点 --> 目标站

对目标站仍是**端到端 TLS**：中转机只透传字节，看不到 Cookie / 响应体 / 明文。

**会话键**：中转机按代理用户名把同一条 51代理 出口**粘住**（时长见中转机
`HJ_RELAY_UPSTREAM_TTL`）。所以「同一个 proxies 反复用」= 同一个出口 IP；
换一个键就换一条出口。需要「取码与提交走同一 IP」的流程，复用同一份 proxies 即可。

**配置**（`.env`，留空则不启用中转）::

    PROXY_RELAY_URL=http://<中转机>:17890
    PROXY_RELAY_SECRET=<与中转机 hj_relay.env 的 HJ_RELAY_SECRET 一致>

本模块只负责「把中转能力包成 requests 能用的 proxies」，供海角爬虫与代理 IP 服务共用
（别在别处再拼一遍这个 URL）。
"""
import os
import secrets
from urllib.parse import quote, urlsplit

RELAY_URL = (os.getenv('PROXY_RELAY_URL', '') or '').strip()
RELAY_SECRET = (os.getenv('PROXY_RELAY_SECRET', '') or '').strip()


def enabled() -> bool:
    """中转出口是否已配置（未配置时调用方应回退到直连形态）"""
    return bool(RELAY_URL and RELAY_SECRET)


def _host() -> str:
    """中转机的 host:port（配置缺失 / 格式不对时抛错）"""
    if not enabled():
        raise RuntimeError(
            '未配置国内中转出口: 请在 .env 里设置 PROXY_RELAY_URL 与 PROXY_RELAY_SECRET')
    host = urlsplit(RELAY_URL).netloc
    if not host:
        raise RuntimeError(
            f'PROXY_RELAY_URL 格式不对（应形如 http://ip:port）: {RELAY_URL!r}')
    return host


def build_proxies(key: str = None) -> dict:
    """构造「经国内中转」的 requests proxies 参数

    :param key: 会话键；同一个 key 在中转机侧对应同一条 51代理 出口。
                不传则每次新生成一个（即每取一次换一条出口）
    :return: {'http': url, 'https': url}
    """
    key = key or secrets.token_urlsafe(9)
    url = f'http://{key}:{quote(RELAY_SECRET, safe="")}@{_host()}'
    return {'http': url, 'https': url}


def build_url(key: str = None) -> str:
    """只取「经国内中转」的代理地址串（写进接口返回体时用，便于调用方直接使用）

    :param key: 同 build_proxies
    :return: 形如 http://<会话键>:<密钥>@<中转机>:<端口>
    """
    return build_proxies(key)['https']


def describe() -> str:
    """给日志 / 接口回显用的简短描述（不含密钥）"""
    return f'{urlsplit(RELAY_URL).netloc}（经国内中转）'
