"""超管控制台 - 服务余量

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/quotas/     余量总览 + 最低数量阈值 / 通知配置
    POST /console/quotas/     action = save（保存配置）/ refresh（立即检查一轮）

被监控的服务清单来自 API/apis/quota/services.py 的注册表（代码侧唯一来源），
本页只负责展示与配置读写。
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.apis.quota.services import SERVICES
from API.apis.quota.utils import CHECK_INTERVAL_SECONDS, check_all
from API.models import QuotaService, QuotaSetting

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.quota')

REDIRECT_URL = 'website:console_quotas'


@superadmin_required
def quotas_view(request):
    """服务余量页：展示 + 保存配置 + 立即检查"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save':
            return _save(request)
        if action == 'refresh':
            return _refresh(request)
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)
    return _render(request)


def _render(request):
    """渲染：注册表顺序逐个服务一行，附全局通知设置"""
    setting = QuotaSetting.get_solo()
    rows = []
    for code, meta in SERVICES.items():
        # 注意：这里不能用 `_` 当丢弃变量 —— 会盖掉上面 `gettext as _` 的翻译函数
        service, _created = QuotaService.objects.get_or_create(
            code=code, defaults={'threshold': meta.get('default_threshold')})
        rows.append({
            'code': code,
            'name': _(meta['name']),
            'unit': _(meta['unit']),
            'balance': service.balance,
            'threshold': service.threshold,
            'notify_enabled': service.notify_enabled,
            'notify_method': service.notify_method,
            'alert_active': service.alert_active,
            'last_checked_at': service.last_checked_at,
            'last_error': service.last_error,
            'last_notified_at': service.last_notified_at,
        })
    return render(request, 'console/quotas.html', {
        'rows': rows,
        'setting': setting,
        'notify_methods': QuotaService.NOTIFY_METHOD_CHOICES,
        'check_interval_minutes': CHECK_INTERVAL_SECONDS // 60,
    })


def _save(request):
    """保存「接收邮箱 + 各服务的阈值 / 开关 / 通知方式」

    先整体校验再落库：任一项非法就整单不保存，避免出现「改了一半」的配置。
    """
    email = (request.POST.get('notify_email') or '').strip()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, _('接收通知邮箱格式不正确：%(email)s') % {'email': email})
            return redirect(REDIRECT_URL)

    valid_methods = dict(QuotaService.NOTIFY_METHOD_CHOICES)
    form_rows = []
    for code, meta in SERVICES.items():
        raw = (request.POST.get(f'threshold_{code}') or '').strip()
        threshold = None
        if raw:
            try:
                threshold = Decimal(raw)
            except (InvalidOperation, ValueError):
                threshold = None
                messages.error(request, _('%(name)s 的阈值必须是数字') % {'name': _(meta['name'])})
                return redirect(REDIRECT_URL)
            if not threshold.is_finite() or threshold < 0:
                messages.error(request,
                               _('%(name)s 的阈值必须是不小于 0 的数字') % {'name': _(meta['name'])})
                return redirect(REDIRECT_URL)
        method = (request.POST.get(f'notify_method_{code}') or '').strip()
        form_rows.append({
            'code': code,
            'threshold': threshold,
            # 多选框没勾选时不会提交，故按「字段是否存在」判断
            'notify_enabled': request.POST.get(f'notify_enabled_{code}') == 'on',
            'notify_method': method if method in valid_methods else QuotaService.NOTIFY_METHOD_EMAIL,
        })

    setting = QuotaSetting.get_solo()
    setting.notify_email = email
    setting.save(update_fields=['notify_email', 'updated_time'])

    for row in form_rows:
        service, _created = QuotaService.objects.get_or_create(code=row['code'])
        service.threshold = row['threshold']
        service.notify_enabled = row['notify_enabled']
        service.notify_method = row['notify_method']
        service.save(update_fields=['threshold', 'notify_enabled', 'notify_method', 'updated_time'])

    notify_success(request, _('余量通知设置已保存'))
    return redirect(REDIRECT_URL)


def _refresh(request):
    """立即检查一轮（与后台线程同一套逻辑，因此也会按需发告警）"""
    results = check_all()
    failed = [item for item in results if not item['ok']]
    if failed:
        detail = '；'.join(f'{item["name"]}：{item["message"]}' for item in failed)
        messages.warning(request, _('检查完成，%(n)s 个服务取数失败：%(detail)s')
                         % {'n': len(failed), 'detail': detail})
    else:
        notify_success(request, _('检查完成，已更新 %(n)s 个服务的余量') % {'n': len(results)})
    return redirect(REDIRECT_URL)
