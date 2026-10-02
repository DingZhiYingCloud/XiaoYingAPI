"""上游故障告警 回归测试

覆盖范围：
    第 1 轮 判定窗口：当前小时 + 上一小时（含跨天）
    第 2 轮 指标采集：真实读小时表，只把 4xxxx 计为上游错误，窗口外的行不计入
    第 3 轮 判定条件：失败率 ≥ 阈值 且 调用量 ≥ 最小样本数（两个条件缺一不可）
    第 4 轮 告警只发一次 + 恢复重新武装
    第 5 轮 关闭告警 / 窗口内无调用：已置位的告警态复位
    第 6 轮 未配置接收邮箱：置位但不发信
    第 7 轮 控制台页面：展示 / 保存 / 立即检查 / 非法入参 / 匿名拦截
    第 8 轮 多语言：en / zh-hant 不回退中文

隔离策略：测试用的服务前缀带随机后缀（TEST_SERVICE），可精确删除；告警设置（单例）、
告警态与「服务余量」的通知邮箱**测试前快照、结束时原样还原**。

邮件一律不外发：把 `API.apis.monitor.utils.send_email` 换成记录替身，只断言调用参数。
告警判定用替身指标驱动（第 3~6 轮 patch `collect_metrics`），避免真实统计数据的波动
影响结论；第 2 轮单独测真实取数。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_upstream_alert.py
"""
import os
import sys
import time
from datetime import date, datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db.models import Max
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from API.apis.monitor import utils as monitor_utils
from API.common.status_code import StatusCode
from API.models import (
    ApiCallStat, ApiCallStatHour, ConsoleAuditLog, QuotaSetting, SecuritySetting,
    UpstreamAlertSetting, UpstreamAlertState,
)

RUN = str(int(time.time()))
TEST_SERVICE = f'/api/xytest{RUN}/'
TEST_PATH = f'{TEST_SERVICE}probe'
TEST_EMAIL = f'xytest.monitor.{RUN}@example.com'
URL_NAME = 'website:console_upstreams'

_PASSED = 0
_FAILED = 0
_FAILURES = []


def check(name, condition, detail=''):
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f'  [PASS] {name}')
    else:
        _FAILED += 1
        _FAILURES.append(name)
        print(f'  [FAIL] {name} {detail}')


def section(title):
    print(f'\n{"=" * 70}\n{title}\n{"=" * 70}')


class _MailRecorder:
    """发信替身：只记录调用，不外发"""

    def __init__(self):
        self.calls = []

    def __call__(self, subject, body, recipients, html_body=None):
        self.calls.append({'subject': subject, 'body': body, 'recipients': list(recipients)})
        return True, '邮件发送成功'

    def for_service(self, service):
        """本次测试服务触发的告警邮件"""
        return [call for call in self.calls if service in call['subject']]


class _MetricsStub:
    """指标替身：把「告警判定」与真实统计数据解耦"""

    def __init__(self):
        self.data = {}

    def set(self, calls, failed):
        self.data = {TEST_SERVICE: {
            'calls': calls, 'failed': failed,
            'rate': round(failed * 100 / calls, 2) if calls else 0.0,
        }}

    def __call__(self, now=None):
        return dict(self.data)


def _make_hour_row(stat_date, stat_hour, path, status_code, call_count):
    ApiCallStatHour.objects.create(
        stat_date=stat_date, stat_hour=stat_hour, service=TEST_SERVICE, path=path,
        app_id='-', status_code=status_code, call_count=call_count)


def _cleanup_stats():
    ApiCallStatHour.objects.filter(service=TEST_SERVICE).delete()
    ApiCallStat.objects.filter(service=TEST_SERVICE).delete()
    UpstreamAlertState.objects.filter(service=TEST_SERVICE).delete()


def snapshot():
    """记录测试前的告警设置、告警态与余量通知邮箱，供结束时还原"""
    setting = UpstreamAlertSetting.get_solo()
    return {
        'setting': {
            'enabled': setting.enabled,
            'failed_rate_threshold': setting.failed_rate_threshold,
            'min_calls': setting.min_calls,
        },
        'states': {
            row.service: {'alert_active': row.alert_active, 'last_alert_at': row.last_alert_at}
            for row in UpstreamAlertState.objects.all()
        },
        'notify_email': QuotaSetting.get_solo().notify_email,
        # 控制台写操作会被审计留痕（见 admin_auth），第 7 轮的 POST 会往审计表塞记录；
        # 记下当前最大 id，结束时删掉本次新增的部分
        'audit_max_id': ConsoleAuditLog.objects.aggregate(m=Max('id'))['m'] or 0,
    }


def restore(state):
    """还原快照：原有告警态恢复字段值，测试期间新建的行删掉"""
    setting = UpstreamAlertSetting.get_solo()
    setting.enabled = state['setting']['enabled']
    setting.failed_rate_threshold = state['setting']['failed_rate_threshold']
    setting.min_calls = state['setting']['min_calls']
    setting.save()

    for service, fields in state['states'].items():
        UpstreamAlertState.objects.filter(service=service).update(**fields)
    UpstreamAlertState.objects.exclude(service__in=state['states']).delete()

    quota_setting = QuotaSetting.get_solo()
    quota_setting.notify_email = state['notify_email']
    quota_setting.save(update_fields=['notify_email'])

    ConsoleAuditLog.objects.filter(id__gt=state['audit_max_id']).delete()


def superadmin_client():
    """返回 (已登录超管的客户端, 是否临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(
            username=f'xytest_admin_{RUN}', email=f'xytest.admin.{RUN}@example.com',
            password='xytest-admin-pass')
        created = True
    client = Client()
    client.force_login(admin)
    return client, created


def enable_alerts(threshold='50', min_calls=20):
    """把全局告警参数设成测试用的值"""
    setting = UpstreamAlertSetting.get_solo()
    setting.enabled = True
    setting.failed_rate_threshold = threshold
    setting.min_calls = min_calls
    setting.save()
    quota = QuotaSetting.get_solo()
    quota.notify_email = TEST_EMAIL
    quota.save(update_fields=['notify_email'])


# ───────────────────────── 第 1 轮：判定窗口 ─────────────────────────

def round1_window():
    section('第 1 轮 判定窗口（当前小时 + 上一小时）')
    now = timezone.localtime()
    slots = monitor_utils.window_slots(now)
    check('窗口覆盖两个整点小时桶', len(slots) == 2, f'slots={slots}')
    check('第一个桶是当前小时',
          slots[0] == (now.date(), now.hour), f'slots={slots} now={now}')
    previous = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    check('第二个桶是上一小时',
          slots[1] == (previous.date(), previous.hour), f'slots={slots}')

    # 跨天：00:30 的上一小时应落到前一天 23 点
    midnight = timezone.make_aware(datetime(2026, 1, 2, 0, 30))
    slots = monitor_utils.window_slots(midnight)
    check('跨天时上一小时正确落到前一天 23 点',
          slots == [(date(2026, 1, 2), 0), (date(2026, 1, 1), 23)], f'slots={slots}')


# ───────────────────────── 第 2 轮：指标采集 ─────────────────────────

def round2_metrics():
    section('第 2 轮 指标采集（真实读小时表）')
    slots = monitor_utils.window_slots()
    cur_date, cur_hour = slots[0]
    prev_date, prev_hour = slots[1]

    _make_hour_row(cur_date, cur_hour, TEST_PATH, StatusCode.SUCCESS, 100)
    _make_hour_row(cur_date, cur_hour, TEST_PATH, StatusCode.EXTERNAL_API_FAILED, 30)
    _make_hour_row(prev_date, prev_hour, TEST_PATH, StatusCode.SUCCESS, 20)
    _make_hour_row(prev_date, prev_hour, TEST_PATH, StatusCode.EXTERNAL_API_TIMEOUT, 50)
    # 非 4xxxx 的失败（客户端错误 / 系统错误 / HTTP 状态码）不算上游错误
    _make_hour_row(cur_date, cur_hour, TEST_PATH, StatusCode.PARAM_VALUE_INVALID, 40)
    _make_hour_row(cur_date, cur_hour, TEST_PATH, StatusCode.INTERNAL_ERROR, 10)
    _make_hour_row(cur_date, cur_hour, TEST_PATH, 502, 5)
    # 窗口之外（3 小时前）的行不计入
    out = timezone.localtime().replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    _make_hour_row(out.date(), out.hour, TEST_PATH, StatusCode.EXTERNAL_API_FAILED, 999)

    metrics = monitor_utils.collect_metrics()
    row = metrics.get(TEST_SERVICE)
    check('测试服务已出现在指标里', row is not None, f'metrics keys={list(metrics)[:5]}')
    if row:
        check('调用量按两个桶累加（100+30+20+50+40+10+5）',
              row['calls'] == 255, f'calls={row["calls"]}')
        check('上游错误只计 4xxxx（30+50）', row['failed'] == 80, f'failed={row["failed"]}')
        check('失败率 = 上游错误 / 总调用', row['rate'] == round(80 * 100 / 255, 2),
              f'rate={row["rate"]}')
    check('窗口外的行未被计入', row is not None and row['failed'] != 1079)
    check('扫描器归并的伪服务不参与判定',
          monitor_utils.UNMATCHED_SERVICE not in metrics,
          f'unmatched={monitor_utils.UNMATCHED_SERVICE}')


# ───────────────────────── 第 3 轮：判定条件 ─────────────────────────

def round3_judgement(stub, mail):
    section('第 3 轮 判定条件（失败率 + 最小样本数）')
    enable_alerts(threshold='50', min_calls=20)
    UpstreamAlertState.objects.filter(service=TEST_SERVICE).delete()

    stub.set(calls=100, failed=40)          # 40% < 50%
    monitor_utils.check_all()
    check('失败率未达阈值时不告警',
          not UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)

    stub.set(calls=10, failed=10)           # 100% 但样本 10 < 20
    monitor_utils.check_all()
    check('样本不足时不告警（即使失败率 100%）',
          not UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)
    check('样本不足时也不发信', not mail.for_service(TEST_SERVICE))

    stub.set(calls=20, failed=10)           # 50% 恰好等于阈值，样本刚好 20
    monitor_utils.check_all()
    check('刚好等于阈值与最小样本数即告警',
          UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)


# ───────────────────────── 第 4 轮：告警只发一次 ─────────────────────────

def round4_alert_once(stub, mail):
    section('第 4 轮 告警只发一次 + 恢复重新武装')
    mail.calls.clear()
    UpstreamAlertState.objects.filter(service=TEST_SERVICE).delete()
    enable_alerts(threshold='50', min_calls=20)

    stub.set(calls=100, failed=80)
    monitor_utils.check_all()
    state = UpstreamAlertState.objects.get(service=TEST_SERVICE)
    emails = mail.for_service(TEST_SERVICE)
    check('超过阈值后进入告警态', state.alert_active)
    check('告警邮件发出 1 封', len(emails) == 1, f'n={len(emails)}')
    if emails:
        check('收件人为后台配置的邮箱', emails[0]['recipients'] == [TEST_EMAIL],
              emails[0]['recipients'])
        check('标题含服务前缀与失败率',
              TEST_SERVICE in emails[0]['subject'] and '80.0' in emails[0]['subject'],
              emails[0]['subject'])
    check('告警时间已记录', state.last_alert_at is not None)

    monitor_utils.check_all()
    check('仍然超过阈值时不重复发信', len(mail.for_service(TEST_SERVICE)) == 1,
          f'n={len(mail.for_service(TEST_SERVICE))}')

    stub.set(calls=100, failed=10)
    monitor_utils.check_all()
    check('回落到阈值以下后复位',
          not UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)
    check('恢复本身不发邮件', len(mail.for_service(TEST_SERVICE)) == 1,
          f'n={len(mail.for_service(TEST_SERVICE))}')

    stub.set(calls=100, failed=90)
    monitor_utils.check_all()
    check('再次超过阈值时重新告警',
          UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active
          and len(mail.for_service(TEST_SERVICE)) == 2,
          f'n={len(mail.for_service(TEST_SERVICE))}')


# ───────────────────────── 第 5 轮：关闭告警 / 无调用 ─────────────────────────

def round5_disabled_and_idle(stub, mail):
    section('第 5 轮 关闭告警 / 窗口内无调用')
    setting = UpstreamAlertSetting.get_solo()
    setting.enabled = False
    setting.save(update_fields=['enabled'])

    stub.set(calls=100, failed=100)
    monitor_utils.check_all()
    check('关闭告警后即使 100% 失败也不告警',
          not UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)

    # 重新打开并进入告警态，再验证「窗口内无调用」会复位
    setting.enabled = True
    setting.save(update_fields=['enabled'])
    stub.set(calls=100, failed=100)
    monitor_utils.check_all()
    check('重新打开后恢复判定', UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)

    before = len(mail.for_service(TEST_SERVICE))
    stub.data = {}                                   # 窗口内无任何调用
    monitor_utils.check_all()
    check('窗口内无调用时告警态复位',
          not UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)
    check('无调用不产生新告警', len(mail.for_service(TEST_SERVICE)) == before)


# ───────────────────────── 第 6 轮：未配置邮箱 ─────────────────────────

def round6_no_email(stub, mail):
    section('第 6 轮 未配置接收邮箱时置位但不发信')
    UpstreamAlertState.objects.filter(service=TEST_SERVICE).delete()
    QuotaSetting.get_solo()                          # 确保单例行存在
    QuotaSetting.objects.filter(pk=QuotaSetting.SINGLETON_PK).update(notify_email='')

    stub.set(calls=100, failed=100)
    before = len(mail.for_service(TEST_SERVICE))
    monitor_utils.check_all()
    check('无邮箱时仍进入告警态',
          UpstreamAlertState.objects.get(service=TEST_SERVICE).alert_active)
    check('无邮箱时不发信（只记日志）',
          len(mail.for_service(TEST_SERVICE)) == before,
          f'n={len(mail.for_service(TEST_SERVICE))} before={before}')

    QuotaSetting.objects.filter(pk=QuotaSetting.SINGLETON_PK).update(notify_email=TEST_EMAIL)


# ───────────────────────── 第 7 轮：控制台页面 ─────────────────────────

def round7_console(client, mail):
    section('第 7 轮 控制台页面（展示 / 保存 / 立即检查 / 权限）')
    url = reverse(URL_NAME)
    mail.calls.clear()
    # 页面按「调用统计里出现过的服务」列行，故给测试服务补一条按天记录
    ApiCallStat.objects.update_or_create(
        stat_date=timezone.localdate(), path=TEST_PATH, app_id='-',
        status_code=StatusCode.SUCCESS,
        defaults={'service': TEST_SERVICE, 'call_count': 1})

    resp = client.get(url)
    check('超管访问页面 200', resp.status_code == 200, f'status={resp.status_code}')
    html = resp.content.decode('utf-8')
    check('页面含测试服务与参数表单',
          all(token in html for token in (
              TEST_SERVICE, 'name="failed_rate_threshold"', 'name="min_calls"',
              'name="enabled"')))

    anon = Client()
    resp = anon.get(url)
    expected = 404 if SecuritySetting.get_solo().hide_console else 302
    check('匿名访问被拦截（404 隐身 / 302 跳登录）',
          resp.status_code == expected, f'status={resp.status_code} expect={expected}')

    # 非法阈值：整单不保存
    before = UpstreamAlertSetting.get_solo().min_calls
    resp = client.post(url, {'action': 'save', 'failed_rate_threshold': 'abc', 'min_calls': '7'})
    check('非数字阈值被拒（302 回列表）', resp.status_code == 302, f'status={resp.status_code}')
    check('非法阈值不落库', UpstreamAlertSetting.get_solo().min_calls == before)

    resp = client.post(url, {'action': 'save', 'failed_rate_threshold': '120', 'min_calls': '7'})
    check('超过 100 的阈值被拒',
          resp.status_code == 302 and UpstreamAlertSetting.get_solo().min_calls == before)

    resp = client.post(url, {'action': 'save', 'failed_rate_threshold': '30', 'min_calls': '0'})
    check('最小样本数 0 被拒',
          resp.status_code == 302 and UpstreamAlertSetting.get_solo().min_calls == before)

    # 正常保存
    resp = client.post(url, {'action': 'save', 'failed_rate_threshold': '30',
                             'min_calls': '7', 'enabled': 'on'})
    saved = UpstreamAlertSetting.get_solo()
    check('保存返回 302', resp.status_code == 302, f'status={resp.status_code}')
    check('阈值已保存', str(saved.failed_rate_threshold) == '30.00',
          f'threshold={saved.failed_rate_threshold}')
    check('最小样本数已保存', saved.min_calls == 7, f'min_calls={saved.min_calls}')
    check('启用开关已保存', saved.enabled)

    # 取消勾选「启用告警」应关闭（复选框未勾选时浏览器不提交该字段）
    resp = client.post(url, {'action': 'save', 'failed_rate_threshold': '30', 'min_calls': '7'})
    check('未勾选启用时开关被关闭', not UpstreamAlertSetting.get_solo().enabled)

    # 立即检查：测试服务的告警态由真实指标驱动，能正常跑完
    resp = client.post(url, {'action': 'refresh'})
    check('立即检查返回 302', resp.status_code == 302, f'status={resp.status_code}')

    resp = client.post(url, {'action': 'nope'})
    check('未知动作被拒但仍正常返回', resp.status_code == 302, f'status={resp.status_code}')


# ───────────────────────── 第 8 轮：多语言 ─────────────────────────

def round8_i18n(client):
    section('第 8 轮 多语言（en / zh-hant 不回退中文）')
    url = reverse(URL_NAME)

    # 第 7 轮的 POST 攒下若干提示消息（未跟随重定向，故一直留在 session 里）。
    # 消息文案在入队时就已按当时的语言解析成字符串，会原样出现在后续页面里，
    # 与翻译无关 —— 先 GET 一次把它们消费掉，再做断言。
    client.get(url)

    html = client.get(url, HTTP_ACCEPT_LANGUAGE='en').content.decode('utf-8')
    flags = {
        'title': 'Upstream Failure Alerts' in html,
        'enable': 'Enable Alerts' in html,
        'no_zh_enable': '启用告警' not in html,
        'no_zh_threshold': '失败率阈值' not in html,
        'no_tag_b': '{%' not in html,
        'no_tag_v': '{{' not in html,
    }
    check('英文页已翻译（无中文回退 / 无模板标记泄漏）', all(flags.values()), f'{flags}')

    # 注意「游」在繁体里写作「遊」（zhconv 口径），断言要用繁体字形
    html = client.get(url, HTTP_ACCEPT_LANGUAGE='zh-hant').content.decode('utf-8')
    flags = {'启用': '啟用告警' in html, '上游错误': '上遊錯誤' in html}
    check('繁体页已翻译（无简体回退）', all(flags.values()), f'{flags}')


def main():
    _cleanup_stats()
    state = snapshot()
    mail = _MailRecorder()
    stub = _MetricsStub()
    original_send = monitor_utils.send_email
    original_metrics = monitor_utils.collect_metrics
    created_admin = False

    try:
        round1_window()
        round2_metrics()

        # 第 3~6 轮用替身指标驱动判定，避免真实统计波动影响结论
        monitor_utils.send_email = mail
        monitor_utils.collect_metrics = stub
        round3_judgement(stub, mail)
        round4_alert_once(stub, mail)
        round5_disabled_and_idle(stub, mail)
        round6_no_email(stub, mail)

        # 控制台页面走真实取数
        monitor_utils.collect_metrics = original_metrics
        client, created_admin = superadmin_client()
        round7_console(client, mail)
        round8_i18n(client)
    finally:
        monitor_utils.send_email = original_send
        monitor_utils.collect_metrics = original_metrics
        _cleanup_stats()
        restore(state)
        if created_admin:
            get_user_model().objects.filter(username=f'xytest_admin_{RUN}').delete()
        print('\n测试数据已清理（测试服务统计行已删除，设置与告警态已还原）')

    print(f'\n{"=" * 70}')
    print(f'总计：PASS {_PASSED} / FAIL {_FAILED}')
    if _FAILURES:
        print('失败项：')
        for name in _FAILURES:
            print(f'  - {name}')
    print('=' * 70)
    return 1 if _FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
