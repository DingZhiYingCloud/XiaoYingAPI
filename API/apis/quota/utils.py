"""服务余量巡检与通知

后台线程按固定间隔（`CHECK_INTERVAL_SECONDS`）遍历服务注册表取数、写回余量；
低于各服务设定的阈值时发一封邮件提醒。

**告警去重**：跌破阈值只发一次，余量恢复（或关闭通知）后自动复位、重新武装 —— 见
`_evaluate_alert()`，避免余额没充上时被同一件事天天刷屏。

**多 worker**：uwsgi 每个 worker 都有自己的线程，故「告警态翻转」用行级条件更新抢占，
保证同一轮告警只发出一封邮件；重复取数是可接受的（接口免费、不消耗上游额度）。

为什么用后台线程而不是 celery / cron：与反馈中心 AI 审核同一口径
（见 `API/apps.py` 的 `start_review_worker()`），不引入额外常驻组件。
"""
import logging
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

from API.apis.emails.v1.utils import send_email
from API.models import QuotaService, QuotaSetting

from .services import SERVICES

logger = logging.getLogger('api.quota')

# 巡检间隔（秒）：余量变化慢，半小时一轮足够；调频率改这里
CHECK_INTERVAL_SECONDS = 30 * 60


def check_all():
    """巡检全部已注册服务：逐个取数、写回余量、按需告警

    :return: 每项的检查结果列表（元素为 `_check_one()` 的返回值）
    """
    results = []
    for code, meta in SERVICES.items():
        # 首次为某服务建行时带上注册表里的默认阈值（如 DeepSeek 默认 10 元），
        # 之后一律以控制台页面上的配置为准
        service, _ = QuotaService.objects.get_or_create(
            code=code, defaults={'threshold': meta.get('default_threshold')})
        results.append(_check_one(service, meta))
    return results


def _check_one(service, meta):
    """检查单个服务

    :return: dict {code, name, ok, message, balance, alert}
        alert 取值：'' 无变化 / 'alerted' 本次已发告警 / 'recovered' 已恢复（重新武装）
    """
    ok, result = meta['fetch']()
    now = timezone.now()

    if not ok:
        # 取数失败只记错误、不动余量（旧值比「没有值」有信息量），也不参与告警判定
        service.last_checked_at = now
        service.last_error = str(result)[:255]
        service.save(update_fields=['last_checked_at', 'last_error', 'updated_time'])
        logger.warning('服务余量检查失败 [%s]: %s', service.code, result)
        return {'code': service.code, 'name': meta['name'], 'ok': False,
                'message': str(result), 'balance': service.balance, 'alert': ''}

    service.balance = result
    service.last_checked_at = now
    service.last_error = ''
    service.save(update_fields=['balance', 'last_checked_at', 'last_error', 'updated_time'])

    return {'code': service.code, 'name': meta['name'], 'ok': True, 'message': '',
            'balance': result, 'alert': _evaluate_alert(service, meta, result)}


def _evaluate_alert(service, meta, balance):
    """按余量与阈值翻转「告警态」，返回本次动作（'' / 'alerted' / 'recovered'）

    - 低于阈值：仅当当前不在告警态时发一封邮件并置位 —— 告警只发一次，不重复刷屏；
    - 不低于阈值（含未设阈值 / 未启用通知）：若原本在告警态则复位（重新武装），
      恢复本身不发邮件。
    """
    below = (service.notify_enabled and service.threshold is not None
             and balance < service.threshold)

    if not below:
        if service.alert_active:
            service.alert_active = False
            service.save(update_fields=['alert_active', 'updated_time'])
            return 'recovered'
        return ''

    # 抢占式翻转：多个 worker 同时巡检时，只有把 alert_active 由 False 改成 True 的那个
    # 进程负责发信；其余进程的影响行数为 0，直接跳过
    claimed = QuotaService.objects.filter(pk=service.pk, alert_active=False).update(
        alert_active=True, updated_time=timezone.now())
    service.alert_active = True
    if not claimed:
        return ''
    _send_alert(service, meta, balance)
    return 'alerted'


def _send_alert(service, meta, balance):
    """发余量告警邮件

    未配置接收邮箱时只记日志：告警态已置位，不会反复重试（配好邮箱后下一轮恢复即重新武装）。
    邮件正文固定中文（收件人是后台管理员，不做多语言）。
    """
    recipient = (QuotaSetting.get_solo().notify_email or '').strip()
    name, unit = meta['name'], meta['unit']
    if not recipient:
        logger.warning('服务余量告警未发送：后台未配置接收邮箱（%s 仅剩 %s%s，阈值 %s%s）',
                       name, balance, unit, service.threshold, unit)
        return

    subject = f'【服务余量告警】{name} 仅剩 {balance}{unit}'
    body = '\n'.join([
        f'{name} 的余量已低于设定的最低数量阈值，请及时充值。',
        '',
        f'当前余量：{balance}{unit}',
        f'告警阈值：{service.threshold}{unit}',
        f'检查时间：{timezone.localtime(service.last_checked_at).strftime("%Y-%m-%d %H:%M:%S")}',
        '',
        '余量回升到阈值以上（或在后台关闭该服务的通知）后会重新武装，再次跌破时会再发一封；',
        '在此之前本邮件不会重复发送。可在后台「服务余量」页面调整阈值与接收邮箱。',
    ])
    ok, message = send_email(subject, body, [recipient])
    if ok:
        service.last_notified_at = timezone.now()
        service.save(update_fields=['last_notified_at', 'updated_time'])
        logger.info('服务余量告警已发送 [%s] → %s（余量 %s%s，阈值 %s%s）',
                    service.code, recipient, balance, unit, service.threshold, unit)
    else:
        logger.warning('服务余量告警发送失败 [%s]: %s', service.code, message)


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
    threading.Thread(target=_worker_loop, name='quota-check', daemon=True).start()
    logger.info('服务余量巡检线程已启动（间隔 %s 秒）', CHECK_INTERVAL_SECONDS)


def _worker_loop():
    """巡检线程主循环：启动后先查一轮，之后每隔 CHECK_INTERVAL_SECONDS 再查"""
    while True:
        try:
            close_old_connections()
            check_all()
        except Exception:
            logger.exception('服务余量巡检线程异常')
        time.sleep(CHECK_INTERVAL_SECONDS)
