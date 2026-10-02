"""IP 封禁 + 控制台首页仪表盘 回归测试
覆盖范围：
    第 1 轮 封禁与判定（纯逻辑）：默认 7 天、自定义天数、永久、到期自动失效、
            手动解禁立即失效、重复封禁保留历史
    第 2 轮 入参校验：非法 IP / 本机内网 IP / 空原因 一律拒绝
    第 3 轮 中间件：/api/ 命中封禁返回 20022；解禁后恢复；控制台路径不受影响
    第 4 轮 官网前台：命中封禁时全站顶部提示条出现（含 IP / 原因 / 解禁时间 / 联系方式）
    第 5 轮 控制台页面：鉴权、封禁动作、解禁动作、原因必填
    第 6 轮 控制台首页仪表盘：超管可访问、含趋势与排行图表数据

隔离策略：测试用的 IP 一律取 TEST-NET 网段（198.51.100.x / 203.0.113.x），
跑完全部按网段删除；控制台审计日志按 path 清理；临时超管用完删除。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_ip_ban.py
"""
import os
import sys
import time
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from django.utils.translation import override

from API.common import StatusCode
from API.common.ip_guard import (DEFAULT_BAN_DAYS, ban_ip, client_ip, effective_ban_count,
                                 find_effective_ban, is_banned, unban_ip)
from API.models import BannedIP, ConsoleAuditLog, SecuritySetting

RUN = str(int(time.time()))
#: 测试用 IP（1.2.3.x / 5.6.7.8 都是本机不可能出现的公网地址；
#: 注意不能用 198.51.100.x 这类 TEST-NET 网段 —— Python 视其为「私有」，会被保护逻辑挡下）
BAN_IP = '1.2.3.4'
BAN_IP2 = '5.6.7.8'
CONSOLE_PATH = '/console/ip-bans/'

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
        _FAILURES.append((name, detail))
        print(f'  [FAIL] {name}' + (f'  → {detail}' if detail else ''))


def section(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)


def cleanup():
    BannedIP.objects.filter(ip__startswith='1.2.3.').delete()
    BannedIP.objects.filter(ip=BAN_IP2).delete()
    ConsoleAuditLog.objects.filter(path=CONSOLE_PATH).delete()
    ConsoleAuditLog.objects.filter(path='/console/').delete()
    get_user_model().objects.filter(username='xytest_ipban_admin').delete()
    print()
    print('测试数据已清理（封禁记录 / 审计日志 / 临时超管）')


def admin_client():
    """返回 (已登录超管的客户端, 是否临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(username='xytest_ipban_admin', email='',
                                                   password='xytest-ipban')
        created = True
    client = Client()
    client.force_login(admin)
    return client, created


# ==================== 第 1 轮：封禁与判定 ====================

def round1_ban_logic():
    section('第 1 轮 封禁与判定（纯逻辑）')

    record, error = ban_ip(BAN_IP, reason='高频扫描接口', operator='tester')
    check('默认封禁成功', record is not None and error == '', str(error))
    check(f'默认封禁 {DEFAULT_BAN_DAYS} 天',
          record.expire_time is not None
          and abs((record.expire_time - timezone.now()).days - DEFAULT_BAN_DAYS) <= 1,
          str(record.expire_time))
    check('封禁后判定为已封禁', is_banned(BAN_IP) and record.is_effective)
    check('原因与操作人已留痕', record.reason == '高频扫描接口' and record.operator == 'tester')
    check('生效中计数至少为 1', effective_ban_count() >= 1)

    custom, error = ban_ip(BAN_IP2, reason='恶意刷单', days=3, operator='tester')
    check('自定义天数封禁成功（3 天）',
          custom is not None and abs((custom.expire_time - timezone.now()).days - 3) <= 1,
          str(error))

    # 到期自动失效：直接把到期时间改到过去
    BannedIP.objects.filter(pk=custom.pk).update(expire_time=timezone.now() - timedelta(minutes=1))
    custom.refresh_from_db()
    check('到期后自动失效（无需定时任务）',
          custom.is_expired and not custom.is_effective and custom.status_key == 'expired',
          custom.status_key)
    check('到期后不再判定为已封禁', not is_banned(BAN_IP2))

    # 永久封禁
    forever, _ = ban_ip(BAN_IP2, reason='持续攻击', permanent=True, operator='tester')
    check('永久封禁没有到期时间', forever.is_permanent and forever.expire_time is None)
    check('永久封禁判定生效', is_banned(BAN_IP2))

    # 手动解禁：立即失效，但记录保留
    unban_ip(forever, operator='tester', note='已确认是误判')
    forever.refresh_from_db()
    check('手动解禁后立即失效',
          not forever.is_active and not forever.is_effective
          and forever.status_key == 'unbanned',
          forever.status_key)
    check('解禁后不再判定为已封禁', not is_banned(BAN_IP2))
    check('解禁留痕（时间 + 备注）',
          forever.unbanned_at is not None and forever.unban_note == '已确认是误判')
    check('历史记录保留（同一 IP 有 2 条记录）',
          BannedIP.objects.filter(ip=BAN_IP2).count() == 2)

    # 解禁后再封：新增一条，历史不动
    again, _ = ban_ip(BAN_IP2, reason='再次攻击', days=1, operator='tester')
    check('解禁后可重新封禁并保留历史',
          again.is_effective and BannedIP.objects.filter(ip=BAN_IP2).count() == 3)

    unban_ip(again, operator='tester', note='清场')
    BannedIP.objects.filter(pk=custom.pk).update(is_active=False)


# ==================== 第 2 轮：入参校验 ====================

def round2_validation():
    section('第 2 轮 入参校验')

    for label, kwargs in [
        ('非法 IP 被拒', dict(ip='999.1.1.1', reason='x')),
        ('空 IP 被拒', dict(ip='', reason='x')),
        ('本机回环 IP 被拒', dict(ip='127.0.0.1', reason='x')),
        ('内网 IP 被拒', dict(ip='192.168.1.10', reason='x')),
        ('内网 IP 被拒（10 段）', dict(ip='10.0.0.5', reason='x')),
        ('空原因被拒', dict(ip='1.2.3.30', reason='   ')),
        ('天数为 0 被拒', dict(ip='1.2.3.31', reason='x', days='0')),
        ('天数非数字被拒', dict(ip='1.2.3.32', reason='x', days='abc')),
    ]:
        record, error = ban_ip(operator='tester', **kwargs)
        check(label, record is None and bool(error), f'{record} {error!r}')

    check('非法入参不落库',
          not BannedIP.objects.filter(ip__in=['127.0.0.1', '192.168.1.10', '10.0.0.5',
                                              '999.1.1.1', '1.2.3.30',
                                              '1.2.3.31', '1.2.3.32']).exists())
    # IPv6 也能封
    record, error = ban_ip('2001:4860:4860::8888', reason='IPv6 测试', operator='tester')
    check('IPv6 地址可封禁', record is not None, str(error))
    BannedIP.objects.filter(ip='2001:4860:4860::8888').delete()


# ==================== 第 3 轮：中间件 ====================

def round3_middleware():
    section('第 3 轮 中间件（/api/ 拦截 + 控制台豁免）')

    client = Client(SERVER_NAME='xiaoyingapi.com', secure=True)
    headers = {'HTTP_X_FORWARDED_FOR': BAN_IP2}

    resp = client.get('/api/not-exist-yet/', **headers)
    payload = resp.json()
    check('未封禁时 /api/ 不返回「IP 已被封禁」',
          payload.get('code') != StatusCode.IP_BANNED, str(payload))

    ban_ip(BAN_IP2, reason='中间件用例', operator='tester')
    resp = client.get('/api/not-exist-yet/', **headers)
    payload = resp.json()
    check('/api/ 命中封禁返回 IP_BANNED',
          payload.get('code') == StatusCode.IP_BANNED, str(payload))
    check('返回文案含封禁原因',
          'IP 已被封禁' in payload.get('msg', '') and '中间件用例' in payload.get('msg', ''),
          payload.get('msg', ''))
    check('封禁判定优先于路由（不落到 404）', payload.get('code') != StatusCode.NOT_FOUND)

    # 控制台豁免：即使本机 IP 被封也照常进入（这里用封禁 IP 请求控制台，应拿到登录跳转/404 而非封禁 JSON）
    resp = client.get(CONSOLE_PATH, **headers)
    check('控制台路径不受 IP 封禁影响', resp.status_code in (302, 404), str(resp.status_code))

    resp = client.get('/', **headers)
    check('官网首页不被拦截（仍可浏览）', resp.status_code == 200, str(resp.status_code))

    BannedIP.objects.filter(ip=BAN_IP2).delete()
    resp = client.get('/api/not-exist-yet/', **headers)
    check('解禁后 /api/ 立即恢复',
          resp.json().get('code') != StatusCode.IP_BANNED, str(resp.json()))

    # 取 IP 的口径：XFF 末段
    from django.test import RequestFactory
    request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='1.1.1.1, 2.2.2.2, 3.3.3.3')
    check('IP 取 X-Forwarded-For 末段（抗伪造）', client_ip(request) == '3.3.3.3',
          client_ip(request))


# ==================== 第 4 轮：官网顶部提示条 ====================

def round4_web_banner():
    section('第 4 轮 官网前台顶部提示条')

    ban_ip(BAN_IP, reason='提示条用例', days=5, operator='tester')
    client = Client(SERVER_NAME='xiaoyingapi.com', secure=True)
    with override('zh-hans'):
        body = client.get('/', HTTP_X_FORWARDED_FOR=BAN_IP).content.decode('utf-8')
    check('前台首页出现封禁提示条', '你的 IP 已被封禁' in body)
    check('提示条含被封 IP', BAN_IP in body)
    check('提示条含封禁原因', '提示条用例' in body)
    check('提示条含解禁时间', '解禁时间' in body)
    check('提示条引导联系管理员', '联系管理员解禁' in body)

    body2 = client.get('/', HTTP_X_FORWARDED_FOR='8.8.4.4').content.decode('utf-8')
    check('未被封的 IP 不出现提示条', '你的 IP 已被封禁' not in body2)

    # 控制台不出现提示条
    admin, _created = admin_client()
    with override('zh-hans'):
        console_body = admin.get('/console/', HTTP_X_FORWARDED_FOR=BAN_IP).content.decode('utf-8')
    check('控制台页面不出现提示条', '你的 IP 已被封禁' not in console_body)

    BannedIP.objects.filter(ip=BAN_IP).delete()


# ==================== 第 5 轮：控制台页面 ====================

def round5_console(client):
    section('第 5 轮 控制台「IP 封禁」页')

    anon = Client()
    resp = anon.get(CONSOLE_PATH)
    expected = 404 if SecuritySetting.get_solo().hide_console else 302
    check('未登录访问被拦截（隐身 404 / 跳登录）',
          resp.status_code == expected, f'{resp.status_code} expect={expected}')

    resp = client.get(CONSOLE_PATH)
    body = resp.content.decode('utf-8')
    check('超管可访问（200）', resp.status_code == 200, str(resp.status_code))
    check('页面含表单与说明',
          '新增封禁' in body and 'name="reason"' in body and 'name="days"' in body
          and 'name="permanent"' in body)

    # 原因必填
    before = BannedIP.objects.count()
    resp = client.post(CONSOLE_PATH, {'action': 'ban', 'ip': BAN_IP, 'days': '7'})
    check('不填原因不落库', BannedIP.objects.count() == before, str(resp.status_code))

    # 正常封禁
    resp = client.post(CONSOLE_PATH, {'action': 'ban', 'ip': BAN_IP,
                                      'days': '7', 'reason': '控制台封禁用例'})
    record = BannedIP.objects.filter(ip=BAN_IP, is_active=True).first()
    check('控制台封禁成功（302 + 落库）',
          resp.status_code == 302 and record is not None and record.is_effective,
          str(resp.status_code))
    body = client.get(CONSOLE_PATH).content.decode('utf-8')
    check('列表展示该封禁（IP / 原因 / 封禁中）',
          BAN_IP in body and '控制台封禁用例' in body and '封禁中' in body)

    # 解禁
    resp = client.post(CONSOLE_PATH, {'action': 'unban', 'id': str(record.pk),
                                      'note': '误封已解除'})
    record.refresh_from_db()
    check('控制台解禁成功（302 + 不再生效）',
          resp.status_code == 302 and not record.is_effective and not is_banned(BAN_IP),
          str(resp.status_code))
    body = client.get(CONSOLE_PATH).content.decode('utf-8')
    check('列表展示已解禁状态与备注', '已解禁' in body and '误封已解除' in body)

    resp = client.post(CONSOLE_PATH, {'action': 'unban', 'id': 'not-a-uuid'})
    check('非法记录 ID 不报 500', resp.status_code == 302, str(resp.status_code))
    resp = client.post(CONSOLE_PATH, {'action': 'nope'})
    check('未知动作被拒绝（302）', resp.status_code == 302, str(resp.status_code))

    for lang, expect in (('en', 'IP Bans'), ('zh-hant', 'IP 封禁')):
        lang_client = Client()
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        lang_client.force_login(get_user_model().objects.filter(is_superuser=True).first())
        page = lang_client.get(CONSOLE_PATH).content.decode('utf-8')
        check(f'{lang} 页面已翻译（{expect}）', expect in page, expect)


# ==================== 第 6 轮：控制台首页仪表盘 ====================

def round6_home(client):
    section('第 6 轮 控制台首页仪表盘')

    with override('zh-hans'):
        resp = client.get('/console/')
        body = resp.content.decode('utf-8')
    check('首页可访问（200）', resp.status_code == 200, str(resp.status_code))
    check('含 KPI 与仪表盘区块',
          '近 7 天调用概览' in body and '调用趋势' in body and '服务排行' in body
          and '收入与订单' in body and '资源与待关注' in body)
    check('含趋势与排行图表数据（json_script）',
          'home-trend-data' in body and 'home-services-data' in body)
    check('含图表容器与 Chart.js',
          'id="home-trend"' in body and 'id="home-services"' in body
          and 'chart.umd.min.js' in body)
    check('含 IP 封禁入口卡片', '生效中的 IP 封禁' in body)
    check('模板未泄漏（无 {% / {{）', '{%' not in body and '{{' not in body)


def main():
    created_admin = False
    print('IP 封禁 + 控制台首页仪表盘 回归测试开始')
    try:
        round1_ban_logic()
        round2_validation()
        round3_middleware()
        round4_web_banner()
        client, created_admin = admin_client()
        round5_console(client)
        round6_home(client)
    finally:
        cleanup()

    print()
    print('=' * 70)
    print(f'总计：PASS {_PASSED} / FAIL {_FAILED}')
    print('=' * 70)
    if _FAILED:
        for name, detail in _FAILURES:
            print(f'  [FAILED] {name}: {detail}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
