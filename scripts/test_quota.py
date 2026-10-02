"""服务余量监控 + 低量邮件告警 回归测试

覆盖范围：
    第 1 轮 取数：51代理 账户余额 / 超级鹰 题分（**真实调用上游**，验证接口口径未变）
    第 2 轮 巡检写回：check_all() 更新余量、检查时间，并清空上次错误
    第 3 轮 告警只发一次：跌破阈值发一封，继续低于不再发
    第 4 轮 恢复重新武装：余量回升后复位，再次跌破可再发一封
    第 5 轮 不通知的情形：阈值留空 / 未启用通知
    第 6 轮 取数失败：只记错误，不覆盖上一次成功取回的余量
    第 7 轮 控制台页面：展示 / 保存配置 / 立即检查 / 非法入参 / 匿名拦截

隔离策略：QuotaService 是「一个服务一行」、QuotaSetting 是「全库一行」的固定表，没有
可供标记的隔离维度，故**测试前快照、结束时原样还原**（含删除测试期间新建的行）。

邮件一律不外发：把 `API.apis.quota.utils.send_email` 换成记录替身，只断言调用参数。
告警逻辑用替身取数函数驱动，避免真实网络抖动影响判定；第 1 轮单独测真实取数。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_quota.py
"""
import os
import sys
import time
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db.models import Max
from django.test import Client
from django.urls import reverse

from API.apis.quota import utils as quota_utils
from API.apis.quota.services import (SERVICES, fetch_51daili_balance,
                                     fetch_chaojiying_score)
from API.models import ConsoleAuditLog, QuotaService, QuotaSetting, SecuritySetting

RUN = str(int(time.time()))
TEST_EMAIL = f'xytest.quota.{RUN}@example.com'
URL_NAME = 'website:console_quotas'

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


class _StubFetcher:
    """取数替身：把「告警逻辑」与真实网络解耦，按时设定的结果返回"""

    def __init__(self):
        self.result = (True, Decimal('0'))

    def set(self, ok, value):
        self.result = (ok, value)

    def __call__(self):
        return self.result


class _MailRecorder:
    """发信替身：只记录调用，不外发"""

    def __init__(self):
        self.calls = []
        self.ok = True

    def __call__(self, subject, body, recipients, html_body=None):
        self.calls.append({
            'subject': subject, 'body': body, 'recipients': list(recipients),
        })
        return self.ok, ('邮件发送成功' if self.ok else '邮件发送失败: 模拟失败')


def service_of(code):
    obj, _ = QuotaService.objects.get_or_create(code=code)
    return obj


def snapshot():
    """记录测试前的余量行与全局设置，供结束时还原"""
    return {
        'services': {
            row.code: {
                'balance': row.balance, 'threshold': row.threshold,
                'notify_enabled': row.notify_enabled, 'notify_method': row.notify_method,
                'alert_active': row.alert_active, 'last_checked_at': row.last_checked_at,
                'last_error': row.last_error, 'last_notified_at': row.last_notified_at,
            } for row in QuotaService.objects.all()
        },
        'setting_existed': QuotaSetting.objects.filter(pk=QuotaSetting.SINGLETON_PK).exists(),
        'notify_email': QuotaSetting.get_solo().notify_email,
        # 控制台写操作会被审计留痕（见 admin_auth），第 7 轮的 POST 会往审计表塞记录；
        # 记下当前最大 id，结束时删掉本次新增的部分
        'audit_max_id': ConsoleAuditLog.objects.aggregate(m=Max('id'))['m'] or 0,
    }


def restore(state):
    """还原快照：原有行恢复字段值，测试期间新建的行删掉"""
    for code, fields in state['services'].items():
        QuotaService.objects.filter(code=code).update(**fields)
    QuotaService.objects.exclude(code__in=state['services']).delete()
    if state['setting_existed']:
        setting = QuotaSetting.get_solo()
        setting.notify_email = state['notify_email']
        setting.save(update_fields=['notify_email'])
    else:
        QuotaSetting.objects.all().delete()
    ConsoleAuditLog.objects.filter(id__gt=state['audit_max_id']).delete()


def superadmin_client():
    """返回 (已登录超管的客户端, 超管对象, 是否临时创建)"""
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
    return client, admin, created


# ───────────────────────── 第 1 轮：真实取数 ─────────────────────────

def round1_fetch():
    section('第 1 轮 取数（真实调用上游）')
    ok_a, balance_a = fetch_51daili_balance()
    check('51代理 余额取数成功', ok_a, f'err={balance_a}' if not ok_a else '')
    if ok_a:
        check('51代理 余额为正数', balance_a > 0, f'balance={balance_a}')
    # 51代理 对同账号高频调用会回「请求过快」，故两次真实请求之间留出间隔
    time.sleep(3)
    ok_b, score_b = fetch_chaojiying_score()
    check('超级鹰 题分取数成功', ok_b, f'err={score_b}' if not ok_b else '')
    if ok_b:
        check('超级鹰 题分为正数', score_b > 0, f'score={score_b}')
    return ok_a and ok_b


# ───────────────────────── 第 2 轮：巡检写回 ─────────────────────────

def round2_check(stub):
    section('第 2 轮 巡检写回（check_all）')
    service = service_of('chaojiying')
    service.threshold = None
    service.notify_enabled = True
    service.last_error = '上一轮的旧错误'
    service.save()

    stub.set(True, Decimal('500'))
    results = quota_utils.check_all()

    service.refresh_from_db()
    check('check_all 覆盖全部注册服务', len(results) == len(SERVICES), f'n={len(results)}')
    check('余量已写回', service.balance == Decimal('500'), f'balance={service.balance}')
    check('检查时间已更新', service.last_checked_at is not None)
    check('上次错误已清空', service.last_error == '', f'last_error={service.last_error!r}')
    check('未设阈值时不告警', not service.alert_active)


# ───────────────────────── 第 3 轮：告警只发一次 ─────────────────────────

def round3_alert_once(stub, mail):
    section('第 3 轮 告警只发一次')
    setting = QuotaSetting.get_solo()
    setting.notify_email = TEST_EMAIL
    setting.save(update_fields=['notify_email'])

    service = service_of('chaojiying')
    service.threshold = Decimal('1000')
    service.notify_enabled = True
    service.alert_active = False
    service.save()

    stub.set(True, Decimal('900'))
    quota_utils.check_all()
    service.refresh_from_db()
    check('跌破阈值后进入告警态', service.alert_active)
    check('告警邮件发出 1 封', len(mail.calls) == 1, f'n={len(mail.calls)}')
    if mail.calls:
        call = mail.calls[0]
        check('收件人为后台配置的邮箱', call['recipients'] == [TEST_EMAIL], call['recipients'])
        check('标题含服务名与余量',
              '超级鹰' in call['subject'] and '900' in call['subject'], call['subject'])
    check('告警时间已记录', service.last_notified_at is not None)

    mail.calls.clear()
    quota_utils.check_all()
    service.refresh_from_db()
    check('仍低于阈值时不重复发信', not mail.calls, f'n={len(mail.calls)}')
    check('告警态保持不变', service.alert_active)


# ───────────────────────── 第 4 轮：恢复重新武装 ─────────────────────────

def round4_rearm(stub, mail):
    section('第 4 轮 恢复后重新武装')
    service = service_of('chaojiying')

    stub.set(True, Decimal('2000'))
    quota_utils.check_all()
    service.refresh_from_db()
    check('回升到阈值以上后复位', not service.alert_active)
    check('恢复不发邮件', not mail.calls, f'n={len(mail.calls)}')

    stub.set(True, Decimal('800'))
    quota_utils.check_all()
    service.refresh_from_db()
    check('再次跌破时重新告警', service.alert_active and len(mail.calls) == 1,
          f'calls={len(mail.calls)}')


# ───────────────────────── 第 5 轮：不通知的情形 ─────────────────────────

def round5_disabled(stub):
    section('第 5 轮 不通知的情形（阈值留空 / 未启用通知）')
    service = service_of('chaojiying')

    stub.set(True, Decimal('1'))
    service.threshold = None
    service.notify_enabled = True
    service.save()
    quota_utils.check_all()
    service.refresh_from_db()
    check('阈值留空时不告警并复位', not service.alert_active)

    service.threshold = Decimal('1000')
    service.notify_enabled = False
    service.alert_active = False
    service.save()
    quota_utils.check_all()
    service.refresh_from_db()
    check('未启用通知时即使低于阈值也不告警', not service.alert_active)


# ───────────────────────── 第 6 轮：取数失败 ─────────────────────────

def round6_failure(stub):
    section('第 6 轮 取数失败只记错误')
    service = service_of('chaojiying')
    service.balance = Decimal('777')
    service.notify_enabled = True
    service.threshold = Decimal('1000')
    service.alert_active = False
    service.save()

    stub.set(False, '模拟上游不可用')
    results = quota_utils.check_all()
    service.refresh_from_db()
    failed = [item for item in results if not item['ok']]
    check('失败结果如实上报', len(failed) == len(SERVICES), f'n={len(failed)}')
    check('余量不被失败结果覆盖', service.balance == Decimal('777'), f'balance={service.balance}')
    check('错误已记录', service.last_error == '模拟上游不可用', service.last_error)
    check('取数失败不触发告警', not service.alert_active)


# ───────────────────────── 第 7 轮：控制台页面 ─────────────────────────

def round7_console(client, stub):
    section('第 7 轮 控制台页面（展示 / 保存 / 立即检查 / 权限）')
    url = reverse(URL_NAME)

    resp = client.get(url)
    check('超管访问页面 200', resp.status_code == 200, f'status={resp.status_code}')
    html = resp.content.decode('utf-8')
    check('页面含各服务与阈值输入框',
          all(token in html for token in ('51代理', '超级鹰', 'name="threshold_chaojiying"',
                                          'name="notify_email"')))

    anon = Client()
    resp = anon.get(url)
    expected = 404 if SecuritySetting.get_solo().hide_console else 302
    check('匿名访问被拦截（404 隐身 / 302 跳登录）',
          resp.status_code == expected, f'status={resp.status_code} expect={expected}')

    # 邮箱格式非法：整单不保存
    before = QuotaSetting.get_solo().notify_email
    resp = client.post(url, {'action': 'save', 'notify_email': 'not-an-email'})
    check('非法邮箱被拒（302 回列表）', resp.status_code == 302, f'status={resp.status_code}')
    check('非法邮箱不落库', QuotaSetting.get_solo().notify_email == before)

    # 正常保存
    stub.set(True, Decimal('640'))
    data = {'action': 'save', 'notify_email': TEST_EMAIL}
    for code in SERVICES:
        data[f'threshold_{code}'] = '1000'
        data[f'notify_enabled_{code}'] = 'on'
        data[f'notify_method_{code}'] = 'email'
    resp = client.post(url, data)
    check('保存返回 302', resp.status_code == 302, f'status={resp.status_code}')
    check('接收邮箱已保存', QuotaSetting.get_solo().notify_email == TEST_EMAIL)
    saved = service_of('chaojiying')
    check('阈值已保存', saved.threshold == Decimal('1000'), f'threshold={saved.threshold}')
    check('通知开关已保存', saved.notify_enabled)

    # 阈值为负：整单不保存
    bad = dict(data)
    bad['threshold_chaojiying'] = '-1'
    resp = client.post(url, bad)
    check('负数阈值被拒', resp.status_code == 302 and
          service_of('chaojiying').threshold == Decimal('1000'))

    # 阈值非数字：整单不保存
    bad = dict(data)
    bad['threshold_chaojiying'] = 'abc'
    resp = client.post(url, bad)
    check('非数字阈值被拒', resp.status_code == 302 and
          service_of('chaojiying').threshold == Decimal('1000'))

    # 立即检查
    stub.set(True, Decimal('123'))
    resp = client.post(url, {'action': 'refresh'})
    check('立即检查返回 302', resp.status_code == 302, f'status={resp.status_code}')
    check('立即检查已更新余量', service_of('chaojiying').balance == Decimal('123'),
          f'balance={service_of("chaojiying").balance}')

    # 不支持的操作
    resp = client.post(url, {'action': 'nope'})
    check('未知动作被拒但仍正常返回', resp.status_code == 302, f'status={resp.status_code}')


# ───────────────────────── 第 8 轮：多语言 ─────────────────────────

def round8_i18n(client):
    section('第 8 轮 多语言（en / zh-hant 不回退中文）')
    url = reverse(URL_NAME)

    html = client.get(url, HTTP_ACCEPT_LANGUAGE='en').content.decode('utf-8')
    check('英文页已翻译（无中文回退 / 无模板标记泄漏）',
          'Notification Settings' in html and 'Check now' in html
          and '最低数量阈值' not in html and '立即检查' not in html
          and '{%' not in html and '{{' not in html)

    html = client.get(url, HTTP_ACCEPT_LANGUAGE='zh-hant').content.decode('utf-8')
    check('繁体页已翻译（无简体回退）',
          '通知設置' in html and '最低數量閾值' in html)


def main():
    state = snapshot()
    mail = _MailRecorder()
    original_send = quota_utils.send_email
    original_fetch = {code: meta['fetch'] for code, meta in SERVICES.items()}
    stub = _StubFetcher()
    created_admin = None

    try:
        round1_fetch()

        # 后续各轮用替身取数，避免真实网络抖动影响判定
        for meta in SERVICES.values():
            meta['fetch'] = stub
        quota_utils.send_email = mail

        round2_check(stub)
        round3_alert_once(stub, mail)
        round4_rearm(stub, mail)
        round5_disabled(stub)
        round6_failure(stub)

        client, _admin, created_admin = superadmin_client()
        round7_console(client, stub)
        round8_i18n(client)
    finally:
        quota_utils.send_email = original_send
        for code, fetch in original_fetch.items():
            SERVICES[code]['fetch'] = fetch
        restore(state)
        if created_admin:
            created_admin.delete()
        print('\n测试数据已还原（余量行与通知设置回到测试前状态）')

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
