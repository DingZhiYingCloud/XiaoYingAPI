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

from django.utils import timezone

from API.models import BannedIP

#: 默认封禁天数
DEFAULT_BAN_DAYS = 7
#: 控制台封禁表单的快捷天数档位
BAN_DAY_PRESETS = (1, 3, 7, 30)


def client_ip(request) -> str:
    """取客户端真实 IP（X-Forwarded-For 末段 → X-Real-IP → REMOTE_ADDR）"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        parts = [seg.strip() for seg in xff.split(',') if seg.strip()]
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


def find_effective_ban(ip: str):
    """取该 IP 当前**生效中**的封禁记录（无则 None）

    同一 IP 可能有多条历史记录，只要有一条「未解禁且未到期」就算生效。
    """
    ip = (ip or '').strip()
    if not ip:
        return None
    for record in BannedIP.objects.filter(ip=ip, is_active=True).order_by('-create_time'):
        if not record.is_expired:
            return record
    return None


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
    return record


def effective_ban_count() -> int:
    """当前生效中的封禁条数（控制台首页仪表盘用）"""
    return sum(1 for record in BannedIP.objects.filter(is_active=True) if not record.is_expired)
