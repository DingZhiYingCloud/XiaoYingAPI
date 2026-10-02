"""接入项目「客户自助 + 额度（点数余额）」回归测试

覆盖范围：
    第 1 轮 额度判定（纯逻辑）：余额与单价比较、免费节点、开放接口、默认价兜底
    第 2 轮 中间件拦截（端到端，打真实 /api/ 端点）：余额充足放行、余额不足 30012、
            签名错误仍返回 20011（额度不掩盖认证错误）
    第 3 轮 归属隔离：只能看到 / 打开自己的项目，别人的一律 404
    第 4 轮 自助建项目：空名 / 超长 / 重名被拒；正常创建且归属正确、默认零额度
    第 5 轮 重置密钥：密钥变化、旧密钥立即失效、新密钥可用
    第 6 轮 未登录跳转：匿名访问 302 到登录页并带 next
    第 7 轮 超管控制台：额度页列出项目余额、充值 / 扣回写入流水、非法入参被拒
    第 8 轮 多语言：en / zh-hant 不回退中文

隔离策略：测试用户 / 项目 / 统计行都带随机后缀，结束全部删除；控制台写操作产生的
审计留痕按 max_id 清理；充值流水随项目级联删除；签名 nonce 表按 app_id 清理。

用真实 /api/ 端点做端到端验证：`POST /api/email/v1/send` 只带签名参数、不带业务参数时
会在参数校验阶段直接返回 20001（不发信、不产生任何副作用），因此既能证明「请求确实
走到了业务视图」，又不会造成污染。余额不足时请求在中间件就被拦下，业务根本不会执行。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_projects_quota.py
"""
import json
import os
import secrets
import sys
import time
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.models import Max
from django.test import Client
from django.urls import reverse

from API.apis.user_center.sign import build_sign
from API.common import credit_guard
from API.common.status_code import StatusCode
from API.models import ApiCallStat, AppCreditLedger, ConsoleAuditLog, User, UserApp
from API.models.Credit.price import DEFAULT_PRICE

from _test_support import grant_credit

RUN = str(int(time.time()))
SEND_PATH = '/api/email/v1/send'          # 只带签名参数时返回 20001，无副作用
LIST_URL = 'website:my_projects'
DETAIL_URL = 'website:my_project_detail'
CONSOLE_URL = 'website:console_projects'
CREDITS_URL = 'website:console_credits'

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


def code_of(resp):
    """取响应 JSON 里的业务 code（非 JSON 返回 None）"""
    try:
        return json.loads(resp.content.decode('utf-8')).get('code')
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def make_account(idx):
    """构造唯一且合法的账号（6-12 位纯数字）"""
    return (RUN + str(idx))[-12:]


def make_user(idx, tag):
    return User.objects.create(
        account=make_account(idx), username=f'{tag}_{RUN}',
        password=make_password('xytest-pass'),
    )


def login_website(client, user):
    """直接把官网登录态写进会话（免走真实登录与图形验证）"""
    session = client.session
    session['website_user'] = {
        'user_id': str(user.pk), 'account': user.account, 'username': user.username,
    }
    session.save()


def signed_post(client, app, path, extra=None):
    """按项目签名规则发一次请求（每次新 nonce，避免触发防重放）"""
    params = {'app_id': app.app_id, 'timestamp': str(int(time.time())),
              'nonce': secrets.token_hex(8)}
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app.app_secret)
    return client.post(path, params)


def cleanup(app_ids, user_ids):
    """删除测试数据：统计 → nonce → 项目 → 用户"""
    ApiCallStat.objects.filter(app_id__in=app_ids).delete()
    with connection.cursor() as cur:
        for app_id in app_ids:
            # 注意：Django 的 cursor 用 %s 占位符（不是原生 sqlite3 的 ?）
            cur.execute('DELETE FROM api_nonce WHERE app_id = %s', [app_id])
    UserApp.objects.filter(owner_id__in=user_ids).delete()
    User.objects.filter(pk__in=user_ids).delete()


# ───────────────────────── 第 1 轮：额度判定（纯逻辑） ─────────────────────────

def round1_credit(app):
    section('第 1 轮 额度判定（纯逻辑）')
    set_balance(app, '0')
    check('余额 0 → 不足（按默认单价 1 点判定）',
          credit_guard.insufficient(app, DEFAULT_PRICE) is not None)
    check('不足提示含「额度不足」',
          '额度不足' in (credit_guard.insufficient(app, DEFAULT_PRICE) or ''))
    check('app 为 None（开放接口 / 未认证）→ 放行',
          credit_guard.insufficient(None, DEFAULT_PRICE) is None)
    check('单价 0（免费节点）→ 放行',
          credit_guard.insufficient(app, Decimal('0')) is None)

    set_balance(app, '5')
    check('余额恰好等于单价 → 放行',
          credit_guard.insufficient(app, Decimal('5')) is None)
    check('余额低于单价 → 拦截',
          credit_guard.insufficient(app, Decimal('6')) is not None)

    check('未配置单价时 resolve_price 兜底 DEFAULT_PRICE',
          credit_guard.resolve_price('/api/xytest-not-configured/x') == DEFAULT_PRICE)


def set_balance(app, value):
    """直接改余额（测试专用，不写流水）"""
    UserApp.objects.filter(pk=app.pk).update(balance=Decimal(value))
    app.refresh_from_db(fields=['balance'])
    return app


# ───────────────────────── 第 2 轮：中间件额度拦截（端到端） ─────────────────────────

def round2_middleware(client, app):
    section('第 2 轮 中间件额度拦截（端到端，打真实 /api/ 端点）')

    set_balance(app, '1000')
    resp = signed_post(client, app, SEND_PATH)
    check('余额充足 → 请求进入业务（返回缺参数的 20001，而非 30012）',
          code_of(resp) == StatusCode.PARAM_MISSING, f'code={code_of(resp)}')

    set_balance(app, '0')
    resp = signed_post(client, app, SEND_PATH)
    check('余额为 0 → 中间件返回 30012',
          code_of(resp) == StatusCode.QUOTA_EXCEEDED, f'code={code_of(resp)}')
    # 注意：JsonResponse 默认 ensure_ascii，中文在正文里是 \uXXXX 转义，需解析后再断言
    quota_msg = (json.loads(resp.content.decode('utf-8')).get('msg') or '')
    check('额度不足响应带可读提示', '额度不足' in quota_msg, quota_msg)

    set_balance(app, '0.5')
    resp = signed_post(client, app, SEND_PATH)
    check('余额低于本次单价（0.5 < 1）→ 30012',
          code_of(resp) == StatusCode.QUOTA_EXCEEDED, f'code={code_of(resp)}')

    # 认证失败优先于额度：签名错了仍是 20011，不被 30012 掩盖
    resp = client.post(SEND_PATH, {
        'app_id': app.app_id, 'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8), 'sign': 'deadbeef',
    })
    check('签名错误仍返回 20011（额度不掩盖认证错误）',
          code_of(resp) == StatusCode.AUTH_FAILED, f'code={code_of(resp)}')

    set_balance(app, '1000')
    resp = signed_post(client, app, SEND_PATH)
    check('补足余额 → 请求进入业务', code_of(resp) == StatusCode.PARAM_MISSING,
          f'code={code_of(resp)}')


# ───────────────────────── 第 3 轮：归属隔离 ─────────────────────────

def round3_isolation(user_a, user_b, app_a):
    section('第 3 轮 归属隔离（只能管自己的项目）')

    client_a, client_b = Client(), Client()
    login_website(client_a, user_a)
    login_website(client_b, user_b)

    html = client_a.get(reverse(LIST_URL)).content.decode('utf-8')
    check('本人列表含自己的项目', app_a.name in html)
    check('本人列表有新建入口', 'name="name"' in html)

    html = client_b.get(reverse(LIST_URL)).content.decode('utf-8')
    check('他人列表不含该项目的名称与 APPID',
          app_a.name not in html and app_a.app_id not in html)

    resp = client_a.get(reverse(DETAIL_URL, args=[app_a.pk]))
    check('本人可打开项目详情', resp.status_code == 200, f'status={resp.status_code}')

    resp = client_b.get(reverse(DETAIL_URL, args=[app_a.pk]))
    check('他人访问该项目详情 → 404', resp.status_code == 404, f'status={resp.status_code}')

    resp = client_b.post(reverse(DETAIL_URL, args=[app_a.pk]), {'action': 'reset_secret'})
    check('他人无法重置该项目密钥 → 404', resp.status_code == 404, f'status={resp.status_code}')


# ───────────────────────── 第 4 轮：自助建项目 ─────────────────────────

def round4_create(user_a):
    section('第 4 轮 自助创建项目')
    client = Client()
    login_website(client, user_a)
    url = reverse(LIST_URL)
    before = UserApp.objects.filter(owner=user_a).count()

    client.post(url, {'action': 'create', 'name': '   '})
    check('空名称被拒', UserApp.objects.filter(owner=user_a).count() == before)

    client.post(url, {'action': 'create', 'name': 'x' * 101})
    check('超长名称被拒', UserApp.objects.filter(owner=user_a).count() == before)

    resp = client.post(url, {'action': 'create', 'name': f'重名-{RUN}'})
    check('首次创建成功（302 跳详情）', resp.status_code == 302, f'status={resp.status_code}')
    created = UserApp.objects.filter(owner=user_a, name=f'重名-{RUN}').first()
    check('创建后归属为当前用户', created is not None and created.owner_id == user_a.pk)
    check('自动生成了 APPID 与 APPSECRET',
          bool(created and created.app_id and created.app_secret))
    check('新项目默认零额度（什么都调不了，需管理员充值）',
          created is not None and created.balance == 0)
    check('新项目默认启用', created is not None and created.status is True)

    client.post(url, {'action': 'create', 'name': f'重名-{RUN}'})
    check('重名被拒（数量不变）',
          UserApp.objects.filter(name=f'重名-{RUN}').count() == 1)

    client.post(url, {'action': 'nope'})
    check('未知动作不影响数据', UserApp.objects.filter(owner=user_a).count() >= before + 1)
    # 后面几轮要打真实 /api/ 接口，先补一笔额度（否则会先被 30012 拦住）
    grant_credit(created)
    return created


# ───────────────────────── 第 5 轮：重置密钥 ─────────────────────────

def round5_reset(user_a, app):
    section('第 5 轮 重置密钥')
    client = Client()
    login_website(client, user_a)
    url = reverse(DETAIL_URL, args=[app.pk])

    resp = client.get(url)
    html = resp.content.decode('utf-8')
    check('详情页下发 APPID 与密钥明文（打码展示）',
          app.app_id in html and app.app_secret in html)
    check('密钥默认不显示（打码态）',
          'data-secret-real hidden' in html and 'data-secret-masked' in html)

    old_secret = app.app_secret
    resp = client.post(url, {'action': 'reset_secret'})
    check('重置返回 302', resp.status_code == 302, f'status={resp.status_code}')
    app.refresh_from_db()
    check('密钥已变化', app.app_secret != old_secret)

    resp = signed_post(client, app, SEND_PATH)      # 用新密钥签名
    check('新密钥可用（进入业务）', code_of(resp) == StatusCode.PARAM_MISSING,
          f'code={code_of(resp)}')

    params = {'app_id': app.app_id, 'timestamp': str(int(time.time())),
              'nonce': secrets.token_hex(8)}
    params['sign'] = build_sign(params, old_secret)  # 旧密钥签名
    resp = client.post(SEND_PATH, params)
    check('旧密钥立即失效（20011）', code_of(resp) == StatusCode.AUTH_FAILED,
          f'code={code_of(resp)}')


# ───────────────────────── 第 6 轮：未登录跳转 ─────────────────────────

def round6_anonymous():
    section('第 6 轮 未登录访问跳登录页')
    resp = Client().get(reverse(LIST_URL))
    check('匿名访问列表 → 302', resp.status_code == 302, f'status={resp.status_code}')
    location = resp.headers.get('Location', '')
    check('跳转目标含登录页与 next 回跳',
          '/login/' in location and 'next=' in location, location)

    # 浏览器同时持有「超管会话」时访问前台页：登录页绝不能按 next 把请求打回前台页，
    # 否则与前台 login_required 互踢 → ERR_TOO_MANY_REDIRECTS（前台页永远打不开）。
    admin = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
    if admin is None:
        check('存在可用超管账号（超管死循环用例）', False, '本地没有超管，请先 createsuperuser')
        return
    su = Client()
    su.force_login(admin)
    first = su.get(reverse(LIST_URL))
    check('超管访问前台页 → 仍 302 到登录页', first.status_code == 302, str(first.status_code))
    looped = su.get(f'/login/?next={reverse(LIST_URL)}')
    check('登录页不再回跳前台页（不死循环）', looped.status_code == 200,
          f'status={looped.status_code} loc={looped.headers.get("Location", "")}')
    check('登录页渲染出登录表单', 'id="login-account"' in looped.content.decode('utf-8'))


# ───────────────────────── 第 7 轮：超管控制台（额度） ─────────────────────────

def round7_console(app):
    section('第 7 轮 超管控制台（项目余额 + 充值 / 扣回 + 流水）')
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    if admin is None:
        check('存在可用超管账号（跳过本轮）', False, '本地没有超管，请先 createsuperuser')
        return
    client = Client()
    client.force_login(admin)

    # 项目页展示余额并给「去充值」入口
    html = client.get(reverse(CONSOLE_URL)).content.decode('utf-8')
    check('接入项目页展示归属', '归属：' in html)
    check('接入项目页展示额度余额与充值入口',
          '额度余额：' in html and reverse(CREDITS_URL) in html)
    check('接入项目页不再有日/月配额输入',
          'name="daily_limit"' not in html and 'name="monthly_limit"' not in html)

    url = reverse(CREDITS_URL)
    html = client.get(url).content.decode('utf-8')
    check('额度页列出项目与余额', app.name in html and app.app_id in html)
    check('额度页含充值表单', 'name="amount"' in html and 'name="remark"' in html)

    set_balance(app, '1000')
    before = Decimal('1000')

    resp = client.post(url, {'action': 'recharge', 'id': str(app.pk), 'amount': '2500.5',
                             'remark': f'测试充值-{RUN}'})
    app.refresh_from_db()
    check('充值成功（余额增加）',
          resp.status_code == 302 and app.balance == before + Decimal('2500.5'),
          f'balance={app.balance}')
    ledger = AppCreditLedger.objects.filter(app=app).order_by('-create_time').first()
    check('充值写入流水（金额 / 调整后余额 / 操作人 / 备注）',
          ledger is not None and ledger.amount == Decimal('2500.5')
          and ledger.balance_after == app.balance
          and bool(ledger.operator) and ledger.remark == f'测试充值-{RUN}',
          f'ledger={ledger!r}')

    client.post(url, {'action': 'recharge', 'id': str(app.pk), 'amount': '-500'})
    app.refresh_from_db()
    check('负数 = 扣回（纠错用）', app.balance == before + Decimal('2000.5'),
          f'balance={app.balance}')

    client.post(url, {'action': 'recharge', 'id': str(app.pk), 'amount': '0'})
    app.refresh_from_db()
    check('金额为 0 被拒（不落库）', app.balance == before + Decimal('2000.5'))

    client.post(url, {'action': 'recharge', 'id': str(app.pk), 'amount': 'abc'})
    app.refresh_from_db()
    check('非法金额被拒（不落库）', app.balance == before + Decimal('2000.5'))

    resp = client.post(url, {'action': 'recharge', 'id': 'not-a-uuid', 'amount': '1'})
    check('非法项目 id 被拒且不 500', resp.status_code == 302, f'status={resp.status_code}')

    resp = client.post(url, {'action': 'nope', 'id': str(app.pk), 'amount': '1'})
    app.refresh_from_db()
    check('未知动作不改变余额', resp.status_code == 302 and app.balance == before + Decimal('2000.5'))

    # 非超管访问额度页被拦（隐身开启时 404）
    resp = Client().get(url)
    check('匿名访问额度页被拦（404 / 302）', resp.status_code in (302, 404),
          f'status={resp.status_code}')


# ───────────────────────── 第 8 轮：多语言 ─────────────────────────

def round8_i18n(user_a):
    section('第 8 轮 多语言（en / zh-hant 不回退中文）')
    client = Client()
    login_website(client, user_a)
    url = reverse(LIST_URL)

    html = client.get(url, HTTP_ACCEPT_LANGUAGE='en').content.decode('utf-8')
    flags = {
        'title': 'My Projects' in html,
        'create': 'Create Project' in html,
        'no_zh': '我的项目' not in html and '创建项目' not in html,
        'no_tag': '{%' not in html and '{{' not in html,
    }
    check('英文页已翻译（无中文回退 / 无模板标记泄漏）', all(flags.values()), f'{flags}')

    # 「项目」繁体写作「項目」（zhconv 口径），断言用繁体字形
    html = client.get(url, HTTP_ACCEPT_LANGUAGE='zh-hant').content.decode('utf-8')
    flags = {'title': '我的項目' in html, 'create': '創建項目' in html}
    check('繁体页已翻译（无简体回退）', all(flags.values()), f'{flags}')


def main():
    audit_max_id = ConsoleAuditLog.objects.aggregate(m=Max('id'))['m'] or 0
    user_a = make_user(1, 'xyq_a')
    user_b = make_user(2, 'xyq_b')
    app_a = UserApp.objects.create(name=f'额度测试项目-{RUN}', owner=user_a)
    app_ids, user_ids = [], [user_a.pk, user_b.pk]
    created_extra = []

    try:
        app_ids.append(app_a.app_id)

        round1_credit(app_a)

        client = Client()
        login_website(client, user_a)
        round2_middleware(client, app_a)

        round3_isolation(user_a, user_b, app_a)
        extra = round4_create(user_a)
        if extra is not None:
            created_extra.append(extra)
            app_ids.append(extra.app_id)
        round5_reset(user_a, app_a)
        round6_anonymous()
        round7_console(app_a)
        round8_i18n(user_a)
    finally:
        for item in created_extra:
            ApiCallStat.objects.filter(app_id=item.app_id).delete()
        cleanup(app_ids, user_ids)
        ConsoleAuditLog.objects.filter(id__gt=audit_max_id).delete()
        print('\n测试数据已清理（项目 / 额度流水 / 统计 / nonce / 用户 / 审计留痕）')

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
