"""API 服务策略（服务 / 线路 / 端点三级继承）回归测试

覆盖范围：
    第 1 轮 fail-closed：未命中任何策略的 /api/ 路径 → 需要签名，匿名 20011
    第 2 轮 开放节点：迁移写入的 /api/captcha_self/ 与 /api/captcha_auth/aliyun/ 仍开放
    第 3 轮 三级继承（认证）：服务级 open 向上继承；端点级 auth 覆盖服务级
    第 4 轮 状态继承 + 「只有正常可调用」：maintenance→30004 / offline→30005 / dev→30006
             一律硬拦截（含合法签名），端点级 normal 可覆盖上层状态恢复可调用
    第 5 轮 额度与单价继承：服务级单价 → 端点级覆写（0=免费 / 抬高）；余额不足返 30012；
             未配置单价时兜底 DEFAULT_PRICE
    第 6 轮 前缀边界：/api/foo 的策略不得命中 /api/foobar/...
    第 7 轮 缓存失效：改 status / auth_mode / price 后立即生效，不必等 TTL
    第 8 轮 控制台页面：未登录跳转、超管可访问、含三级联动数据、增删改各自生效
    第 9 轮 三语（zh-hans / zh-hant / en）页面正常渲染且关键词已翻译
    第 10 轮 服务树枚举自证（真实路由 vs 文档注册表）
    第 11 轮 前台状态图标：四态图标唯一、服务项与线路子项字段齐备、线路状态取端点最严重、
             渲染无空图标名、图例与文档页线路 Tab 均带图标
    第 12 轮 文档可见性 / 使用范围：两字段三级继承、admin_only 对外 20020（状态拦截优先）、
             docs_visible=hidden 从 /docs/ 目录、文档页、左侧菜单与在线调试中消失
    第 13 轮 线路多选：一条策略覆盖多条线路（extra_prefixes）全部生效；编辑可增删线路；
             线路被另一条策略接管时「让位」（部分让位保留其余、全部让位则删除）
    第 14 轮 批量删除：列表页勾选框 + 批量删除表单；未勾选被拒、只删勾选项、非法 id 忽略
    第 15 轮 建议策略：清单与迁移写入的 9 条逐条一致、后台「一键新建建议策略」预览面板、
             只补缺失 / 可反复执行 / 不覆盖已有、管理命令 --dry-run、stream 免签代码兜底

隔离策略：测试数据用 MARK（xysvcpolicy<RUN>）标记，策略路径前缀一律包含 MARK，
测试结束统一删除。另有两轮的例外，均不残留：
- 第 12 轮为了验证「文档隐藏」在真实文档页 / 在线调试上的效果，会临时给一个真实端点
  建策略（前置检查该前缀原本无策略，`finally` 里必删）；
- 第 15 轮为了验证建议策略的新建 / 不覆盖语义，会在**事务里**改动真实策略，结束整体回滚。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_service_policy.py
"""
import io
import json
import os
import re
import secrets
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import Client
from django.urls import resolve, reverse

from API.apis.user_center.sign import build_sign
from API.common import StatusCode
from API.common.credit_guard import (
    invalidate_api_price_cache,
    resolve_price,
)
from API.common.middleware import (
    invalidate_api_service_policy_cache,
    is_admin_only,
    is_docs_hidden,
    requires_auth,
    resolve_service_policy,
)
from API.models import ApiPricePolicy, ApiServicePolicy, SecuritySetting, UserApp
from API.models.Credit.price import DEFAULT_PRICE
from API.website.docs.menu import build_docs_menu
from API.website.service_presets import apply_presets, preset_rows
from API.website.service_status import (
    STATUS_DEFS,
    UNCLICKABLE_STATUSES,
    channel_status_fields,
    worst_status,
)
from API.website.service_tree import service_tree

from _test_support import grant_credit

# 建议策略清单里挑一条真实前缀做「新建 / 不覆盖 / 免签兜底」的验证对象。
# 这些操作都在事务里做、结束整体回滚（见 round15），不改动库里的真实配置。
PRESET_TARGET = '/api/dramas/hongguo/stream'

RUN = str(int(time.time()))
MARK = f'xysvcpolicy{RUN}'
BASE = f'/api/{MARK}'  # 测试用（不存在的）路径前缀，不会与真实服务冲突


def svc(name):
    """服务级前缀：/api/<MARK><name>/（深度 1，与 clean() 的形状校验一致）"""
    return f'{BASE}{name}/'

# 迁移写入的开放节点（登录/注册页图形验证码）
CAPTCHA_OPEN_PATHS = ('/api/captcha_self/generate', '/api/captcha_auth/aliyun/config')

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


def _json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def _code(resp):
    return _json(resp).get('code')


def _signed(app, extra=None):
    """构造带合法签名的请求参数"""
    params = {
        'app_id': app.app_id,
        'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    params.update(extra or {})
    params['sign'] = build_sign(params, app.app_secret)
    return params


def _mk_app(tag):
    app = UserApp.objects.create(name=f'SvcApp{MARK}{tag}')
    # 授权模型是「额度」：新项目默认 0 点，签名通过后会被 30012 拦掉、到不了业务层，
    # 而本脚本多处要验证「签名通过后落到路由/状态判定」，故先补一笔额度
    return grant_credit(app)


def _mk_policy(**kwargs):
    """建策略（不触发模型 clean，等价于 DDL 直建；用于构造各种继承场景）"""
    return ApiServicePolicy.objects.create(**kwargs)


def _mk_price(path_prefix, level, price):
    """建一条调用单价（独立于服务策略的 ApiPricePolicy，行存在 = 显式设价）"""
    return ApiPricePolicy.objects.create(path_prefix=path_prefix, level=level, price=price)


def superadmin_client():
    """返回 (已登录超管的客户端, 超管对象, 是否临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(
            username=f'xytest_svc_{RUN}', email=f'xytest.svc.{RUN}@example.com',
            password='xytest-admin-pass')
        created = True
    client = Client()
    client.force_login(admin)
    return client, admin, created


def cleanup():
    """删除全部测试数据（策略 / 单价 的路径前缀包含 MARK 即删，含 extra_prefixes）"""
    ids = [p.pk for p in ApiServicePolicy.objects.all()
           if any(MARK in prefix for prefix in p.all_prefixes)]
    ApiServicePolicy.objects.filter(pk__in=ids).delete()
    ApiPricePolicy.objects.filter(path_prefix__contains=MARK).delete()
    UserApp.objects.filter(name__contains=MARK).delete()
    invalidate_api_service_policy_cache()
    invalidate_api_price_cache()


# ───────────────────────── 第 1 轮：fail-closed ─────────────────────────

def round1_fail_closed():
    section('第 1 轮 fail-closed（未命中任何策略 → 需要签名）')
    app = _mk_app('A')
    anon = Client()
    path = f'{BASE}/unmatched/probe'
    check('未命中策略的路径判定为「需要签名」', requires_auth(path) is True)
    resp = anon.get(path)
    check('匿名请求返回 20011', _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')
    resp = anon.get(path, _signed(app))
    check('携带合法签名后放行（落到未匹配路由 20030）',
          _code(resp) == StatusCode.NOT_FOUND, f'code={_code(resp)}')
    return app


# ───────────────────────── 第 2 轮：开放节点 ─────────────────────────

def round2_captcha_open():
    section('第 2 轮 开放节点（迁移写入的两个 captcha 策略仍开放）')
    for prefix in ('/api/captcha_self/', '/api/captcha_auth/aliyun/'):
        policy = ApiServicePolicy.objects.filter(path_prefix=prefix).first()
        check(f'迁移写入服务级策略 {prefix}', policy is not None and policy.level == 'service'
              and policy.auth_mode == 'open' and policy.status == 'normal',
              f'policy={policy!r}')
    anon = Client()
    for path in CAPTCHA_OPEN_PATHS:
        check(f'{path} 判定为开放（不需要签名）', requires_auth(path) is False)
        resp = anon.get(path)
        check(f'{path} 匿名请求未被签名拦截', _code(resp) != StatusCode.AUTH_FAILED,
              f'code={_code(resp)}')


# ───────────────────────── 第 3 轮：三级继承（认证） ─────────────────────────

def round3_auth_inherit():
    section('第 3 轮 三级继承（认证模式：服务 open → 线路/端点继承；端点 auth 覆盖）')
    _mk_policy(name=f'SvcOpen {MARK}', level='service', path_prefix=f'{BASE}open/',
               auth_mode='open', status='inherit')

    check('线路级未设 → 继承服务级开放',
          requires_auth(f'{BASE}open/ch/any') is False)
    check('端点级未设 → 继承服务级开放',
          requires_auth(f'{BASE}open/ch/ep') is False)

    _mk_policy(name=f'EpAuth {MARK}', level='endpoint', path_prefix=f'{BASE}open/ch/ep',
               auth_mode='auth', status='inherit')
    check('端点级 auth 覆盖服务级 open', requires_auth(f'{BASE}open/ch/ep') is True)
    check('同服务其他端点仍继承开放', requires_auth(f'{BASE}open/ch/other') is False)

    anon = Client()
    resp = anon.get(f'{BASE}open/ch/ep')
    check('端点级 auth 的匿名请求返回 20011',
          _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}open/ch/other')
    check('继承开放的端点匿名不被拦截', _code(resp) != StatusCode.AUTH_FAILED, f'code={_code(resp)}')


# ───────────────────────── 第 4 轮：状态继承 ─────────────────────────

def round4_status_inherit():
    section('第 4 轮 状态继承与状态拦截（只有 normal 可调用）')
    _mk_policy(name=f'SvcMaint {MARK}', level='service', path_prefix=f'{BASE}maint/',
               status='maintenance', auth_mode='inherit')
    check('服务级维护态生效', resolve_service_policy(f'{BASE}maint/x')['status'] == 'maintenance')

    anon = Client()
    resp = anon.get(f'{BASE}maint/x')
    check('服务下任意请求返回 30004', _code(resp) == StatusCode.SERVICE_MAINTENANCE,
          f'code={_code(resp)}')

    app = _mk_app('M')
    resp = anon.get(f'{BASE}maint/x', _signed(app))
    check('携带合法签名仍返回 30004（未做签名校验）',
          _code(resp) == StatusCode.SERVICE_MAINTENANCE, f'code={_code(resp)}')

    _mk_policy(name=f'EpNormal {MARK}', level='endpoint', path_prefix=f'{BASE}maint/ok',
               status='normal', auth_mode='inherit')
    check('端点级 normal 覆盖服务级维护态',
          resolve_service_policy(f'{BASE}maint/ok')['status'] == 'normal')
    resp = anon.get(f'{BASE}maint/ok')
    check('该端点不再返回维护码（落到 20011）',
          _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')

    # 已下线（offline）同样硬拦截，且用独立业务码 30005，便于调用方与「维护中」区分
    _mk_policy(name=f'SvcOffline {MARK}', level='service', path_prefix=f'{BASE}offline/',
               status='offline', auth_mode='inherit')
    check('服务级已下线生效',
          resolve_service_policy(f'{BASE}offline/x')['status'] == 'offline')
    resp = anon.get(f'{BASE}offline/x')
    check('已下线服务返回 30005（不是 30004）',
          _code(resp) == StatusCode.SERVICE_OFFLINE, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}offline/x', _signed(_mk_app('O')))
    check('已下线：携带合法签名仍返回 30005（未做签名校验）',
          _code(resp) == StatusCode.SERVICE_OFFLINE, f'code={_code(resp)}')
    _mk_policy(name=f'EpNormalOffline {MARK}', level='endpoint',
               path_prefix=f'{BASE}offline/ok',
               status='normal', auth_mode='inherit')
    resp = anon.get(f'{BASE}offline/ok')
    check('端点级 normal 覆盖服务级已下线（落到 20011）',
          _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')

    # 「开发中」同样硬拦截（口径：只有 normal 可调用），用独立业务码 30006
    _mk_policy(name=f'SvcDev {MARK}', level='service', path_prefix=f'{BASE}dev/',
               status='dev', auth_mode='inherit')
    check('服务级开发中生效',
          resolve_service_policy(f'{BASE}dev/x')['status'] == 'dev')
    resp = anon.get(f'{BASE}dev/x')
    check('开发中服务返回 30006（不是 20011）',
          _code(resp) == StatusCode.SERVICE_DEVELOPING, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}dev/x', _signed(_mk_app('V')))
    check('开发中：携带合法签名仍返回 30006（未做签名校验）',
          _code(resp) == StatusCode.SERVICE_DEVELOPING, f'code={_code(resp)}')
    _mk_policy(name=f'EpNormalDev {MARK}', level='endpoint', path_prefix=f'{BASE}dev/ok',
               status='normal', auth_mode='inherit')
    resp = anon.get(f'{BASE}dev/ok')
    check('端点级 normal 覆盖服务级开发中（恢复可调用，落到 20011）',
          _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')


# ───────────────────────── 第 5 轮：额度与单价继承 ─────────────────────────

def round5_credit_inherit(app_a, app_b):
    section('第 5 轮 额度与单价继承（独立价格表：服务级 → 端点级覆写；余额不足 30012）')
    # 服务级单价 5 点（写在独立的 ApiPricePolicy 上，与服务策略解耦）
    _mk_price(f'{BASE}wl/', 'service', 5)
    UserApp.objects.filter(pk=app_b.pk).update(balance=0)

    check('服务级单价生效（端点未设时继承）',
          resolve_price(f'{BASE}wl/probe') == 5)
    check('同服务其它路径单价一致',
          resolve_price(f'{BASE}wl/other') == 5)

    anon = Client()
    resp = anon.get(f'{BASE}wl/probe')
    check('未签名被拒（20011）', _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}wl/probe', _signed(app_a))
    check('余额充足的项目通过（落到 20030）',
          _code(resp) == StatusCode.NOT_FOUND, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}wl/probe', _signed(app_b))
    check('余额为 0 的项目返回 30012',
          _code(resp) == StatusCode.QUOTA_EXCEEDED, f'code={_code(resp)}')

    # 端点级单价覆写：把该端点单价设为 0（免费）→ 零余额项目也能过
    _mk_price(f'{BASE}wl/free', 'endpoint', 0)
    check('端点级单价覆盖服务级（0 = 免费）',
          resolve_price(f'{BASE}wl/free') == 0)
    check('服务级其余路径仍按 5 点',
          resolve_price(f'{BASE}wl/other') == 5)
    resp = anon.get(f'{BASE}wl/free', _signed(app_b))
    check('免费端点：零余额项目也能通过（落到 20030）',
          _code(resp) == StatusCode.NOT_FOUND, f'code={_code(resp)}')

    # 端点级抬高单价：余额 10 点的项目在 50 点的端点上被拒、在 5 点的路径上放行
    _mk_price(f'{BASE}wl/pricey', 'endpoint', 50)
    UserApp.objects.filter(pk=app_b.pk).update(balance=10)
    check('端点级单价 50 覆盖服务级 5',
          resolve_price(f'{BASE}wl/pricey') == 50)
    resp = anon.get(f'{BASE}wl/pricey', _signed(app_b))
    check('余额不足本次单价 → 30012',
          _code(resp) == StatusCode.QUOTA_EXCEEDED, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}wl/other', _signed(app_b))
    check('同一项目在低单价路径上放行（余额够付）',
          _code(resp) == StatusCode.NOT_FOUND, f'code={_code(resp)}')

    # 线路级单价：服务级 5 → 线路级 8（端点未设时取线路级）
    _mk_price(f'{BASE}wl/ch/', 'channel', 8)
    check('线路级单价覆盖服务级',
          resolve_price(f'{BASE}wl/ch/probe') == 8)
    check('线路级不影响同服务其它线路',
          resolve_price(f'{BASE}wl/other') == 5)

    # 未配置任何单价 → 兜底 DEFAULT_PRICE（保证「零额度什么都调不了」没有缺口）
    check('未配置单价时兜底为 DEFAULT_PRICE',
          resolve_price(f'{BASE}unpriced/x') == DEFAULT_PRICE)


# ───────────────────────── 第 6 轮：前缀边界 ─────────────────────────

def round6_prefix_boundary():
    section('第 6 轮 前缀边界（/api/foo 不得命中 /api/foobar）')
    foo_prefix = f'{BASE}foo'
    _mk_policy(name=f'Boundary {MARK}', level='channel', path_prefix=foo_prefix,
               auth_mode='open', status='inherit')

    check('精确匹配 /api/<MARK>foo 命中', requires_auth(f'{BASE}foo') is False)
    check('子路径 /api/<MARK>foo/child 命中', requires_auth(f'{BASE}foo/child') is False)
    check('/api/<MARK>foobar 不被命中（仍需要签名）',
          requires_auth(f'{BASE}foobar/x') is True)
    check('/api/<MARK>foobar/child 不被命中（仍需要签名）',
          requires_auth(f'{BASE}foobar') is True)

    anon = Client()
    check('越界路径匿名请求返回 20011',
          _code(anon.get(f'{BASE}foobar/x')) == StatusCode.AUTH_FAILED)


# ───────────────────────── 第 7 轮：缓存失效 ─────────────────────────

def round7_cache_invalidation(app_c):
    section('第 7 轮 缓存失效（改动立即生效，无需等 TTL）')
    policy = _mk_policy(name=f'Cache {MARK}', level='service', path_prefix=f'{BASE}cache/',
                        auth_mode='open', status='normal')
    check('初始开放（并已填充缓存）', requires_auth(f'{BASE}cache/probe') is False)

    policy.auth_mode = 'auth'
    policy.save(update_fields=['auth_mode', 'updated_time'])
    check('改 auth_mode 后立即生效', requires_auth(f'{BASE}cache/probe') is True)

    policy.status = 'maintenance'
    policy.save(update_fields=['status', 'updated_time'])
    check('改 status 后立即生效',
          resolve_service_policy(f'{BASE}cache/probe')['status'] == 'maintenance')

    # 单价改动同样即时生效（额度判定读的是独立价格表 + 它的进程内缓存）
    # 先把状态恢复「正常」，否则请求会先被维护态 30004 拦下、测不到额度拦截
    policy.status = 'normal'
    policy.save(update_fields=['status', 'updated_time'])
    UserApp.objects.filter(pk=app_c.pk).update(balance=1)
    price_row = _mk_price(f'{BASE}cache/', 'service', 100)
    check('新增单价后立即生效（缓存已失效）',
          resolve_price(f'{BASE}cache/probe') == 100)
    check('余额 1 点付不起 100 点 → 被额度拦下', not _allowed(f'{BASE}cache/probe', app_c))
    price_row.price = 1
    price_row.save(update_fields=['price', 'updated_time'])
    check('单价降到 1 点后立即放行', _allowed(f'{BASE}cache/probe', app_c))

    invalidate_api_service_policy_cache()
    invalidate_api_price_cache()
    check('显式失效函数可用', isinstance(requires_auth(f'{BASE}cache/probe'), bool))


def _allowed(path, app):
    """签名后是否放行（未被额度拒绝）"""
    anon = Client()
    resp = anon.get(path, _signed(app))
    return _code(resp) != StatusCode.QUOTA_EXCEEDED


# ───────────────────────── 第 8 轮：控制台页面 ─────────────────────────

def round8_console(client, app_a):
    section('第 8 轮 控制台页面与增删改（/console/services/）')
    url = reverse('website:console_services')
    # 默认「后台入口隐身」开启 → 匿名一律 404（与不存在的地址无差别）；关掉隐身才 302。
    # 写死 302 会在默认配置下恒失败（与 test_console_audit.py 同口径）。
    denied = 404 if SecuritySetting.get_solo().hide_console else 302
    check('匿名访问被拦（隐身 404 / 否则 302）', Client().get(url).status_code == denied)

    resp = client.get(url)
    body = resp.content.decode()
    check('超管可访问（200）', resp.status_code == 200, f'status={resp.status_code}')
    check('页面内联三级联动枚举数据（json_script）',
          'service_tree_data' in body and 'service_levels' in body)
    check('三级下拉与自动推导控件存在',
          'data-tree-service' in body and 'data-tree-channel' in body
          and 'data-tree-endpoint' in body and 'data-tree-prefix' in body)
    check('线路为多选下拉（name=channels 且 multiple）',
          'name="channels"' in body and 'data-tree-channel multiple' in body)
    check('菜单高亮「服务策略」', 'menu-active' in body and url in body)
    bad = re.findall(r'onclick="[\w$]*-[\w$-]*\.(?:showModal|close)\(', body)
    check('无「连字符 id」的对话框入口', not bad, f'bad={bad}')

    # 新建（服务级）
    prefix = f'{BASE}console/'
    resp = client.post(url, {'action': 'create', 'name': f'Console {MARK}',
                             'service': prefix, 'status': 'normal', 'auth_mode': 'auth',
                             'docs_visible': 'hidden',
                             'audience': 'admin_only', 'remark': 'created'})
    policy = ApiServicePolicy.objects.filter(path_prefix=prefix).first()
    check('视图新建策略成功（层级自动推导为服务级）',
          resp.status_code == 302 and policy is not None and policy.level == 'service')
    check('新建时保存了文档可见性 / 使用范围',
          policy is not None and policy.docs_visible == 'hidden'
          and policy.audience == 'admin_only')
    check('新建后立即生效（需要认证）', requires_auth(f'{prefix}probe') is True)
    check('服务策略表单已无单价输入（单价已迁到「线路价格」页）',
          'name="price"' not in body)

    # 编辑（改为线路级 open）
    channel = f'{BASE}console/ch/'
    resp = client.post(url, {'action': 'edit', 'id': str(policy.pk), 'name': f'Console2 {MARK}',
                             'service': prefix, 'channels': [channel], 'status': 'normal',
                             'auth_mode': 'open', 'docs_visible': 'visible',
                             'audience': 'normal', 'remark': 'edited'})
    policy.refresh_from_db()
    check('编辑生效（层级推导为线路级 / 模式 / 备注）',
          resp.status_code == 302 and policy.level == 'channel'
          and policy.path_prefix == channel and policy.auth_mode == 'open'
          and policy.remark == 'edited')
    check('编辑生效（文档可见性 / 使用范围）',
          policy.docs_visible == 'visible' and policy.audience == 'normal')
    check('编辑后认证模式立即生效（开放）', requires_auth(f'{channel}probe') is False)

    # 表单校验
    client.post(url, {'action': 'create', 'name': '', 'service': prefix,
                      'status': 'normal', 'auth_mode': 'auth',
                      'docs_visible': 'inherit', 'audience': 'inherit'})
    check('缺少名称被拒且不新建',
          ApiServicePolicy.objects.filter(path_prefix=channel).count() == 1)
    client.post(url, {'action': 'create', 'name': 'bad', 'service': 'no-slash',
                      'status': 'normal', 'auth_mode': 'auth',
                      'docs_visible': 'inherit', 'audience': 'inherit'})
    check('非法服务被拒', not ApiServicePolicy.objects.filter(name='bad').exists())
    client.post(url, {'action': 'create', 'name': 'badfield', 'service': f'{BASE}badfield/',
                      'status': 'normal', 'auth_mode': 'auth',
                      'docs_visible': 'whatever', 'audience': 'inherit'})
    check('非法文档可见性被拒', not ApiServicePolicy.objects.filter(name='badfield').exists())

    # 选中已被占用的线路：原策略让位，由新策略接管（不是报错拒绝）
    old_pk = policy.pk
    resp = client.post(url, {'action': 'create', 'name': f'Takeover {MARK}',
                             'service': prefix, 'channels': [channel],
                             'status': 'normal', 'auth_mode': 'auth',
                             'docs_visible': 'inherit', 'audience': 'inherit'})
    policy = ApiServicePolicy.objects.filter(path_prefix=channel).first()
    check('选中已占用线路 → 原策略让位、新策略接管',
          resp.status_code == 302 and policy is not None
          and policy.name == f'Takeover {MARK}'
          and not ApiServicePolicy.objects.filter(pk=old_pk).exists())
    check('接管后该线路按新策略生效（需要认证）',
          requires_auth(f'{channel}probe') is True)

    # 启停切换（维护态）
    resp = client.post(url, {'action': 'toggle', 'id': str(policy.pk)})
    policy.refresh_from_db()
    check('停用即置维护态', resp.status_code == 302 and policy.status == 'maintenance')
    check('维护态对请求生效',
          resolve_service_policy(f'{channel}probe')['status'] == 'maintenance')
    resp = client.post(url, {'action': 'toggle', 'id': str(policy.pk)})
    policy.refresh_from_db()
    check('再次切换恢复启用', resp.status_code == 302 and policy.status == 'normal')

    # 删除
    resp = client.post(url, {'action': 'delete', 'id': str(policy.pk)})
    check('删除生效', resp.status_code == 302
          and not ApiServicePolicy.objects.filter(pk=policy.pk).exists())


# ───────────────────────── 第 9 轮：多语言 ─────────────────────────

def round9_i18n(client, admin):
    section('第 9 轮 三语渲染（zh-hans / zh-hant / en）')
    url = reverse('website:console_services')
    resp = client.get(url)
    text = resp.content.decode()
    check('简体页面正常渲染且含「服务策略」',
          resp.status_code == 200 and '服务策略' in text)

    for lang, must, extras in (
            ('en', 'Service Policies',
             ('Docs Visibility', 'Audience', 'Channel (multi-select', 'Hold Ctrl / Cmd')),
            ('zh-hant', '服務策略',
             ('文檔可見性', '使用範圍', '線路（可多選', '按住 Ctrl / Cmd 可多選'))):
        lang_client = Client()
        lang_client.force_login(admin)
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        resp = lang_client.get(url)
        text = resp.content.decode()
        check(f'{lang} 页面渲染成功且关键词已翻译',
              resp.status_code == 200 and must in text, f'status={resp.status_code}')
        missing = [word for word in extras if word not in text]
        check(f'{lang} 新配置项文案已翻译（文档可见性 / 使用范围）', not missing,
              f'missing={missing}')


# ───────────────────────── 第 10 轮：枚举模块自证 ─────────────────────────

def round10_service_tree():
    section('第 10 轮 服务树枚举自证（真实路由 vs 文档注册表）')
    tree = service_tree()
    check('枚举到服务', len(tree) > 10, f'services={len(tree)}')

    endpoints = [ep for svc in tree for ch in svc['channels'] for ep in ch['endpoints']]
    check('枚举到端点', len(endpoints) > 50, f'endpoints={len(endpoints)}')

    unresolved = [ep['path'] for ep in endpoints if not _resolve_ok(ep['path'])]
    check('所有端点路径均为真实路由（django.urls.resolve 通过）', not unresolved,
          f'unresolved={unresolved[:5]}')

    shaped = [svc['prefix'] for svc in tree
              if not svc['prefix'].startswith('/api/') or not svc['prefix'].endswith('/')]
    check('服务前缀均为 /api/xxx/ 形式', not shaped, f'bad={shaped[:5]}')

    # 参数段截断：确认没有端点路径再含 <...>
    dirty = [ep['path'] for ep in endpoints if '<' in ep['path']]
    check('端点路径已截断参数段（不含 <...>）', not dirty, f'dirty={dirty[:5]}')

    known = {ep['path'] for ep in endpoints}
    check('关键端点存在（/api/movies/movie_555/detail）',
          '/api/movies/movie_555/detail' in known)
    check('关键端点存在（/api/user_center/users/login）',
          '/api/user_center/users/login' in known)

    movies = next((svc for svc in tree if svc['slug'] == 'movies'), None)
    check('电影服务已归类并带中文名', movies is not None and movies['registered']
          and movies['name'] == '电影')


def _resolve_ok(path):
    try:
        resolve(path)
        return True
    except Exception:
        return False


# ───────────────────── 第 11 轮：前台状态图标（导航 / 图例 / 线路 Tab） ─────────────────────

def round11_status_icons():
    """状态图标是「静默失效」型功能：字段缺失时 lucide 只会跳过空图标名，页面照常渲染。
    因此这里既查菜单数据源，也查渲染结果里没有空的 data-lucide。"""
    section('第 11 轮 前台服务状态图标（导航 / 图例 / 线路 Tab）')

    # 状态定义表自带图标与配色，且四态互不相同
    defs = {k: STATUS_DEFS[k] for k in ('normal', 'dev', 'maintenance', 'offline')}
    missing = [k for k, v in defs.items() if not v.get('icon') or not v.get('fg')]
    check('每个状态都有图标名与图标配色', not missing, f'missing={missing}')
    icons = [v['icon'] for v in defs.values()]
    check('四态图标互不相同', len(set(icons)) == 4, f'icons={icons}')

    # 线路级状态 = 该线路下全部端点生效状态里最严重的一个（端点级策略也要体现）
    check('worst_status 取最严重', worst_status(['normal', 'dev', 'maintenance']) == 'maintenance')
    check('worst_status 空集合兜底为 normal', worst_status([]) == 'normal')

    ch_prefix, ep_a, ep_b = f'{BASE}line/', f'{BASE}line/one', f'{BASE}line/two'
    line = _mk_policy(name=f'Line {MARK}', level='channel', path_prefix=ch_prefix,
                      status='normal', auth_mode='inherit')
    check('线路无异常时状态为 normal',
          channel_status_fields([ep_a, ep_b])['status'] == 'normal')

    ep = _mk_policy(name=f'LineEp {MARK}', level='endpoint', path_prefix=ep_a,
                    status='maintenance', auth_mode='inherit')
    check('端点级维护会体现在线路状态上',
          channel_status_fields([ep_a, ep_b])['status'] == 'maintenance')
    check('线路状态图标与配色随之变化',
          channel_status_fields([ep_a, ep_b])['status_icon'] == 'wrench'
          and channel_status_fields([ep_a, ep_b])['status_fg'] == 'text-warning')

    line.status = 'offline'
    line.save(update_fields=['status', 'updated_time'])
    check('线路级下线比端点级维护更严重（取更严重者）',
          channel_status_fields([ep_a, ep_b])['status'] == 'offline')
    check('未设策略的线路走全局兜底 normal',
          channel_status_fields([f'{BASE}none/one'])['status'] == 'normal')
    ep.delete()
    line.delete()

    # 导航数据源：服务项与线路子项都必须带状态图标，且「不可点击」规则一致
    menu = build_docs_menu()
    check('导航菜单非空', bool(menu), f'menu={len(menu)}')
    bad = [n['name'] for n in menu if not n.get('status_icon') or not n.get('status_fg')]
    check('导航每个服务项都带状态图标与配色', not bad, f'bad={bad[:5]}')
    mismatch = [n['name'] for n in menu
                if n.get('status') in defs
                and (n['status_icon'] != defs[n['status']]['icon']
                     or n['status_fg'] != defs[n['status']]['fg'])]
    check('导航图标与状态一一对应', not mismatch, f'mismatch={mismatch[:5]}')

    kids = [c for n in menu for c in n['children']]
    check('导航含可展开服务的线路子项', bool(kids), f'kids={len(kids)}')
    bad_kids = [c['name'] for c in kids if not c.get('status_icon') or not c.get('status_fg')]
    check('每个线路子项都带状态图标与配色', not bad_kids, f'bad={bad_kids[:5]}')
    bad_flag = [c['name'] for c in kids
                if c['disabled'] != (c['status'] in UNCLICKABLE_STATUSES)]
    check('线路子项「不可点击」与服务级规则一致', not bad_flag, f'bad={bad_flag[:5]}')

    client = Client()
    resp = client.get(reverse('website:docs_index'))
    body = resp.content.decode()
    check('/docs/ 正常渲染（200）', resp.status_code == 200, f'status={resp.status_code}')
    check('渲染结果无空图标名（data-lucide=""）', 'data-lucide=""' not in body)
    for key, d in defs.items():
        check(f'图例含「{d["label"]}」图标（{d["icon"]}）',
              f'data-lucide="{d["icon"]}"' in body)

    # 文档页顶部线路 Tab：每条线路都带自己的状态图标
    page = next(n for n in menu if n['children'])
    resp = client.get(page['url'])
    body = resp.content.decode()
    check(f'文档页 {page["slug"]} 正常渲染（200）', resp.status_code == 200,
          f'status={resp.status_code}')
    tabs = re.findall(r'<button[^>]*data-doc-tab="[^"]*"[^>]*>(.*?)</button>', body, re.S)
    check('文档页线路 Tab 数量与线路数一致', len(tabs) == len(page['children']),
          f'tabs={len(tabs)} kids={len(page["children"])}')
    check('每个线路 Tab 都带状态图标',
          bool(tabs) and all('data-lucide="' in t for t in tabs))
    check('文档页同样无空图标名', 'data-lucide=""' not in body)


# ───────────────── 第 12 轮：文档可见性 / 使用范围 ─────────────────

# 真实文档端点（用于验证「文档隐藏」在真实文档页与在线调试上的过滤效果）
_REAL_ENDPOINT = '/api/seo/friend_links'
_REAL_SERVICE_PREFIX = '/api/seo/'
_REAL_SERVICE_SLUG = 'seo'


def round12_docs_visible_audience():
    section('第 12 轮 文档可见性（docs_visible）与使用范围（audience）')

    # 12.1 全局兜底：未命中策略时为 visible / normal
    probe = f'{BASE}dv/probe'
    eff = resolve_service_policy(probe)
    check('未命中策略时兜底 docs_visible=visible', eff['docs_visible'] == 'visible')
    check('未命中策略时兜底 audience=normal', eff['audience'] == 'normal')
    check('is_docs_hidden 未命中为 False', is_docs_hidden(probe) is False)
    check('is_admin_only 未命中为 False', is_admin_only(probe) is False)

    # 12.2 三级继承：服务级设定 → 线路 / 端点继承；端点级覆盖
    _mk_policy(name=f'DvSvc {MARK}', level='service', path_prefix=f'{BASE}dv/',
               docs_visible='hidden', audience='admin_only')
    check('线路级继承服务级 docs_visible=hidden', is_docs_hidden(f'{BASE}dv/ch/any') is True)
    check('端点级继承服务级 audience=admin_only', is_admin_only(f'{BASE}dv/ch/any') is True)

    _mk_policy(name=f'DvEp {MARK}', level='endpoint', path_prefix=f'{BASE}dv/ch/visible',
               docs_visible='visible', audience='normal')
    check('端点级 visible 覆盖服务级 hidden', is_docs_hidden(f'{BASE}dv/ch/visible') is False)
    check('端点级 normal 覆盖服务级 admin_only', is_admin_only(f'{BASE}dv/ch/visible') is False)
    check('同服务其他端点仍继承隐藏', is_docs_hidden(f'{BASE}dv/ch/other') is True)

    # 12.3 admin_only 对外一律 20020（带不带签名都一样）
    anon = Client()
    resp = anon.get(f'{BASE}dv/ch/any')
    check('admin_only 匿名请求返回 20020', _code(resp) == StatusCode.FORBIDDEN,
          f'code={_code(resp)}')
    resp = anon.get(f'{BASE}dv/ch/any', _signed(_mk_app('D')))
    check('admin_only 携带合法签名仍返回 20020（未做签名校验）',
          _code(resp) == StatusCode.FORBIDDEN, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}dv/ch/visible')
    check('端点级 normal 覆盖后不再被 20020 拦截',
          _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')

    # 12.4 状态拦截优先于 admin_only（维护态先返回 30004）
    _mk_policy(name=f'DvMaint {MARK}', level='service', path_prefix=f'{BASE}dvm/',
               status='maintenance', audience='admin_only')
    resp = anon.get(f'{BASE}dvm/x')
    check('维护态优先于 admin_only（返回 30004 而非 20020）',
          _code(resp) == StatusCode.SERVICE_MAINTENANCE, f'code={_code(resp)}')

    # 12.5 真实文档页 / 在线调试的过滤效果（临时建策略，finally 必删）
    if ApiServicePolicy.objects.filter(path_prefix=_REAL_ENDPOINT).exists():
        check('真实端点无既有策略（跳过 12.5）', False,
              f'{_REAL_ENDPOINT} 已存在策略，未做临时隐藏测试')
        return
    temp = _mk_policy(name=f'DvReal {MARK}', level='endpoint', path_prefix=_REAL_ENDPOINT,
                      docs_visible='hidden')
    try:
        check('真实端点被判定为文档隐藏', is_docs_hidden(_REAL_ENDPOINT) is True)

        resp = anon.get(reverse('website:docs_service', args=[_REAL_SERVICE_SLUG]))
        body = resp.content.decode()
        check('文档页仍可访问（服务未整体隐藏）', resp.status_code == 200,
              f'status={resp.status_code}')
        check('隐藏的端点不出现在文档页', _REAL_ENDPOINT not in body)

        hidden_menu = [(c['name'], c['url']) for n in build_docs_menu()
                       for c in n['children']]
        check('左侧菜单不受端点级隐藏影响（线路仍在）', bool(hidden_menu))

        resp = anon.post(reverse('website:docs_call'),
                         data=json.dumps({'path': _REAL_ENDPOINT, 'method': 'GET'}),
                         content_type='application/json')
        payload = _json(resp)
        check('在线调试拒绝隐藏端点（404）', payload.get('http_status') == 404,
              f'payload={payload}')
    finally:
        temp.delete()
        invalidate_api_service_policy_cache()
    check('临时策略已删除（真实配置还原）',
          not ApiServicePolicy.objects.filter(path_prefix=_REAL_ENDPOINT).exists())
    check('删除后真实端点恢复可见', is_docs_hidden(_REAL_ENDPOINT) is False)


# ───────────────── 第 13 轮：线路多选（一条策略覆盖多条线路） ─────────────────

def round13_multi_channel(client):
    section('第 13 轮 线路多选（一条策略覆盖多条线路 / 接管让位）')
    url = reverse('website:console_services')
    svc = f'{BASE}multi/'
    ch1, ch2, ch3 = f'{svc}one/', f'{svc}two/', f'{svc}three/'

    resp = client.post(url, {'action': 'create', 'name': f'Multi {MARK}',
                             'service': svc, 'channels': [ch1, ch2],
                             'status': 'normal', 'auth_mode': 'open',
                             'docs_visible': 'inherit', 'audience': 'inherit'})
    policy = ApiServicePolicy.objects.filter(path_prefix=ch1).first()
    check('多选线路创建成功（一条策略两条线路）',
          resp.status_code == 302 and policy is not None and policy.level == 'channel'
          and policy.all_prefixes == [ch1, ch2], f'policy={policy!r}')
    check('两条线路都按该策略生效', requires_auth(f'{ch1}x') is False
          and requires_auth(f'{ch2}x') is False)
    check('未选中的线路不受影响（仍需要签名）', requires_auth(f'{ch3}x') is True)

    body = client.get(url).content.decode()
    check('列表页展示该策略的全部线路前缀',
          f'<code class="font-mono text-base-content/60">{ch1}</code>' in body
          and f'<code class="font-mono text-base-content/60">{ch2}</code>' in body)
    check('编辑按钮携带全部线路前缀（供多选回填）',
          f'data-prefixes="{ch1},{ch2}"' in body)

    # 编辑：改成三条线路
    resp = client.post(url, {'action': 'edit', 'id': str(policy.pk), 'name': f'Multi2 {MARK}',
                             'service': svc, 'channels': [ch3, ch1, ch2],
                             'status': 'maintenance', 'auth_mode': 'open',
                             'docs_visible': 'inherit', 'audience': 'inherit'})
    policy.refresh_from_db()
    check('编辑可增删线路且三条均生效',
          resp.status_code == 302 and set(policy.all_prefixes) == {ch1, ch2, ch3}
          and resolve_service_policy(f'{ch2}x')['status'] == 'maintenance',
          f'prefixes={policy.all_prefixes}')

    # 让位：另一条策略只接管其中一条 → 原策略保留其余线路
    client.post(url, {'action': 'create', 'name': f'Steal {MARK}',
                      'service': svc, 'channels': [ch2],
                      'status': 'normal', 'auth_mode': 'auth',
                      'docs_visible': 'inherit', 'audience': 'inherit'})
    policy.refresh_from_db()
    thief = ApiServicePolicy.objects.filter(name=f'Steal {MARK}').first()
    check('部分线路被接管：原策略保留其余线路',
          thief is not None and thief.all_prefixes == [ch2]
          and set(policy.all_prefixes) == {ch1, ch3},
          f'thief={thief!r} left={policy.all_prefixes}')
    check('被接管线路改用新策略的配置',
          resolve_service_policy(f'{ch2}x')['auth_mode'] == 'auth'
          and resolve_service_policy(f'{ch1}x')['auth_mode'] == 'open')

    # 全部让位：一条策略把原策略剩余线路全接管 → 原策略被删除
    stolen = {ch1, ch3}
    client.post(url, {'action': 'create', 'name': f'StealAll {MARK}',
                      'service': svc, 'channels': [ch1, ch3],
                      'status': 'normal', 'auth_mode': 'auth',
                      'docs_visible': 'inherit', 'audience': 'inherit'})
    check('全部线路被接管 → 原策略让位删除',
          not ApiServicePolicy.objects.filter(pk=policy.pk).exists()
          and set(ApiServicePolicy.objects.get(name=f'StealAll {MARK}').all_prefixes) == stolen)


# ───────────────── 第 14 轮：批量删除 + 弹窗版面 ─────────────────

def round14_bulk_delete(client):
    section('第 14 轮 批量删除与弹窗版面（/console/services/）')
    url = reverse('website:console_services')

    body = client.get(url).content.decode()
    check('列表页含批量删除表单与勾选框',
          'name="action" value="delete_bulk"' in body and 'service_batch_form' in body
          and 'data-row-check' in body and 'data-select-all' in body and 'data-batch-delete' in body)
    check('弹窗为两块分区且无单价输入',
          'name="price"' not in body and '作用范围' in body and '对外表现' in body)
    check('白名单相关 UI 已彻底移除',
          'data-apps-panel' not in body and 'data-app-scope' not in body
          and '白名单' not in body)
    check('列表页不再有单价列',
          '项目范围' not in body and '生效结果' in body)

    svc = f'{BASE}bulk/'
    prefixes = [f'{svc}a/', f'{svc}b/', f'{svc}c/']
    for i, prefix in enumerate(prefixes):
        client.post(url, {'action': 'create', 'name': f'Bulk{i} {MARK}',
                          'service': svc, 'channels': [prefix],
                          'status': 'normal', 'auth_mode': 'auth',
                          'docs_visible': 'inherit', 'audience': 'inherit'})
    ids = [str(p.pk) for p in ApiServicePolicy.objects.filter(path_prefix__in=prefixes)]
    check('三条策略已就绪（供批量删除）', len(ids) == 3, f'ids={ids}')

    # 一条都没勾（或全是非法值）→ 不删
    resp = client.post(url, {'action': 'delete_bulk'})
    check('未勾选时批量删除被拒且不删除',
          resp.status_code == 302
          and ApiServicePolicy.objects.filter(pk__in=ids).count() == 3)
    resp = client.post(url, {'action': 'delete_bulk', 'ids': ['abc', '']})
    check('非法 id 被忽略（不误删）',
          resp.status_code == 302
          and ApiServicePolicy.objects.filter(pk__in=ids).count() == 3)

    # 只勾两条 → 只删这两条，且立即失效
    resp = client.post(url, {'action': 'delete_bulk', 'ids': ids[:2]})
    check('只删除勾选的两条策略',
          resp.status_code == 302
          and ApiServicePolicy.objects.filter(pk__in=ids).count() == 1
          and not ApiServicePolicy.objects.filter(pk=ids[0]).exists()
          and not ApiServicePolicy.objects.filter(pk=ids[1]).exists())
    check('被删策略立即失效（路径回到 fail-closed）',
          requires_auth(f'{prefixes[0]}x') is True
          and len(resolve_service_policy(f'{prefixes[0]}x')['chain']) == 0)


# ───────────────── 第 15 轮：建议策略（清单 / 一键新建 / 免签兜底） ─────────────────

def round15_service_presets(client):
    section('第 15 轮 建议策略清单与「一键新建」（预览面板 / 幂等 / 不覆盖 / 免签兜底）')
    url = reverse('website:console_services')

    # 1) 清单自证：必须与 0028 / 0031 / 0032 / 0035 / 0043 写入的 9 条逐条一致
    #    （level 也照抄迁移原文，即便有几处与服务树归类不符 —— 见 service_presets.py 注释）
    expected = {
        '/api/captcha_self/': ('service', 'open'),
        '/api/captcha_auth/aliyun/': ('service', 'open'),
        '/api/statistics/': ('service', 'open'),
        '/api/haijiao/video/m3u8': ('endpoint', 'open'),
        '/api/haijiao/image': ('endpoint', 'open'),
        '/api/dramas/hongguo/stream': ('endpoint', 'open'),
        '/api/feedback/': ('service', 'auth'),
        '/api/feedback/ticket': ('endpoint', 'open'),
        '/api/feedback/contacts': ('endpoint', 'open'),
    }
    rows = preset_rows()
    got = {row['path_prefix']: (row['level'], row['auth_mode']) for row in rows}
    check('清单恰为迁移写入的 9 条建议策略（层级 / 认证模式一致）',
          got == expected, f'got={got}')
    check('每条都写明了「为什么需要」', all(row['reason'].strip() for row in rows))

    # 每条前缀都必须是服务树里真实存在的服务 / 线路 / 端点，否则后台编辑弹窗反查不到，
    # 保存时会被降级成服务级（这是比「前缀形状」更要紧的正确性约束）。
    known = set()
    for svc in service_tree():
        known.add(svc['prefix'])
        for channel in svc['channels']:
            known.add(channel['prefix'])
            known.update(ep['path'] for ep in channel['endpoints'])
    unknown = [row['path_prefix'] for row in rows if row['path_prefix'] not in known]
    check('每条前缀都能在服务树里反查到（编辑弹窗可回填）', not unknown, f'unknown={unknown}')

    # 2) 页面：按钮 + 预览面板（列出全部建议前缀与「为什么需要」）
    #    「将新建 / 已存在」的标注与库内实际状态有关，放到下面的事务里按受控状态断言
    body = client.get(url).content.decode()
    check('列表页含「一键新建建议策略」按钮与预览面板',
          'data-open-presets' in body and 'service_presets_modal' in body
          and 'value="apply_presets"' in body)
    check('预览面板列出全部建议前缀与原因',
          all(row['path_prefix'] in body for row in rows)
          and rows[0]['reason'] in body)

    # 3) 语义验证：补齐缺失 / 可反复执行 / 不覆盖已有 / 后台入口 / 免签兜底。
    #    整段放在事务里，结束一律回滚 —— 不落任何真实改动。
    with transaction.atomic():
        ApiServicePolicy.objects.filter(path_prefix=PRESET_TARGET).delete()
        invalidate_api_service_policy_cache()

        # 预览面板必须按「当下库内状态」逐条标注：缺的那条标「将新建」，其余标「已存在，跳过」
        row_html = client.get(url).content.decode().split(PRESET_TARGET, 1)[1].split('</tr>', 1)[0]
        check('预览面板按当前库存逐条标注动作（缺失的标「将新建」）',
              '将新建' in row_html, f'row={row_html[:200]!r}')

        created, existed = apply_presets()
        check('一键新建只补缺失的那条，其余按现状跳过',
              created == [PRESET_TARGET] and PRESET_TARGET not in existed
              and len(created) + len(existed) == len(rows),
              f'created={created} existed={len(existed)}')

        created2, existed2 = apply_presets()
        check('可反复执行（第二次新建 0 条，全部按已存在跳过）',
              created2 == [] and len(existed2) == len(rows),
              f'created2={created2} existed2={len(existed2)}')

        ApiServicePolicy.objects.filter(path_prefix=PRESET_TARGET).update(auth_mode='auth')
        created3, _ = apply_presets()
        check('已存在的策略不被覆盖（手工改成需签名后仍是需签名）',
              created3 == []
              and ApiServicePolicy.objects.get(path_prefix=PRESET_TARGET).auth_mode == 'auth')

        out = io.StringIO()
        call_command('seed_service_policies', '--dry-run', stdout=out)
        text = out.getvalue()
        check('管理命令 --dry-run 显示无需新建',
              '新建 0 条' in text and '已存在跳过 9 条' in text, f'out={text.strip()}')

        # 后台入口：删掉目标后再走一次真实按钮路径（POST action=apply_presets）
        ApiServicePolicy.objects.filter(path_prefix=PRESET_TARGET).delete()
        invalidate_api_service_policy_cache()
        resp = client.post(url, {'action': 'apply_presets'})
        check('后台「一键新建」按钮补齐缺失策略并跳回列表',
              resp.status_code == 302
              and ApiServicePolicy.objects.filter(path_prefix=PRESET_TARGET).exists())

        # 免签兜底：DB 里没有这条 open 策略时，该路径仍不得被要求签名（代码内名单生效）
        ApiServicePolicy.objects.filter(path_prefix=PRESET_TARGET).delete()
        invalidate_api_service_policy_cache()
        get_resp = client.get(PRESET_TARGET)
        head_resp = client.head(PRESET_TARGET)
        check('stream 免签兜底：GET 不被中间件拦成 20011（落到视图的 403 缺令牌）',
              get_resp.status_code == 403 and _code(get_resp) != StatusCode.AUTH_FAILED,
              f'status={get_resp.status_code} body={get_resp.content[:120]!r}')
        check('stream 免签兜底：HEAD 同样放行',
              head_resp.status_code == 403 and _code(head_resp) != StatusCode.AUTH_FAILED,
              f'status={head_resp.status_code}')
        transaction.set_rollback(True)
    invalidate_api_service_policy_cache()


def main():
    print('\nAPI 服务策略回归测试开始')
    print(f'标记：{MARK}（策略前缀统一含该标记，测试后自动清理）')
    client, admin, created_admin = superadmin_client()
    try:
        app_a = round1_fail_closed()
        round2_captcha_open()
        round3_auth_inherit()
        round4_status_inherit()
        app_b = _mk_app('B')
        round5_credit_inherit(app_a, app_b)
        round6_prefix_boundary()
        app_c = _mk_app('C')
        round7_cache_invalidation(app_c)
        round8_console(client, app_a)
        round9_i18n(client, admin)
        round10_service_tree()
        round11_status_icons()
        round12_docs_visible_audience()
        round13_multi_channel(client)
        round14_bulk_delete(client)
        round15_service_presets(client)
    finally:
        cleanup()
        if created_admin:
            admin.delete()
        print('\n测试数据已清理（策略 / 项目 / 缓存）')
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
