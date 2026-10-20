"""IP 封禁的判定与读写（中间件 / 控制台 / 官网横幅共用同一口径）

**IP 口径全站唯一**：线上是 Nginx + uwsgi，真实来源 IP 由 Nginx 追加在
`X-Forwarded-For` 的**最后一段**（`$proxy_add_x_forwarded_for` 会把客户端自带的 XFF
原样保留在前，只有末段是 Nginx 亲眼看到的直连地址），因此这里**取末段** ——
与 `API/website/views.py` 登录防爆破的取法一致，避免各处再抄一份「首段 / 末段」不同的实现。

**「生效中」的判定两步走**：先用 (ip, is_active) 索引捞出该 IP 未手动解禁的记录，
再在 Python 侧判到期 —— 把「为空或大于当前时间」写进 SQL 会让索引失效，得不偿失。
"""
import ipaddress
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from API.models import BannedIP

#: 默认封禁天数
DEFAULT_BAN_DAYS = 7
#: 控制台封禁表单的快捷天数档位
BAN_DAY_PRESETS = (1, 3, 7, 30)

#: 「缓存未命中」哨兵（缓存值可能是 None=未封禁，不能用 None 判未命中）
_CACHE_MISS = object()


def _ban_cache_key(ip: str) -> str:
    return f'ip_ban:{ip}'


def client_ip(request) -> str:
    """取客户端真实 IP（Cloudflare → XFF 最后一个公网地址 → X-Real-IP → REMOTE_ADDR）

    **站点在 Cloudflare 之后**：CF 会把真实访客 IP 放在 `CF-Connecting-IP`，
    而 `X-Forwarded-For` 的末段是 Cloudflare 边缘节点（或回源的内网地址）。
    支付风控要求 `clientip` 是真实付款人 IP（传 127.0.0.1 / 内网 / DNS 地址会被上游
    直接拒成「系统异常无法完成付款」），因此：

    1. 优先 `CF-Connecting-IP`（Cloudflare 会覆盖客户端自带值；前提是源站只允许 CF 回源）；
    2. 其次从 XFF **从后往前找第一个公网地址**（跳过 127.0.0.1 / 10.x / 172.16-31.x 等代理地址）；
    3. 最后退回 `X-Real-IP` / `REMOTE_ADDR`。

    直接连源站（绕过 Cloudflare）时 `CF-Connecting-IP` 可伪造，故源站防火墙应只放行
    Cloudflare 回源 IP —— 这是使用该头的前提。
    """
    cf_ip = (request.META.get('HTTP_CF_CONNECTING_IP', '') or '').strip()
    if cf_ip and is_valid_ip(cf_ip) and not is_protected_ip(cf_ip):
        return cf_ip

    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        parts = [seg.strip() for seg in xff.split(',') if seg.strip()]
        for part in reversed(parts):
            if is_valid_ip(part) and not is_protected_ip(part):
                return part
        if parts:
            return parts[-1]
    return (request.META.get('HTTP_X_REAL_IP', '')
            or request.META.get('REMOTE_ADDR', '') or '').strip()


def is_valid_ip(ip: str) -> bool:
    """是否是合法的 IPv4 / IPv6 地址"""
    try:
        ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return False
    return True


def is_protected_ip(ip: str) -> bool:
    """本机 / 内网 / 保留地址不允许封禁（避免把自己或内网服务锁死）"""
    try:
        addr = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return False
    return bool(addr.is_loopback or addr.is_private or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def _query_effective_ban(ip: str):
    """直查库：该 IP 生效中的封禁记录（无则 None）

    同一 IP 可能有多条历史记录，只要有一条「未解禁且未到期」就算生效。
    """
    for record in BannedIP.objects.filter(ip=ip, is_active=True).order_by('-create_time'):
        if not record.is_expired:
            return record
    return None


def find_effective_ban(ip: str):
    """取该 IP 当前**生效中**的封禁记录（无则 None）

    带进程内 TTL 缓存（settings.IP_BAN_CACHE_TTL，默认 30s）：封禁判定会出现在每个
    网页请求上，而封禁本身是低频运维操作，缓存可省掉请求级 DB 查询；后台调入/解封会
    立即清掉本进程缓存，改动对其它 worker 最多滞后 TTL 生效。TTL=0 时关闭缓存。
    """
    ip = (ip or '').strip()
    if not ip:
        return None
    ttl = getattr(settings, 'IP_BAN_CACHE_TTL', 30)
    if not ttl:
        return _query_effective_ban(ip)

    key = _ban_cache_key(ip)
    cached = cache.get(key, _CACHE_MISS)
    if cached is not _CACHE_MISS:
        return cached
    record = _query_effective_ban(ip)
    cache.set(key, record, ttl)
    return record


def is_banned(ip: str) -> bool:
    """该 IP 当前是否被封禁"""
    return find_effective_ban(ip) is not None


def ban_ip(ip: str, *, reason: str, days=None, permanent: bool = False,
           operator: str = ''):
    """新增一条封禁记录

    :param days: 封禁天数（permanent=True 时忽略）；默认 DEFAULT_BAN_DAYS
    :return: (record, error) —— 成功时 error 为空串
    """
    ip = (ip or '').strip()
    if not is_valid_ip(ip):
        return None, 'IP 地址格式不正确'
    if is_protected_ip(ip):
        return None, '本机 / 内网地址不允许封禁'

    reason = (reason or '').strip()
    if not reason:
        return None, '请填写封禁原因'

    expire_time = None
    if not permanent:
        try:
            days = int(days if days is not None else DEFAULT_BAN_DAYS)
        except (TypeError, ValueError):
            return None, '封禁天数必须是正整数'
        if days <= 0:
            return None, '封禁天数必须是正整数'
        expire_time = timezone.now() + timedelta(days=days)

    record = BannedIP.objects.create(
        ip=ip, reason=reason[:255], expire_time=expire_time,
        operator=(operator or '')[:64],
    )
    cache.delete(_ban_cache_key(ip))
    return record, ''


def unban_ip(record, *, operator: str = '', note: str = ''):
    """手动解禁（已解禁的原样返回，不覆盖首次解禁信息）"""
    if record is None or not record.is_active:
        return record
    record.is_active = False
    record.unbanned_at = timezone.now()
    record.unban_note = (note or '')[:255]
    if operator and not record.operator:
        record.operator = operator[:64]
    record.save(update_fields=['is_active', 'unbanned_at', 'unban_note', 'operator',
                               'updated_time'])
    cache.delete(_ban_cache_key(record.ip))
    return record


def effective_ban_count() -> int:
    """当前生效中的封禁条数（控制台首页仪表盘用）"""
    return sum(1 for record in BannedIP.objects.filter(is_active=True) if not record.is_expired)
