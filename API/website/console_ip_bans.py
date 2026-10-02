"""超管控制台 - IP 封禁

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/ip-bans/   封禁列表（生效中 / 已过期 / 已解禁）+ 封禁表单
    POST /console/ip-bans/   action = ban（新增封禁）/ unban（手动解禁）

口径（判定与读写都在 `API/common/ip_guard.py`，与拦截中间件、官网顶部提示条共用同一份实现）：
    · 默认封禁 7 天；可选 1 / 3 / 7 / 30 天快捷档位，也能手填天数，或直接勾「永久封禁」；
    · **封禁必须填原因** —— 原因会同时展示给被封访客（官网顶部提示条）与管理员，用于申诉与复核；
    · 到期自动失效（按 `expire_time` 判定，不需要定时任务）；手动解禁置 `is_active=False` 并留痕；
    · 本机 / 内网地址不允许封禁；控制台与 Django admin 永不参与判定（管理员被封后仍能进来解禁）。
"""
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.common.ip_guard import (BAN_DAY_PRESETS, DEFAULT_BAN_DAYS, ban_ip, client_ip,
                                 unban_ip)
from API.models import BannedIP

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.security')

REDIRECT_URL = 'website:console_ip_bans'
#: 一次扫描的记录条数（生效中的全部列出，历史在页面内截断）
SCAN_LIMIT = 200
#: 历史（已过期 / 已解禁）最多展示条数
HISTORY_LIMIT = 50


@superadmin_required
def ip_bans_view(request):
    """IP 封禁：展示 + 封禁 + 解禁"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'ban':
            return _ban(request)
        if action == 'unban':
            return _unban(request)
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)
    return _render(request)


def _render(request):
    """列表：生效中的排前面（要人去处理），历史按时间倒序跟在后面"""
    records = list(BannedIP.objects.all()[:SCAN_LIMIT])
    active = [row for row in records if row.is_effective]
    history = [row for row in records if not row.is_effective][:HISTORY_LIMIT]
    return render(request, 'console/ip_bans.html', {
        'rows': active + history,
        'active_total': len(active),
        'total': BannedIP.objects.count(),
        'presets': BAN_DAY_PRESETS,
        'default_days': DEFAULT_BAN_DAYS,
        'operator_ip': client_ip(request),
    })


def _record_or_none(raw_id):
    """按主键取封禁记录（缺失 / 非法 UUID 一律 None，不抛 500）"""
    raw = (raw_id or '').strip()
    if not raw:
        return None
    try:
        return BannedIP.objects.filter(pk=raw).first()
    except (ValidationError, ValueError):
        return None


def _ban(request):
    """新增封禁（天数解析与校验都交给 ip_guard.ban_ip，保证与其它调用方同一口径）"""
    record, error = ban_ip(
        (request.POST.get('ip') or '').strip(),
        reason=(request.POST.get('reason') or '').strip(),
        days=(request.POST.get('days') or '').strip() or None,
        permanent=request.POST.get('permanent') == 'on',
        operator=request.user.get_username(),
    )
    if error:
        messages.error(request, _(error))
        return redirect(REDIRECT_URL)
    expire_text = _('永久') if record.is_permanent else record.expire_time.strftime('%Y-%m-%d %H:%M')
    logger.info('IP 已封禁 ip=%s expire=%s operator=%s reason=%s',
                record.ip, expire_text, record.operator, record.reason)
    notify_success(request, _('已封禁 %(ip)s（解禁时间：%(expire)s）：%(reason)s')
                   % {'ip': record.ip, 'expire': expire_text, 'reason': record.reason})
    return redirect(REDIRECT_URL)


def _unban(request):
    """手动解禁（已解禁的不重复操作）"""
    record = _record_or_none(request.POST.get('id'))
    if record is None:
        messages.error(request, _('封禁记录不存在'))
        return redirect(REDIRECT_URL)
    if not record.is_active:
        messages.error(request, _('该记录已解禁，无需重复操作'))
        return redirect(REDIRECT_URL)
    unban_ip(record, operator=request.user.get_username(),
             note=(request.POST.get('note') or '').strip())
    logger.info('IP 已解禁 ip=%s operator=%s', record.ip, request.user.get_username())
    notify_success(request, _('已解禁 %(ip)s') % {'ip': record.ip})
    return redirect(REDIRECT_URL)
