"""上游故障告警巡检

**数据源**：调用统计小时表（`ApiCallStatHour`）。各服务调用上游失败时统一返回 4xxxx
错误码（第三方/外部服务错误，见 `API/common/status_code.py`），故「上游错误」= 业务码
落在 4xxxx 区间的调用。按 `service`（服务前缀，如 `/api/haijiao/`）聚合，与调用统计
看板的失败率口径同源。

**判定窗口**：当前小时 + 上一小时两个整点桶。统计最细只有小时粒度，这是对「最近 1 小时」
最接近的近似；取两个桶还能让窗口在跨整点时保持重叠、样本量不会瞬间归零，避免告警态被误复位。

**判定条件**：窗口内 总调用 ≥ 最小样本数 且 上游错误占比 ≥ 失败率阈值 时告警。

**告警去重**：判定为故障只发一次，恢复正常（或关闭告警）后自动复位、重新武装 —— 见
`_evaluate()`，避免上游一直没修好时被同一件事不停刷屏。

**多 worker**：uwsgi 每个 worker 都有自己的线程，故「告警态翻转」用行级条件更新抢占，
保证同一轮告警只发出一封邮件；重复查询是可接受的（只是读统计表）。

为什么用后台线程而不是 celery / cron：与余量巡检、反馈中心 AI 审核同一口径
（见 `API/apps.py`），不引入额外常驻组件。
"""
import logging
import threading
import time
from datetime import timedelta

from django.db import close_old_connections
from django.db.models import Q, Sum
from django.utils import timezone

from API.apis.emails.v1.utils import send_email
from API.common.api_stats import UNMATCHED_PATH, service_of
from API.models import (
    ApiCallStatHour, QuotaSetting, UpstreamAlertSetting, UpstreamAlertState,
)

logger = logging.getLogger('api.monitor')

# 巡检间隔（秒）：上游故障需要比余量更灵敏，5 分钟一轮；调频率改这里
CHECK_INTERVAL_SECONDS = 5 * 60

# 扫描器探测路径被统计归并后落到的那条「伪服务」前缀（见 api_stats.UNMATCHED_PATH）：
# 它不是真实上游，不参与判定，也不进告警态表
UNMATCHED_SERVICE = service_of(UNMATCHED_PATH)

# 上游错误码区间（左闭右开）：4xxxx = 第三方/外部服务错误
UPSTREAM_CODE_MIN = 40000
UPSTREAM_CODE_MAX = 50000
_UPSTREAM_FILTER = Q(status_code__gte=UPSTREAM_CODE_MIN, status_code__lt=UPSTREAM_CODE_MAX)


def window_slots(now=None):
    """判定窗口覆盖的小时桶：[(日期, 小时)]，当前小时 + 上一小时（跨天安全）"""
    moment = timezone.localtime(now or timezone.now())
    current = moment.replace(minute=0, second=0, microsecond=0)
    previous = current - timedelta(hours=1)
    return [(current.date(), current.hour), (previous.date(), previous.hour)]


def collect_metrics(now=None):
    """窗口内各服务的调用量与上游错误数

    :return: {service: {'calls': 次数, 'failed': 上游错误数, 'rate': 失败率百分比}}
        窗口内没有调用的服务不会出现在结果里。
    """
    window = Q()
    for stat_date, stat_hour in window_slots(now):
        window |= Q(stat_date=stat_date, stat_hour=stat_hour)

    rows = (ApiCallStatHour.objects.filter(window).exclude(service=UNMATCHED_SERVICE)
            .values('service')
            .annotate(calls=Sum('call_count'), failed=Sum('call_count', filter=_UPSTREAM_FILTER)))
    metrics = {}
    for row in rows:
        calls = row['calls'] or 0
        failed = row['failed'] or 0
        metrics[row['service']] = {
            'calls': calls,
            'failed': failed,
            'rate': round(failed * 100 / calls, 2) if calls else 0.0,
        }
    return metrics


def check_all(now=None):
    """巡检一轮：翻转告警态并按需发信

    巡检对象 = 窗口内有调用的服务 ∪ 当前处于告警态的服务：
    前者可能新触发告警，后者即便窗口内已无调用也要能复位（否则服务彻底没流量后
    告警态会一直挂着，下次真出故障时反而不再发信）。

    :return: 每个服务的判定结果列表（元素为 `_check_one()` 的返回值）
    """
    setting = UpstreamAlertSetting.get_solo()
    metrics = collect_metrics(now)

    services = set(metrics)
    services.update(UpstreamAlertState.objects.filter(alert_active=True)
                    .exclude(service=UNMATCHED_SERVICE)
                    .values_list('service', flat=True))

    results = []
    for service in sorted(services):
        metric = metrics.get(service, {'calls': 0, 'failed': 0, 'rate': 0.0})
        results.append(_check_one(service, metric, setting))
    return results


def _check_one(service, metric, setting):
    """判定单个服务并翻转告警态

    :return: dict {service, calls, failed, rate, alert_active, action}
        action 取值：'' 无变化 / 'alerted' 本次已发告警 / 'recovered' 已恢复（重新武装）
    """
    state, _created = UpstreamAlertState.objects.get_or_create(service=service)
    action = _evaluate(state, metric, setting)
    return {'service': service, 'calls': metric['calls'], 'failed': metric['failed'],
            'rate': metric['rate'], 'alert_active': state.alert_active, 'action': action}


def _evaluate(state, metric, setting):
    """按失败率与阈值翻转「告警态」，返回本次动作（'' / 'alerted' / 'recovered'）

    - 判定为故障：仅当当前不在告警态时发一封邮件并置位 —— 告警只发一次，不重复刷屏；
    - 未判定为故障（含关闭告警 / 样本不足）：若原本在告警态则复位（重新武装），
      恢复本身不发邮件。
    """
    breached = (setting.enabled
                and metric['calls'] >= setting.min_calls
                and metric['rate'] >= float(setting.failed_rate_threshold))

    if not breached:
        if state.alert_active:
            state.alert_active = False
            state.save(update_fields=['alert_active', 'updated_time'])
            return 'recovered'
        return ''

    # 抢占式翻转：多个 worker 同时巡检时，只有把 alert_active 由 False 改成 True 的那个
    # 进程负责发信；其余进程的影响行数为 0，直接跳过
    claimed = UpstreamAlertState.objects.filter(pk=state.pk, alert_active=False).update(
        alert_active=True, updated_time=timezone.now())
    state.alert_active = True
    if not claimed:
        return ''
    _send_alert(state, metric, setting)
    return 'alerted'


def _send_alert(state, metric, setting):
    """发上游故障告警邮件

    接收邮箱复用「服务余量」页配置的那个（`QuotaSetting.notify_email`）：两处告警
    都发给同一个后台管理员，不重复配置。未配置邮箱时只记日志：告警态已置位，
    不会反复重试（配好邮箱后下一轮恢复即重新武装）。
    邮件正文固定中文（收件人是后台管理员，不做多语言）。
    """
    recipient = (QuotaSetting.get_solo().notify_email or '').strip()
    if not recipient:
        logger.warning('上游故障告警未发送：后台未配置接收邮箱（%s 失败率 %s%%，'
                       '上游错误 %s / 总调用 %s）',
                       state.service, metric['rate'], metric['failed'], metric['calls'])
        return

    subject = f'【上游故障告警】{state.service} 失败率 {metric["rate"]}%'
    body = '\n'.join([
        f'{state.service} 的上游调用失败率已超过设定的阈值，疑似上游故障，请及时排查。',
        '',
        f'统计窗口：当前小时 + 上一小时',
        f'总调用量：{metric["calls"]} 次',
        f'上游错误：{metric["failed"]} 次（错误码 4xxxx）',
        f'失败率：{metric["rate"]}%',
        f'告警阈值：{setting.failed_rate_threshold}%（样本不少于 {setting.min_calls} 次才判定）',
        f'检查时间：{timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")}',
        '',
        '失败率回落到阈值以下（或在后台关闭告警）后会重新武装，再次超过阈值时会再发一封；',
        '在此之前本邮件不会重复发送。可在后台「上游故障告警」页面调整阈值与最小样本数。',
    ])
    ok, message = send_email(subject, body, [recipient])
    if ok:
        state.last_alert_at = timezone.now()
        state.save(update_fields=['last_alert_at', 'updated_time'])
        logger.info('上游故障告警已发送 [%s] → %s（失败率 %s%%，上游错误 %s / 总调用 %s）',
                    state.service, recipient, metric['rate'], metric['failed'], metric['calls'])
    else:
        logger.warning('上游故障告警发送失败 [%s]: %s', state.service, message)


# ==================== 后台巡检线程 ====================
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def start_worker():
    """启动后台巡检线程（幂等；由 API/apps.py 在服务进程里调用一次）"""
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
    threading.Thread(target=_worker_loop, name='upstream-alert', daemon=True).start()
    logger.info('上游故障告警巡检线程已启动（间隔 %s 秒）', CHECK_INTERVAL_SECONDS)


def _worker_loop():
    """巡检线程主循环：启动后先查一轮，之后每隔 CHECK_INTERVAL_SECONDS 再查"""
    while True:
        try:
            close_old_connections()
            check_all()
        except Exception:
            logger.exception('上游故障告警巡检线程异常')
        time.sleep(CHECK_INTERVAL_SECONDS)
