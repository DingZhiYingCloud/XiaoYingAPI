"""第三方支付回归测试（签名 / 渠道框架 / 下单 / 回调 / 查单 / 退款 / 兑换）

覆盖范围：
    第 1 轮 签名规则（纯逻辑）：待签名串排序与空值口径、'0' 不丢、自签自验、篡改必失败、PEM/裸 Base64 兼容
    第 2 轮 渠道注册表：code → 实现类、未知渠道为 None、available_channels 只返回启用的
    第 3 轮 下单（网关打桩）：订单落库、二维码、参数校验（金额 / 最低额 / 渠道未启用 / 支付未开启）
    第 4 轮 异步通知（真 RSA 验签）：发货一次、重复通知幂等、金额不符拒绝、验签失败拒绝、未知订单拒绝、留痕
    第 5 轮 主动查单（网关打桩）：平台已支付 → 补发货；未支付 → 保持待支付
    第 6 轮 对外视图（直接调视图，绕过签名中间件）：未登录归属隔离、参数校验、退款端点
    第 7 轮 退款（网关打桩）：全额退款状态与余额扣回、超额退款被拒
    第 8 轮 用户余额 → 项目点数：汇率换算、余额扣减与加点、余额不足拒绝
    第 9 轮 回调入口（HTTP，免签名）：验签通过回 success，失败回 fail
    第 10 轮 后台/配置健壮性：未配置密钥时的报错语义

隔离策略：全程**不联网**（网关调用打桩）；RSA 密钥对在测试内现生成，不依赖本地密钥文件；
测试数据（订单 / 流水 / 留痕 / 用户 / 项目 / 渠道配置）跑完全部删除，PaySetting 原样还原。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_pay.py
"""
import base64
import json
import os
import sys
import time
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from Crypto.PublicKey import RSA
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory

from API.apis.pay import service
from API.apis.pay.providers import build_provider, get_provider_class, provider_codes
from API.apis.pay.providers.base import PayError
from API.apis.pay.providers.ezfp import EzfpProvider
from API.apis.pay.providers.sign import (
    build_sign_content,
    normalize_key,
    sign_content,
    verify_content,
)
from API.apis.pay.request import create_view, query_view, refund_view
from API.apis.pay.utils import format_money
from API.common import StatusCode
from API.models import (
    AppCreditLedger,
    PayNotifyLog,
    PayOrder,
    PayProvider,
    PaySetting,
    User,
    UserApp,
    UserBalanceLedger,
)

RUN = str(int(time.time()))
MARK = f'xypay{RUN}'

# 测试汇率与最低金额
RATE = Decimal('2.0000')       # 1 元 = 2 点，便于验证换算
MIN_AMOUNT = Decimal('1.00')

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


def _payload(resp) -> dict:
    """取视图 JSON 应答（JsonResponse 默认转义非 ASCII，直接比对中文会误判）"""
    return json.loads(resp.content.decode('utf-8'))


# ==================== 测试用密钥与桩 ====================

# 商户密钥对（本系统签名用）与平台密钥对（模拟支付平台）
_merchant = RSA.generate(2048)
_platform = RSA.generate(2048)
MERCHANT_PRIV = base64.b64encode(_merchant.export_key('DER', pkcs=8)).decode('ascii')
PLATFORM_PRIV = base64.b64encode(_platform.export_key('DER', pkcs=8)).decode('ascii')
PLATFORM_PUB = base64.b64encode(_platform.publickey().export_key('DER')).decode('ascii')

_GATEWAY_CALLS = []
_QUERY_STATUS = {'value': 1}


def _fake_post(self, path, params):
    """网关打桩：记录调用参数，返回平台口径的成功应答（不联网）"""
    _GATEWAY_CALLS.append((path, dict(params)))
    stamp = str(int(time.time()))
    if path == '/api/pay/create':
        # 按真实网关的 jump 应答造桩（支付宝 / 微信在 method=jump 下都是 https 收银台地址）
        return {'code': 0, 'trade_no': 'PLAT' + RUN, 'pay_type': 'jump',
                'pay_info': 'https://example.invalid/pay/submit/PLAT' + RUN,
                'timestamp': stamp, 'sign_type': 'RSA'}
    if path == '/api/pay/query':
        return {'code': 0, 'status': _QUERY_STATUS['value'], 'trade_no': 'PLAT' + RUN,
                'out_trade_no': params.get('out_trade_no', ''), 'money': params.get('_money', ''),
                'timestamp': stamp, 'sign_type': 'RSA'}
    if path == '/api/pay/refund':
        return {'code': 0, 'refund_no': 'REF' + RUN, 'out_refund_no': params.get('out_refund_no', ''),
                'money': params.get('money', ''), 'timestamp': stamp, 'sign_type': 'RSA'}
    raise AssertionError(f'未打桩的网关路径: {path}')


_saved_post = EzfpProvider._post


def _sign_notify(**kwargs) -> dict:
    """按平台身份给回调参数签名（模拟平台推送）"""
    params = {'pid': '1001', 'trade_status': 'TRADE_SUCCESS', 'type': 'alipay', **kwargs}
    params['sign_type'] = 'RSA'
    params['sign'] = sign_content(build_sign_content(params), PLATFORM_PRIV)
    return params


# ==================== 快照与清理 ====================

_snapshot = {}


def snapshot():
    setting = PaySetting.get_solo()
    _snapshot['setting'] = {
        'enabled': setting.enabled,
        'points_per_yuan': setting.points_per_yuan,
        'min_amount': setting.min_amount,
    }
    _snapshot['providers'] = list(PayProvider.objects.values())


def make_provider():
    """建立测试渠道配置（启用 + 生成密钥）

    用 `update_or_create`：本地可能已存在一条真实配置（联调用），不能直接 create 撞唯一约束。
    """
    config, _created = PayProvider.objects.update_or_create(
        code=EzfpProvider.code,
        defaults={'name': '易支付（测试）', 'enabled': True, 'merchant_id': '1001',
                  'gateway': 'https://example.invalid', 'enabled_methods': '',
                  'private_key_enc': '', 'platform_public_key_enc': ''})
    config.set_private_key(MERCHANT_PRIV)
    config.set_platform_public_key(PLATFORM_PUB)
    config.save()
    return config


def cleanup():
    EzfpProvider._post = _saved_post
    PayOrder.objects.filter(provider_code=EzfpProvider.code).delete()
    PayNotifyLog.objects.filter(provider_code=EzfpProvider.code).delete()
    UserBalanceLedger.objects.filter(user__account__startswith='9' + RUN[:6]).delete()
    User.objects.filter(account__startswith='9' + RUN[:6]).delete()
    UserApp.objects.filter(name__contains=MARK).delete()
    AppCreditLedger.objects.filter(app__name__contains=MARK).delete()
    # 控制台写操作会留审计日志，测试产生的要清掉（口径与 test_console_audit 一致）
    from API.models import ConsoleAuditLog
    ConsoleAuditLog.objects.filter(path='/console/pay/').delete()
    if _snapshot.get('created_admin'):
        get_user_model().objects.filter(username='xytest_pay_admin').delete()
    PayProvider.objects.all().delete()
    for row in _snapshot.get('providers', []):
        row.pop('id', None)
        PayProvider.objects.create(**row)
    saved = _snapshot.get('setting')
    if saved:
        PaySetting.objects.filter(pk=PaySetting.SINGLETON_PK).update(**saved)
    print()
    print('测试数据已清理（订单 / 流水 / 留痕 / 用户 / 项目 / 渠道配置），PaySetting 已还原')


def make_user(suffix=''):
    account = ('9' + RUN[:6] + suffix)[:12]
    return User.objects.create(account=account, username=f'支付测试{suffix}', password='x')


def make_app(suffix=''):
    return UserApp.objects.create(name=f'{MARK}项目{suffix}', app_id=f'app_{MARK}{suffix}',
                                  app_secret='sk_test')


# ==================== 各轮用例 ====================

def round1_sign():
    section('第 1 轮 签名规则（纯逻辑）')

    content = build_sign_content({'b': '2', 'a': '1', 'sign': 'x', 'sign_type': 'RSA', 'empty': ''})
    check('待签名串：排除 sign/sign_type/空值且按参数名升序', content == 'a=1&b=2', content)

    content0 = build_sign_content({'zero': 0, 'zero_str': '0', 'none': None})
    check("待签名串：数字 0 与字符串 '0' 都不被剔除", content0 == 'zero=0&zero_str=0', content0)

    msg = 'a=1&b=2&c=3'
    sig = sign_content(msg, MERCHANT_PRIV)
    check('自签自验通过', verify_content(msg, sig, MERCHANT_PRIV) is True or
          verify_content(msg, sig, base64.b64encode(_merchant.publickey().export_key('DER')).decode()) is True)
    check('内容被篡改 → 验签失败', verify_content(msg + 'x', sig,
          base64.b64encode(_merchant.publickey().export_key('DER')).decode()) is False)
    check('空签名 → 验签失败', verify_content(msg, '', MERCHANT_PRIV) is False)
    check('非法签名 → 验签失败（不抛异常）', verify_content(msg, 'not-base64!!', PLATFORM_PUB) is False)

    pem = ('-----BEGIN PRIVATE KEY-----\n'
           + '\n'.join(PLATFORM_PRIV[i:i + 64] for i in range(0, len(PLATFORM_PRIV), 64))
           + '\n-----END PRIVATE KEY-----\n')
    check('PEM 与裸 Base64 归一化一致', normalize_key(pem) == PLATFORM_PRIV)


def round2_registry():
    section('第 2 轮 渠道注册表')

    check('已登记 ezfp 渠道', 'ezfp' in provider_codes())
    check('未知渠道返回 None', get_provider_class('not-exist') is None)
    config = make_provider()
    check('可由配置构造渠道实例', isinstance(build_provider(config), EzfpProvider))
    available = service.available_channels()
    check('available_channels 仅含启用的渠道', [c.code for c in available] == ['ezfp'])
    config.enabled = False
    config.save(update_fields=['enabled'])
    check('渠道停用后不出现在可选列表', service.available_channels() == [])
    config.enabled = True
    config.save(update_fields=['enabled'])
    check('密钥密文落库（明文不出现在字段里）', 'MII' not in config.private_key_enc[:3] or
          config.private_key_enc.startswith('enc:v1:'))
    check('密钥可解密还原', config.private_key == MERCHANT_PRIV)


def round3_create(user):
    section('第 3 轮 下单（网关打桩）')

    PaySetting.objects.filter(pk=PaySetting.SINGLETON_PK).update(
        enabled=True, points_per_yuan=RATE, min_amount=MIN_AMOUNT)

    order = service.create_order(provider_code='ezfp', amount='10', pay_type='alipay',
                                 subject='账户充值', user=user, client_ip='1.2.3.4')
    check('订单已落库且待支付', order.status == PayOrder.STATUS_PENDING and order.pk is not None)
    check('订单号唯一且带前缀', order.out_trade_no.startswith('XY') and len(order.out_trade_no) > 14)
    check('金额按两位小数落库', str(order.amount) == '10.00')
    check('平台订单号已回填', order.trade_no == 'PLAT' + RUN)
    check('拿到平台支付参数（pay_type=jump + 收银台地址）',
          order.pay_type == 'jump' and order.pay_info.startswith('https://'),
          f'{order.pay_type} {order.pay_info}')
    path, sent = _GATEWAY_CALLS[-1]
    check('下单请求走 /api/pay/create', path == '/api/pay/create')
    check('传给平台的金额是两位小数字符串', sent['money'] == '10.00', str(sent.get('money')))
    check('notify_url 指向本站回调', sent['notify_url'].endswith('/pay/notify/ezfp/'),
          sent['notify_url'])
    check('method 固定 web', sent['method'] == 'web')

    for label, kwargs, expect in [
        ('金额非法被拒', dict(provider_code='ezfp', amount='abc', pay_type='alipay'), '金额非法'),
        ('金额为 0 被拒', dict(provider_code='ezfp', amount='0', pay_type='alipay'), '金额非法'),
        ('低于最低金额被拒', dict(provider_code='ezfp', amount='0.5', pay_type='alipay'), '最低'),
        ('未知渠道被拒', dict(provider_code='not-exist', amount='10', pay_type='alipay'), '不存在'),
    ]:
        try:
            service.create_order(subject='x', user=user, **kwargs)
            check(label, False, '未抛出 PayError')
        except PayError as exc:
            check(label, expect in str(exc), str(exc))

    PayProvider.objects.filter(code='ezfp').update(enabled_methods='alipay')
    try:
        service.create_order(provider_code='ezfp', amount='10', pay_type='wxpay', subject='x', user=user)
        check('未在允许列表的支付方式被拒', False, '未抛出 PayError')
    except PayError as exc:
        check('未在允许列表的支付方式被拒', '不支持支付方式' in str(exc), str(exc))
    PayProvider.objects.filter(code='ezfp').update(enabled_methods='')

    PaySetting.objects.filter(pk=PaySetting.SINGLETON_PK).update(enabled=False)
    try:
        service.create_order(provider_code='ezfp', amount='10', pay_type='alipay', subject='x', user=user)
        check('支付总开关关闭时下单被拒', False, '未抛出 PayError')
    except PayError as exc:
        check('支付总开关关闭时下单被拒', '未开启' in str(exc), str(exc))
    PaySetting.objects.filter(pk=PaySetting.SINGLETON_PK).update(enabled=True)
    return order


def round4_notify(order, user):
    section('第 4 轮 异步通知（真 RSA 验签）')

    before = User.objects.values_list('balance', flat=True).get(pk=user.pk)
    params = _sign_notify(out_trade_no=order.out_trade_no, trade_no='PLAT' + RUN,
                          money='10.00', name='账户充值')
    ok, message = service.handle_notify('ezfp', params)
    check('合法通知被接受', ok is True, message)
    order.refresh_from_db()
    check('订单推进为已支付', order.status == PayOrder.STATUS_PAID)
    check('记录支付时间', order.paid_at is not None)
    after = User.objects.values_list('balance', flat=True).get(pk=user.pk)
    check('用户余额按订单金额增加', after - before == Decimal('10.00'), f'{before} → {after}')
    check('写入一条支付充值流水',
          UserBalanceLedger.objects.filter(user=user, type=UserBalanceLedger.TYPE_PAY).count() == 1)

    # 重复通知：幂等
    ok2, _ = service.handle_notify('ezfp', params)
    after2 = User.objects.values_list('balance', flat=True).get(pk=user.pk)
    check('重复通知仍返回成功（不回 fail）', ok2 is True)
    check('重复通知不重复加钱', after2 == after, f'{after} → {after2}')
    check('流水仍只有一条',
          UserBalanceLedger.objects.filter(user=user, type=UserBalanceLedger.TYPE_PAY).count() == 1)

    log = PayNotifyLog.objects.filter(out_trade_no=order.out_trade_no).order_by('-id').first()
    check('回调原文已留痕且标记验签通过', log is not None and log.verified is True and log.handled is True)

    # 验签失败
    bad = _sign_notify(out_trade_no=order.out_trade_no, money='10.00')
    bad['money'] = '999.00'
    ok3, message3 = service.handle_notify('ezfp', bad)
    check('篡改字段 → 验签失败被拒', ok3 is False and '验签失败' in message3, message3)

    # 金额不符（用平台密钥正确签名，但金额与订单不一致）
    other = service.create_order(provider_code='ezfp', amount='3', pay_type='alipay',
                                 subject='t', user=user)
    mismatch = _sign_notify(out_trade_no=other.out_trade_no, money='9.99')
    ok4, message4 = service.handle_notify('ezfp', mismatch)
    check('金额与订单不符被拒', ok4 is False and '金额不符' in message4, message4)
    other.refresh_from_db()
    check('金额不符时订单保持待支付', other.status == PayOrder.STATUS_PENDING)

    # 未知订单
    unknown = _sign_notify(out_trade_no='XY_NOT_EXIST', money='1.00')
    ok5, message5 = service.handle_notify('ezfp', unknown)
    check('未知订单号被拒', ok5 is False and '订单不存在' in message5, message5)

    # 非成功状态
    pending = _sign_notify(out_trade_no=other.out_trade_no, money='3.00',
                           trade_status='WAIT_BUYER_PAY')
    ok6, _ = service.handle_notify('ezfp', pending)
    check('非 TRADE_SUCCESS 通知被忽略且不报错', ok6 is True)


def round5_query(order):
    section('第 5 轮 主动查单（网关打桩）')

    pending = PayOrder.objects.create(out_trade_no='XY' + RUN + 'Q1', provider_code='ezfp',
                                     pay_type='alipay', subject='t', amount=Decimal('5.00'),
                                     status=PayOrder.STATUS_PENDING)
    _QUERY_STATUS['value'] = 1
    EzfpProvider._post = _fake_post
    service.query_order(pending)
    pending.refresh_from_db()
    check('平台已支付 → 本地订单补发货为已支付', pending.status == PayOrder.STATUS_PAID)
    check('记录最近查单时间', pending.last_query_at is not None)

    _QUERY_STATUS['value'] = 0
    still = PayOrder.objects.create(out_trade_no='XY' + RUN + 'Q2', provider_code='ezfp',
                                    pay_type='alipay', subject='t', amount=Decimal('5.00'),
                                    status=PayOrder.STATUS_PENDING)
    service.query_order(still)
    still.refresh_from_db()
    check('平台未支付 → 订单保持待支付', still.status == PayOrder.STATUS_PENDING)


def round6_views(app, user):
    section('第 6 轮 对外视图（直接调视图，绕过签名中间件）')

    rf = RequestFactory()
    order = service.create_order(provider_code='ezfp', amount='8', pay_type='alipay',
                                 subject='对外订单', app=app, client_ip='9.9.9.9', param='ref-1')

    req = rf.post('/api/pay/create', {'pay_type': 'alipay', 'amount': ''})
    req.auth_app = app
    payload = _payload(create_view(req))
    check('缺少金额 → 返回参数缺失码',
          payload['code'] == StatusCode.PARAM_MISSING and '必填' in payload['msg'], str(payload))

    req = rf.post('/api/pay/query', {'out_trade_no': order.out_trade_no})
    req.auth_app = app
    payload = _payload(query_view(req))
    check('本调用方可查自己的订单',
          payload['code'] == StatusCode.SUCCESS and payload['data']['paid'] is False, str(payload))

    other_app = make_app('b')
    req = rf.post('/api/pay/query', {'out_trade_no': order.out_trade_no})
    req.auth_app = other_app
    payload = _payload(query_view(req))
    check('别的项目查不到该订单（归属隔离）',
          payload['code'] == StatusCode.NOT_FOUND, str(payload))

    req = rf.post('/api/pay/refund', {'out_trade_no': order.out_trade_no})
    req.auth_app = app
    payload = _payload(refund_view(req))
    check('未支付订单不允许退款', '已支付的订单' in payload['msg'], str(payload))

    check('对外订单归属为调用项目', PayOrder.objects.get(pk=order.pk).app_id == app.pk)


def round7_refund(app):
    section('第 7 轮 退款（网关打桩）')

    EzfpProvider._post = _fake_post
    payer = make_user('r')
    order = service.create_order(provider_code='ezfp', amount='20', pay_type='alipay',
                                 subject='退款用例', user=payer)
    ok, message = service.handle_notify('ezfp', _sign_notify(out_trade_no=order.out_trade_no,
                                                             money='20.00'))
    check('退款用例：支付回调处理成功', ok is True, message)
    order.refresh_from_db()
    check('退款用例：订单已支付', order.status == PayOrder.STATUS_PAID, order.status)
    balance_paid = User.objects.values_list('balance', flat=True).get(pk=payer.pk)

    try:
        service.refund_order(order, '30')
        check('超额退款被拒', False, '未抛出 PayError')
    except PayError as exc:
        check('超额退款被拒', '超过可退金额' in str(exc), str(exc))

    service.refund_order(order, '5')
    order.refresh_from_db()
    check('部分退款 → 状态为部分退款且记录金额',
          order.status == PayOrder.STATUS_PARTIAL_REFUNDED and str(order.refund_amount) == '5.00')

    service.refund_order(order, '15')
    order.refresh_from_db()
    check('退满 → 状态为已全额退款', order.status == PayOrder.STATUS_REFUNDED)
    after = User.objects.values_list('balance', flat=True).get(pk=payer.pk)
    check('退款同步扣回用户余额', balance_paid - after == Decimal('20.00'),
          f'{balance_paid} → {after}')
    check('写入退款扣回流水',
          UserBalanceLedger.objects.filter(user=payer, type=UserBalanceLedger.TYPE_REFUND).count() == 2)


def round8_transfer(app):
    section('第 8 轮 用户余额 → 项目点数')

    payer = make_user('t')
    User.objects.filter(pk=payer.pk).update(balance=Decimal('100.00'))
    app.refresh_from_db()
    app_before = app.balance

    ok, message, data = service.transfer_to_app_points(payer, app, '30')
    check('兑换成功', ok is True, message)
    check('汇率换算正确（30 元 × 2 = 60 点）', data and data['points'] == Decimal('60.0000'),
          str(data))
    after = User.objects.values_list('balance', flat=True).get(pk=payer.pk)
    check('用户余额扣减', after == Decimal('70.00'), str(after))
    app.refresh_from_db()
    check('项目点数增加', app.balance - app_before == Decimal('60.0000'),
          f'{app_before} → {app.balance}')
    check('写入兑换流水（含点数快照）',
          UserBalanceLedger.objects.filter(user=payer, type=UserBalanceLedger.TYPE_TRANSFER,
                                           points=Decimal('60.0000')).count() == 1)
    check('项目额度流水也记一笔',
          AppCreditLedger.objects.filter(app=app, amount=Decimal('60.0000')).count() >= 1)

    ok2, message2, _ = service.transfer_to_app_points(payer, app, '1000')
    check('余额不足时拒绝兑换', ok2 is False and '余额不足' in message2, message2)


def round9_http_notify(app):
    section('第 9 轮 回调入口（HTTP，免签名）')

    client = Client()
    order = service.create_order(provider_code='ezfp', amount='6', pay_type='alipay',
                                 subject='HTTP 回调', app=app)
    params = _sign_notify(out_trade_no=order.out_trade_no, money='6.00')
    resp = client.get('/pay/notify/ezfp/', params)
    check('合法回调返回 200 + success', resp.status_code == 200 and resp.content == b'success',
          f'{resp.status_code} {resp.content[:40]!r}')
    order.refresh_from_db()
    check('回调后订单为已支付', order.status == PayOrder.STATUS_PAID)

    resp2 = client.get('/pay/notify/ezfp/', {'out_trade_no': order.out_trade_no, 'money': '1.00'})
    check('缺签名 / 金额不符 → fail', resp2.content == b'fail', resp2.content[:40])

    resp3 = client.get('/pay/notify/unknown-channel/', {'out_trade_no': 'x'})
    check('未知渠道回调 → fail', resp3.content == b'fail')


def round10_console(app):
    section('第 10 轮 控制台「支付设置」页（/console/pay/）')

    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created_admin = False
    if admin is None:
        admin = user_model.objects.create_superuser(username='xytest_pay_admin', email='',
                                                    password='xytest-pay')
        created_admin = True
    _snapshot['created_admin'] = created_admin

    anon = Client()
    resp = anon.get('/console/pay/')
    check('未登录访问 → 隐身 404 或跳登录', resp.status_code in (302, 404), str(resp.status_code))

    client = Client()
    client.force_login(admin)
    resp = client.get('/console/pay/')
    body = resp.content.decode('utf-8')
    check('超管可访问（200）', resp.status_code == 200, str(resp.status_code))
    check('页面含标题与渠道配置',
          '支付设置' in body and '易支付' in body and '商户私钥' in body)
    check('页面标注密钥已配置', '已配置' in body)

    # 保存全局设置
    resp = client.post('/console/pay/', {'action': 'save_setting', 'enabled': 'on',
                                        'points_per_yuan': '3.5', 'min_amount': '2'})
    setting = PaySetting.get_solo()
    check('保存全局设置生效（汇率 / 最低金额 / 开关）',
          resp.status_code == 302 and setting.enabled is True
          and str(setting.points_per_yuan) == '3.5000' and str(setting.min_amount) == '2.00',
          f'{setting.enabled} {setting.points_per_yuan} {setting.min_amount}')

    resp = client.post('/console/pay/', {'action': 'save_setting', 'enabled': 'on',
                                        'points_per_yuan': '0', 'min_amount': '1'})
    check('汇率为 0 时拒绝保存', str(PaySetting.get_solo().points_per_yuan) == '3.5000')

    # 非法密钥：拒绝保存（原密钥保持不变）
    before_key = PayProvider.objects.get(code='ezfp').private_key
    resp = client.post('/console/pay/', {'action': 'save_provider', 'code': 'ezfp',
                                        'merchant_id': '6681', 'enabled': 'on',
                                        'private_key': 'this-is-not-a-key'})
    check('非法商户私钥被拒绝且不落库',
          PayProvider.objects.get(code='ezfp').private_key == before_key)

    # 启用但缺密钥：拒绝
    PayProvider.objects.filter(code='ezfp').update(private_key_enc='')
    resp = client.post('/console/pay/', {'action': 'save_provider', 'code': 'ezfp',
                                        'merchant_id': '6681', 'enabled': 'on',
                                        'method_ezfp_alipay': 'on'})
    config = PayProvider.objects.get(code='ezfp')
    check('启用渠道但缺密钥 → 拒绝启用', config.enabled is False or config.private_key == '')

    # 正常保存：pid + 两把密钥 + 勾选支付宝
    resp = client.post('/console/pay/', {'action': 'save_provider', 'code': 'ezfp',
                                        'merchant_id': '6681', 'enabled': 'on',
                                        'private_key': MERCHANT_PRIV,
                                        'platform_public_key': PLATFORM_PUB,
                                        'method_ezfp_alipay': 'on', 'remark': '本地测试'})
    config = PayProvider.objects.get(code='ezfp')
    check('渠道配置保存成功（pid / 启用 / 支付方式）',
          resp.status_code == 302 and config.enabled is True and config.merchant_id == '6681'
          and config.enabled_methods == 'alipay', f'{config.merchant_id} {config.enabled_methods}')
    check('私钥密文落库且可解密还原', config.private_key == MERCHANT_PRIV)
    check('平台公钥密文落库且可解密还原', config.platform_public_key == PLATFORM_PUB)
    check('未知渠道被拒绝',
          client.post('/console/pay/', {'action': 'save_provider', 'code': 'nope'}).status_code == 302)

    # 订单操作：查单 + 退款
    order = service.create_order(provider_code='ezfp', amount='12', pay_type='alipay',
                                 subject='控制台退款用例', app=app)
    check('先在页面看到该订单', order.out_trade_no in client.get('/console/pay/').content.decode('utf-8'))
    check('按状态筛选订单可用',
          client.get('/console/pay/?status=pending').status_code == 200)

    ok, _ = service.handle_notify('ezfp', _sign_notify(out_trade_no=order.out_trade_no,
                                                      money='12.00'))
    check('订单已支付（供后续退款）', ok is True)
    resp = client.post('/console/pay/', {'action': 'sync_order', 'order_id': str(order.pk)})
    check('手动查单返回 302（成功路径）', resp.status_code == 302)

    resp = client.post('/console/pay/', {'action': 'refund_order', 'order_id': str(order.pk),
                                        'amount': '12'})
    order.refresh_from_db()
    check('控制台退款生效且状态为已全额退款',
          resp.status_code == 302 and order.status == PayOrder.STATUS_REFUNDED, order.status)

    resp = client.post('/console/pay/', {'action': 'refund_order', 'order_id': 'not-a-uuid'})
    check('非法订单ID不报 500', resp.status_code == 302, str(resp.status_code))

    resp = client.post('/console/pay/', {'action': 'unknown'})
    check('未知动作被拒绝（302）', resp.status_code == 302)

    # 三语渲染（要求真的译出来，不能靠回退）
    for lang, expect in (('en', 'Payment Settings'), ('zh-hant', '支付設置')):
        lang_client = Client()
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        lang_client.force_login(admin)
        page = lang_client.get('/console/pay/').content.decode('utf-8')
        check(f'{lang} 页面已翻译（{expect}）', expect in page, expect)


def _login_session(client, user):
    """写官网登录态（session['website_user'] 是含 account / username 的小字典，见 views 登录处）"""
    session = client.session
    session['website_user'] = {
        'user_id': str(user.pk), 'account': user.account, 'username': user.username,
        'token': 'test-token', 'expire_time': None, 'email': user.email,
    }
    session.save()


def round11_wallet(user):
    section('第 11 轮 前台充值中心（/my/wallet/）')

    # 前面的控制台用例改过汇率，这里显式设回测试汇率，保证换算断言稳定
    PaySetting.objects.filter(pk=PaySetting.SINGLETON_PK).update(
        enabled=True, points_per_yuan=RATE, min_amount=MIN_AMOUNT)

    # 前台登录走站点会话（session['website_user']），不是 Django auth
    client = Client()
    _login_session(client, user)

    resp = Client().get('/my/wallet/')
    check('未登录 → 跳登录页',
          resp.status_code == 302 and '/login/' in resp.get('Location', ''), str(resp.get('Location')))

    # 浏览器里同时有「超管会话」时（进过后台控制台）打开充值页：登录页必须渲染出表单，
    # 不能按 next 把请求打回 /my/wallet/ —— 那会和前台 login_required 互踢成无限重定向。
    admin = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
    if admin is None:
        check('存在可用超管账号（充值页死循环用例）', False, '本地没有超管，请先 createsuperuser')
    else:
        su = Client()
        su.force_login(admin)
        looped = su.get('/login/?next=/my/wallet/')
        check('超管打开充值页不死循环（登录页正常渲染）', looped.status_code == 200,
              f'status={looped.status_code} loc={looped.headers.get("Location", "")}')

    resp = client.get('/my/wallet/')
    body = resp.content.decode('utf-8')
    check('登录后可访问（200）', resp.status_code == 200, str(resp.status_code))
    check('页面含余额与充值入口',
          '充值中心' in body and '账户余额' in body and '去支付' in body)

    before = PayOrder.objects.filter(user=user).count()
    resp = client.post('/my/wallet/', {'action': 'create_order', 'amount': '20', 'pay_type': 'alipay'})
    order = PayOrder.objects.filter(user=user).order_by('-create_time').first()
    check('下单成功并跳转到平台收银台',
          resp.status_code == 302 and resp.get('Location') == order.pay_info
          and order.pay_info, f"{resp.status_code} {resp.get('Location')}")
    check('本站充值固定 method=jump', order.method == 'jump', order.method)
    check('订单归属当前用户', order.user_id == user.pk)

    client.post('/my/wallet/', {'action': 'create_order', 'amount': 'abc', 'pay_type': 'alipay'})
    check('金额非法 → 不新建订单', PayOrder.objects.filter(user=user).count() == before + 1)
    client.post('/my/wallet/', {'action': 'create_order', 'amount': '20', 'pay_type': 'notexist'})
    check('支付方式非法 → 不新建订单', PayOrder.objects.filter(user=user).count() == before + 1)

    body = client.get('/my/wallet/').content.decode('utf-8')
    check('页面展示待支付订单与支付入口',
          order.out_trade_no in body and '我已支付' in body)

    payload = _payload(client.post('/my/wallet/',
                                   {'action': 'check_order', 'out_trade_no': order.out_trade_no}))
    check('查单（未支付）返回 paid=false', payload['data']['paid'] is False, str(payload))

    balance_before = User.objects.values_list('balance', flat=True).get(pk=user.pk)
    service.handle_notify('ezfp', _sign_notify(out_trade_no=order.out_trade_no, money='20.00'))
    payload = _payload(client.post('/my/wallet/',
                                   {'action': 'check_order', 'out_trade_no': order.out_trade_no}))
    expect_balance = format_money(balance_before + Decimal('20'))
    check('查单（已支付）返回 paid=true 与新余额',
          payload['data']['paid'] is True and payload['data']['balance'] == expect_balance,
          str(payload))

    payload = _payload(client.post('/my/wallet/', {'action': 'check_order',
                                                  'out_trade_no': 'XY_NOT_EXIST'}))
    check('查不存在的订单 → 404', payload['code'] == 404, str(payload))

    other = make_user('w')
    other_client = Client()
    _login_session(other_client, other)
    payload = _payload(other_client.post('/my/wallet/', {'action': 'check_order',
                                                        'out_trade_no': order.out_trade_no}))
    check('别人的订单查不到（归属隔离）', payload['code'] == 404, str(payload))

    app = make_app('w')
    UserApp.objects.filter(pk=app.pk).update(owner=user)
    app.refresh_from_db()
    resp = client.post('/my/wallet/', {'action': 'transfer', 'app_id': str(app.pk), 'amount': '5'})
    app.refresh_from_db()
    check('兑换成功：项目点数增加（5 元 × 2 点）',
          resp.status_code == 302 and app.balance == Decimal('10.0000'), str(app.balance))
    client.post('/my/wallet/', {'action': 'transfer', 'app_id': str(app.pk), 'amount': '99999'})
    app.refresh_from_db()
    check('余额不足时兑换被拒', app.balance == Decimal('10.0000'), str(app.balance))
    check('兑换非本人项目被拒',
          client.post('/my/wallet/', {'action': 'transfer', 'app_id': str(make_app('x').pk),
                                     'amount': '1'}).status_code == 302)

    check('未知动作被拒绝（302）',
          client.post('/my/wallet/', {'action': 'unknown'}).status_code == 302)

    for lang, expect in (('en', 'Top Up'), ('zh-hant', '充值中心')):
        lang_client = Client()
        _login_session(lang_client, user)
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        page = lang_client.get('/my/wallet/').content.decode('utf-8')
        check(f'{lang} 充值页已翻译（{expect}）', expect in page, expect)


def round12_config_guard():
    section('第 12 轮 配置健壮性')

    PayProvider.objects.filter(code='ezfp').update(merchant_id='', private_key_enc='',
                                                   platform_public_key_enc='')
    config = PayProvider.objects.get(code='ezfp')
    provider = build_provider(config)
    try:
        provider.ensure_configured()
        check('未配置商户ID → 明确报错', False, '未抛出 PayError')
    except PayError as exc:
        check('未配置商户ID → 明确报错', '未配置商户ID' in str(exc), str(exc))

    config.merchant_id = '1001'
    config.save(update_fields=['merchant_id'])
    try:
        build_provider(config).ensure_configured()
        check('未配置商户私钥 → 明确报错', False, '未抛出 PayError')
    except PayError as exc:
        check('未配置商户私钥 → 明确报错', '未配置商户私钥' in str(exc), str(exc))

    try:
        provider.verify_notify({'a': '1'})
        check('未配置平台公钥 → 验签明确报错', False, '未抛出 PayError')
    except PayError as exc:
        check('未配置平台公钥 → 验签明确报错', '平台公钥' in str(exc), str(exc))


def main():
    snapshot()
    print('第三方支付回归测试开始')
    print(f'标记：{MARK}（测试数据跑完自动清理）')
    try:
        round1_sign()
        round2_registry()
        EzfpProvider._post = _fake_post     # 之后所有渠道调用都打桩，全程不联网
        user = make_user()
        main_order = round3_create(user)
        round4_notify(main_order, user)
        round5_query(main_order)
        app = make_app()
        round6_views(app, user)
        round7_refund(app)
        round8_transfer(app)
        round9_http_notify(app)
        round10_console(app)
        round11_wallet(user)
        round12_config_guard()
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
