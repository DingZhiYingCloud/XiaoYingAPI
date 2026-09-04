"""URL 请求安全校验（S-09 整改，复用自 S-01 的 SSRF 防护策略）

纯标准库实现（不依赖 Django/第三方），供 Django API 层与 SpiderServices
爬虫脚本共用：校验目标 URL 是否为"安全的公网 http/https 地址"。

策略：
- 协议仅允许 http/https；
- 域名解析出的**全部** IP 均需通过校验——命中私网/回环/链路本地/保留/组播/未指定
  即拒绝（防 DNS Rebinding）；
- 重定向须逐跳校验（调用方在使用 allow_redirects=False 或手动跳转时调用本函数）。
"""
import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = ('http', 'https')


def _is_blocked_ip(ip) -> bool:
    """是否禁止访问：私网 / 回环 / 链路本地 / 保留 / 组播 / 未指定"""
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def check_public_http_url(url: str):
    """校验 url 是否为可安全抓取的公网 http/https 地址。

    :param url: 待请求的 URL
    :return: (ok, err_msg) - ok=True 表示可安全请求；ok=False 时 err_msg 为拒绝原因
    """
    if not url or not isinstance(url, str):
        return False, 'URL 不能为空'
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, 'URL 解析失败'

    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        return False, '仅支持 http/https 公网 URL'

    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, f'域名解析失败: {host}'
    except OSError:
        return False, f'域名解析失败: {host}'

    if not infos:
        return False, f'域名无可用解析结果: {host}'
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, f'解析出非法的 IP: {info[4][0]}'
        if _is_blocked_ip(ip):
            return False, f'禁止访问内网/保留地址段: {ip}'
    return True, ''


def host_matches(host: str, suffixes) -> bool:
    """host 是否命中域名后缀白名单（host 本身或其子域）"""
    host = (host or '').strip().lower()
    if not host:
        return False
    for suffix in suffixes:
        suffix = suffix.lower().strip('.')
        if host == suffix or host.endswith('.' + suffix):
            return True
    return False
