"""API 服务策略（服务 / 线路 / 端点三级继承）回归测试

覆盖范围：
    第 1 轮 fail-closed：未命中任何策略的 /api/ 路径 → 需要签名，匿名 20011
    第 2 轮 开放节点：迁移写入的 /api/captcha_self/ 与 /api/captcha_auth/aliyun/ 仍开放
    第 3 轮 三级继承（认证）：服务级 open 向上继承；端点级 auth 覆盖服务级
    第 4 轮 状态继承：服务级 maintenance 命中全部；端点级 normal 覆盖
    第 5 轮 白名单继承：服务级 whitelist 只放行车名单项目；端点级 all 覆盖
    第 6 轮 前缀边界：/api/foo 的策略不得命中 /api/foobar/...
    第 7 轮 缓存失效：改 status / auth_mode / 白名单后立即生效，不必等 TTL
    第 8 轮 控制台页面：未登录跳转、超管可访问、含三级联动数据、增删改各自生效
    第 9 轮 三语（zh-hans / zh-hant / en）页面正常渲染且关键词已翻译

隔离策略：全部测试数据用 MARK（xysvcpolicy<RUN>）标记，策略路径前缀一律包含 MARK，
测试结束统一删除，绝不触碰真实策略配置。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_service_policy.py
"""
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
from django.test import Client
from django.urls import resolve, reverse

from API.apis.user_center.sign import build_sign
from API.common import StatusCode
from API.common.middleware import (
    invalidate_api_service_policy_cache,
    requires_auth,
    resolve_service_policy,
)
from API.models import ApiServicePolicy, UserApp
from API.website.service_tree import service_tree

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
    return UserApp.objects.create(name=f'SvcApp{MARK}{tag}')


def _mk_policy(**kwargs):
    """建策略（不触发模型 clean，等价于 DDL 直建；用于构造各种继承场景）"""
    apps = kwargs.pop('apps', None)
    policy = ApiServicePolicy.objects.create(**kwargs)
    if apps:
        policy.apps.set(apps)
    return policy


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
    """删除全部测试数据（策略路径前缀一律包含 MARK）"""
    ApiServicePolicy.objects.filter(path_prefix__contains=MARK).delete()
    UserApp.objects.filter(name__contains=MARK).delete()
    invalidate_api_service_policy_cache()


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
               auth_mode='open', status='inherit', app_scope='inherit')

    check('线路级未设 → 继承服务级开放',
          requires_auth(f'{BASE}open/ch/any') is False)
    check('端点级未设 → 继承服务级开放',
          requires_auth(f'{BASE}open/ch/ep') is False)

    _mk_policy(name=f'EpAuth {MARK}', level='endpoint', path_prefix=f'{BASE}open/ch/ep',
               auth_mode='auth', status='inherit', app_scope='inherit')
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
    section('第 4 轮 状态继承（服务 maintenance → 全部维护；端点 normal 覆盖）')
    _mk_policy(name=f'SvcMaint {MARK}', level='service', path_prefix=f'{BASE}maint/',
               status='maintenance', auth_mode='inherit', app_scope='inherit')
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
               status='normal', auth_mode='inherit', app_scope='inherit')
    check('端点级 normal 覆盖服务级维护态',
          resolve_service_policy(f'{BASE}maint/ok')['status'] == 'normal')
    resp = anon.get(f'{BASE}maint/ok')
    check('该端点不再返回维护码（落到 20011）',
          _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')


# ───────────────────────── 第 5 轮：白名单继承 ─────────────────────────

def round5_whitelist_inherit(app_a, app_b):
    section('第 5 轮 白名单继承（服务 whitelist 仅含 A；端点 all 覆盖）')
    _mk_policy(name=f'SvcWl {MARK}', level='service', path_prefix=f'{BASE}wl/',
               auth_mode='auth', app_scope='whitelist', apps=[app_a])

    anon = Client()
    resp = anon.get(f'{BASE}wl/probe')
    check('未签名被拒（20011）', _code(resp) == StatusCode.AUTH_FAILED, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}wl/probe', _signed(app_a))
    check('名单内项目 A 通过（落到 20030）', _code(resp) == StatusCode.NOT_FOUND, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}wl/probe', _signed(app_b))
    check('名单外项目 B 返回 20020', _code(resp) == StatusCode.FORBIDDEN, f'code={_code(resp)}')

    _mk_policy(name=f'EpAll {MARK}', level='endpoint', path_prefix=f'{BASE}wl/probe',
               auth_mode='inherit', app_scope='all')
    resp = anon.get(f'{BASE}wl/probe', _signed(app_b))
    check('端点级 all 覆盖服务级 whitelist（B 通过）',
          _code(resp) == StatusCode.NOT_FOUND, f'code={_code(resp)}')
    resp = anon.get(f'{BASE}wl/other', _signed(app_b))
    check('同服务其他路径仍受白名单限制（B 返回 20020）',
          _code(resp) == StatusCode.FORBIDDEN, f'code={_code(resp)}')


# ───────────────────────── 第 6 轮：前缀边界 ─────────────────────────

def round6_prefix_boundary():
    section('第 6 轮 前缀边界（/api/foo 不得命中 /api/foobar）')
    foo_prefix = f'{BASE}foo'
    _mk_policy(name=f'Boundary {MARK}', level='channel', path_prefix=foo_prefix,
               auth_mode='open', status='inherit', app_scope='inherit')

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
                        auth_mode='open', status='normal', app_scope='inherit')
    check('初始开放（并已填充缓存）', requires_auth(f'{BASE}cache/probe') is False)

    policy.auth_mode = 'auth'
    policy.save(update_fields=['auth_mode', 'updated_time'])
    check('改 auth_mode 后立即生效', requires_auth(f'{BASE}cache/probe') is True)

    policy.status = 'maintenance'
    policy.save(update_fields=['status', 'updated_time'])
    check('改 status 后立即生效',
          resolve_service_policy(f'{BASE}cache/probe')['status'] == 'maintenance')

    policy.auth_mode = 'auth'
    policy.app_scope = 'whitelist'
    policy.status = 'normal'
    policy.save(update_fields=['auth_mode', 'app_scope', 'status', 'updated_time'])
    check('白名单为空时项目不通过',
          not _allowed(f'{BASE}cache/probe', app_c))
    policy.apps.set([app_c])
    check('加入白名单后立即放行（M2M 改动即时失效缓存）',
          _allowed(f'{BASE}cache/probe', app_c))

    invalidate_api_service_policy_cache()
    check('显式失效函数可用', isinstance(requires_auth(f'{BASE}cache/probe'), bool))


def _allowed(path, app):
    """签名后是否放行（未被白名单拒绝）"""
    anon = Client()
    resp = anon.get(path, _signed(app))
    return _code(resp) != StatusCode.FORBIDDEN


# ───────────────────────── 第 8 轮：控制台页面 ─────────────────────────

def round8_console(client, app_a):
    section('第 8 轮 控制台页面与增删改（/console/services/）')
    url = reverse('website:console_services')
    check('匿名访问跳转登录（302）', Client().get(url).status_code == 302)

    resp = client.get(url)
    body = resp.content.decode()
    check('超管可访问（200）', resp.status_code == 200, f'status={resp.status_code}')
    check('页面内联三级联动枚举数据（json_script）',
          'service_tree_data' in body and 'service_levels' in body)
    check('三级下拉与自动推导控件存在',
          'data-tree-service' in body and 'data-tree-channel' in body
          and 'data-tree-endpoint' in body and 'data-tree-prefix' in body)
    check('菜单高亮「服务策略」', 'menu-active' in body and url in body)
    bad = re.findall(r'onclick="[\w$]*-[\w$-]*\.(?:showModal|close)\(', body)
    check('无「连字符 id」的对话框入口', not bad, f'bad={bad}')

    # 新建（服务级）
    prefix = f'{BASE}console/'
    resp = client.post(url, {'action': 'create', 'name': f'Console {MARK}',
                             'service': prefix, 'status': 'normal', 'auth_mode': 'auth',
                             'app_scope': 'whitelist', 'apps': [str(app_a.pk)], 'remark': 'created'})
    policy = ApiServicePolicy.objects.filter(path_prefix=prefix).first()
    check('视图新建策略成功（层级自动推导为服务级）',
          resp.status_code == 302 and policy is not None and policy.level == 'service')
    check('新建时保存了白名单项目', policy is not None and policy.apps.count() == 1)
    check('新建后立即生效（需要认证）', requires_auth(f'{prefix}probe') is True)

    # 编辑（改为线路级 open）
    channel = f'{BASE}console/ch/'
    resp = client.post(url, {'action': 'edit', 'id': str(policy.pk), 'name': f'Console2 {MARK}',
                             'service': prefix, 'channel': channel, 'status': 'normal',
                             'auth_mode': 'open', 'app_scope': 'all', 'remark': 'edited'})
    policy.refresh_from_db()
    check('编辑生效（层级推导为线路级 / 模式 / 范围 / 备注）',
          resp.status_code == 302 and policy.level == 'channel'
          and policy.path_prefix == channel and policy.auth_mode == 'open'
          and policy.app_scope == 'all' and policy.remark == 'edited')
    check('编辑后白名单已清空', policy.apps.count() == 0)
    check('编辑后认证模式立即生效（开放）', requires_auth(f'{channel}probe') is False)

    # 表单校验
    client.post(url, {'action': 'create', 'name': '', 'service': prefix,
                      'status': 'normal', 'auth_mode': 'auth', 'app_scope': 'all'})
    check('缺少名称被拒且不新建',
          ApiServicePolicy.objects.filter(path_prefix=channel).count() == 1)
    client.post(url, {'action': 'create', 'name': 'bad', 'service': 'no-slash',
                      'status': 'normal', 'auth_mode': 'auth', 'app_scope': 'all'})
    check('非法服务被拒', not ApiServicePolicy.objects.filter(name='bad').exists())
    client.post(url, {'action': 'create', 'name': 'dup', 'service': prefix, 'channel': channel,
                      'status': 'normal', 'auth_mode': 'auth', 'app_scope': 'all'})
    check('重复路径被拒', ApiServicePolicy.objects.filter(path_prefix=channel).count() == 1)

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

    for lang, must in (('en', 'Service Policies'), ('zh-hant', '服務策略')):
        lang_client = Client()
        lang_client.force_login(admin)
        lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        resp = lang_client.get(url)
        text = resp.content.decode()
        check(f'{lang} 页面渲染成功且关键词已翻译',
              resp.status_code == 200 and must in text, f'status={resp.status_code}')


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
        round5_whitelist_inherit(app_a, app_b)
        round6_prefix_boundary()
        app_c = _mk_app('C')
        round7_cache_invalidation(app_c)
        round8_console(client, app_a)
        round9_i18n(client, admin)
        round10_service_tree()
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
