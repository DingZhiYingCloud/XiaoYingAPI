"""超管控制台 - 上游故障告警

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/upstreams/     各服务在当前窗口的上游失败率 + 全局告警参数
    POST /console/upstreams/     action = save（保存参数）/ refresh（立即检查一轮）

被监控的服务不需要人工维护清单 —— 就是调用统计表里出现过的服务前缀
（口径见 API/apis/monitor/utils.py），新接入服务自动纳入监控。
本页只负责展示与参数读写，判定 / 告警逻辑都在 API/apis/monitor/utils.py。
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.apis.monitor.utils import CHECK_INTERVAL_SECONDS, check_all, collect_metrics
from API.common import api_stats_query as stats_query
from API.models import QuotaSetting, UpstreamAlertSetting, UpstreamAlertState

from .admin_auth import notify_success, superadmin_required
from .console import _UNMATCHED_SERVICE, _service_label, _service_names, _service_url

logger = logging.getLogger('api.monitor')

REDIRECT_URL = 'website:console_upstreams'


@superadmin_required
def upstreams_view(request):
    """上游故障告警页：展示 + 保存参数 + 立即检查"""
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
    """渲染：逐个服务一行（当前窗口实测指标 + 告警态），附全局参数"""
    setting = UpstreamAlertSetting.get_solo()
    metrics = collect_metrics()
    states = {state.service: state for state in UpstreamAlertState.objects.all()}
    names = _service_names()

    services = {key for key in stats_query.service_keys() if key}
    services.update(states)
    # 扫描器探测归并出的伪服务不是真实上游，不展示（也不会被巡检写入，这里兜住历史残留行）
    services.discard(_UNMATCHED_SERVICE)

    rows = []
    for service in services:
        metric = metrics.get(service, {'calls': 0, 'failed': 0, 'rate': 0.0})
        state = states.get(service)
        breached = (setting.enabled
                    and metric['calls'] >= setting.min_calls
                    and metric['rate'] >= float(setting.failed_rate_threshold))
        rows.append({
            'service': service,
            'name': _service_label(service, names),
            'url': _service_url(service),
            'calls': metric['calls'],
            'failed': metric['failed'],
            'rate': metric['rate'],
            'breached': breached,
            'alert_active': bool(state and state.alert_active),
            'last_alert_at': state.last_alert_at if state else None,
        })
    # 告警中的置顶，其余按窗口调用量降序 —— 有问题的一眼可见
    rows.sort(key=lambda row: (not row['alert_active'], -row['calls'], row['name']))

    return render(request, 'console/upstreams.html', {
        'rows': rows,
        'setting': setting,
        'notify_email': QuotaSetting.get_solo().notify_email,
        'window_label': _window_label(),
        'check_interval_minutes': CHECK_INTERVAL_SECONDS // 60,
    })


def _window_label():
    """当前判定窗口的展示文案（两个整点小时的时段，如 14:00-16:00）"""
    from API.apis.monitor.utils import window_slots

    slots = sorted(window_slots())
    start = slots[0][1]
    end = slots[-1][1] + 1
    return f'{start:02d}:00 - {end:02d}:00'


def _save(request):
    """保存全局告警参数（阈值 / 最小样本数 / 开关）

    先整体校验再落库：任一项非法就整单不保存，避免出现「改了一半」的配置。
    """
    raw_rate = (request.POST.get('failed_rate_threshold') or '').strip()
    try:
        threshold = Decimal(raw_rate)
    except (InvalidOperation, ValueError):
        messages.error(request, _('失败率阈值必须是数字'))
        return redirect(REDIRECT_URL)
    if not threshold.is_finite() or not (0 <= threshold <= 100):
        messages.error(request, _('失败率阈值必须是 0 到 100 之间的数字'))
        return redirect(REDIRECT_URL)

    raw_calls = (request.POST.get('min_calls') or '').strip()
    try:
        min_calls = int(raw_calls)
    except (TypeError, ValueError):
        messages.error(request, _('最小样本数必须是整数'))
        return redirect(REDIRECT_URL)
    if min_calls < 1:
        messages.error(request, _('最小样本数必须大于 0'))
        return redirect(REDIRECT_URL)

    setting = UpstreamAlertSetting.get_solo()
    setting.enabled = request.POST.get('enabled') == 'on'
    setting.failed_rate_threshold = threshold
    setting.min_calls = min_calls
    setting.save(update_fields=['enabled', 'failed_rate_threshold', 'min_calls', 'updated_time'])

    notify_success(request, _('上游故障告警设置已保存'))
    return redirect(REDIRECT_URL)


def _refresh(request):
    """立即检查一轮（与后台线程同一套逻辑，因此也会按需发告警）"""
    results = check_all()
    alerted = [item['service'] for item in results if item['action'] == 'alerted']
    if alerted:
        messages.warning(request, _('检查完成，%(n)s 个服务触发上游故障告警：%(detail)s')
                         % {'n': len(alerted), 'detail': '、'.join(alerted)})
    else:
        notify_success(request, _('检查完成，%s 个服务均未触发告警') % len(results))
    return redirect(REDIRECT_URL)
