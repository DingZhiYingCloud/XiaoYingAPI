"""用户中心 API 多轮边缘化 / 极端化测试

覆盖范围：
    第一轮 正常流程（注册/登录/验证/信息/退出）
    第二轮 参数校验边界（缺失/超长/过短/空值/特殊字符）
    第三轮 签名安全（参数缺失/时间戳窗口/篡改/未知项目/停用项目）
    第四轮 认证安全（错误密码/封禁/跨项目 Token/过期 Token/伪造 Token）
    第五轮 系统健壮性（批量注册/账号唯一/多 Token 并存/明文密码检查/方法限制）
    第六轮 并发与唯一性（并发创建项目/密钥自动生成与固定/名称唯一/并发注册/并发登录）

运行方式（使用真实数据库，测试结束后自动清理测试数据）：
    .venv\\Scripts\\python.exe scripts\\test_user_center.py
"""
import os
import random
import secrets
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

# 测试提速：PBKDF2 默认迭代次数极高（约 0.5s/次），批量注册 50 用户会拖垮测试。
# 临时切换为 MD5 哈希器（仅影响本进程，不影响生产配置；make_password/check_password 接口一致）。
from django.conf import settings
from django.contrib.auth.hashers import MD5PasswordHasher

settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

from django.test import Client
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError

from API.models import User, UserApp, UserToken
from API.apis.user_center.sign import build_sign

# ───────────────────────── 测试基础设施 ─────────────────────────

BASE = '/api/user_center'
PASS = 'pass123456'
_PREFIX = f'UT{int(time.time())}'

_stats = {'pass': 0, 'fail': 0}
_round_title = ''
_created_apps = []   # (app_id, app_secret, UserApp)
_created_users = []  # user_id
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_user_center_result.log')


def _log(msg):
    print(msg)
    with open(_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def _section(title):
    global _round_title
    _round_title = title
    _log(f'\n===== {title} =====')


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        _log(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        _log(f'  [FAIL] {name} {extra}')


def _signed(app, extra=None, timestamp=None):
    """构造签名参数（可覆盖 timestamp 做时间窗测试；None 值参数自动剔除）"""
    extra = {k: v for k, v in (extra or {}).items() if v is not None}
    params = {
        'app_id': app[0],
        'timestamp': str(timestamp if timestamp is not None else int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app[1])
    return params


def _create_app(name=None, status=True, expire_days=7):
    """创建测试项目：不手动指定密钥，走系统自动生成路径（生产行为）"""
    obj = UserApp.objects.create(
        name=name or f'{_PREFIX}项目{len(_created_apps)}',
        token_expire_days=expire_days, status=status,
    )
    entry = (obj.app_id, obj.app_secret, obj)
    _created_apps.append(entry)
    return entry


def _create_user(app=None, username=None, account=None, password=PASS, status=True):
    """直接造用户（绕过注册接口，用于登录/封禁等用例）"""
    user = User.objects.create(
        account=account or str(random.randint(10000000, 99999999)),
        username=username or f'{_PREFIX}用户{len(_created_users)}',
        password=make_password(password),
        status=status,
    )
    _created_users.append(str(user.id))
    return user


def _response(resp):
    """解析响应 JSON"""
    import json
    return json.loads(resp.content.decode('utf-8'))


def _register(app, username, password):
    return _response(Client().post(f'{BASE}/users/register', _signed(app, {
        'username': username, 'password': password,
    })))


def _login(app, account, password):
    return _response(Client().post(f'{BASE}/users/login', _signed(app, {
        'account': account, 'password': password,
    })))


def _verify(app, token):
    return _response(Client().post(f'{BASE}/users/verify', _signed(app, {'token': token})))


def _info(app, token):
    return _response(Client().get(f'{BASE}/users/info', _signed(app, {'token': token})))


def _logout(app, token):
    return _response(Client().post(f'{BASE}/users/logout', _signed(app, {'token': token})))


def _is_success(resp):
    return resp.get('code') == 10000


# ───────────────────────── 第一轮：正常流程 ─────────────────────────

def round1():
    _section('第一轮 正常流程')
    app = _create_app()

    # 1. 注册
    r = _register(app, '小明', PASS)
    _check('注册成功 code=10000', _is_success(r))
    data = r.get('data') or {}
    acc = data.get('account')
    _check('注册返回账号', bool(acc))
    _check('账号为纯数字 6-12 位', bool(acc) and acc.isdigit() and 6 <= len(acc) <= 12, f'account={acc}')
    _check('注册返回 user_id', bool(data.get('user_id')))
    uid = data.get('user_id')
    if uid:
        _created_users.append(uid)  # 登记用于结束清理

    # 2. 登录
    r = _login(app, acc, PASS)
    _check('登录成功 code=10000', _is_success(r))
    token = (r.get('data') or {}).get('token')
    _check('登录返回 token', bool(token))
    _check('登录返回 user_id 一致', (r.get('data') or {}).get('user_id') == uid)
    _check('登录返回 expire_time', bool((r.get('data') or {}).get('expire_time')))

    # 3. 验证 token
    r = _verify(app, token)
    _check('验证 token 有效', _is_success(r) and (r.get('data') or {}).get('valid') is True)
    _check('验证返回 user_id 一致', (r.get('data') or {}).get('user_id') == uid)

    # 4. 用户信息
    r = _info(app, token)
    _check('获取用户信息成功', _is_success(r))
    _check('信息 username 正确', (r.get('data') or {}).get('username') == '小明')

    # 5. 退出
    r = _logout(app, token)
    _check('退出成功', _is_success(r))

    # 6. 退出后验证失败
    r = _verify(app, token)
    _check('退出后 token 失效', r.get('code') == 20010)


# ───────────────────────── 第二轮：参数校验边界 ─────────────────────────

def round2():
    _section('第二轮 参数校验边界')
    app = _create_app()

    cases = [
        ('缺 username', {'password': PASS}, 20001),
        ('缺 password', {'username': 'x'}, 20001),
        ('username 空字符串', {'username': '', 'password': PASS}, 20001),
        ('username 纯空格', {'username': '   ', 'password': PASS}, 20001),
        ('password 空字符串', {'username': 'x', 'password': ''}, 20001),
        ('username 超长(51)', {'username': 'a' * 51, 'password': PASS}, 20002),
        ('password 过短(7)', {'username': 'x', 'password': 'abc1234'}, 20002),
        ('password 过长(65)', {'username': 'x', 'password': 'p' * 65}, 20002),
        ('password 纯数字(8位无字母)', {'username': 'x', 'password': '12345678'}, 20002),
        ('password 纯字母(8位无数字)', {'username': 'x', 'password': 'abcdefgh'}, 20002),
        ('password 恰好 8 位(字母数字混合)', {'username': 'x', 'password': 'abc12345'}, 10000),
    ]
    for name, extra, expect_code in cases:
        r = _register(app, extra.get('username'), extra.get('password'))
        _check(f'注册-{name}', r.get('code') == expect_code, f'code={r.get("code")} msg={r.get("msg")}')
        if r.get('code') == 10000:
            _created_users.append((r.get('data') or {}).get('user_id'))  # 成功用例登记清理

    # 特殊字符用户名（emoji/中文/符号）允许注册
    r = _register(app, '张三@Test_你好🚀', PASS)
    _check('特殊字符用户名可注册', _is_success(r), f'msg={r.get("msg")}')
    uid = (r.get('data') or {}).get('user_id')
    if uid:
        _created_users.append(uid)

    # 登录参数校验
    r = _login(app, '', PASS)
    _check('登录-缺 account', r.get('code') == 20001)
    r = _login(app, '12345678', '')
    _check('登录-缺 password', r.get('code') == 20001)
    r = _verify(app, '')
    _check('验证-缺 token', r.get('code') == 20001)
    r = _info(app, '')
    _check('信息-缺 token', r.get('code') == 20001)
    r = _logout(app, '')
    _check('退出-缺 token', r.get('code') == 20001)


# ───────────────────────── 第三轮：签名安全 ─────────────────────────

def round3():
    _section('第三轮 签名安全')
    app = _create_app()
    other_app = _create_app()

    # 缺签名参数
    for miss in ('app_id', 'timestamp', 'nonce', 'sign'):
        params = {
            'app_id': app[0], 'timestamp': str(int(time.time())),
            'nonce': 'abc', 'sign': 'x',
            'username': '签名测试', 'password': PASS,
        }
        params.pop(miss)
        r = _response(Client().post(f'{BASE}/users/register', params))
        _check(f'签名-缺 {miss}', r.get('code') == 20011 and '签名参数缺失' in r.get('msg', ''))

    # 时间戳非法
    params = _signed(app, {'username': 'a', 'password': PASS}, timestamp='not-a-number')
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-timestamp 非数字', r.get('code') == 20011 and '格式错误' in r.get('msg', ''))

    # 时间戳过期（10 分钟前）
    ts = int(time.time()) - 600
    params = _signed(app, {'username': 'a', 'password': PASS}, timestamp=ts)
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-timestamp 过期(10分钟前)', r.get('code') == 20011 and '过期' in r.get('msg', ''))

    # 时间戳未来（10 分钟后）
    ts = int(time.time()) + 600
    params = _signed(app, {'username': 'a', 'password': PASS}, timestamp=ts)
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-timestamp 未来(10分钟后)', r.get('code') == 20011 and '过期' in r.get('msg', ''))

    # 边界：5 分钟窗口内（280 秒前，留足请求耗时余量，避免贴上限受延迟抖动影响）
    ts = int(time.time()) - 280
    params = _signed(app, {'username': '边界', 'password': PASS}, timestamp=ts)
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-timestamp 边界(窗口内280秒)', _is_success(r), f'code={r.get("code")}')

    # 错误 sign
    params = _signed(app, {'username': 'a', 'password': PASS})
    params['sign'] = '0' * 64
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-错误 sign', r.get('code') == 20011 and '不匹配' in r.get('msg', ''))

    # 篡改业务参数（签名用 a，实际提交 b）
    params = _signed(app, {'username': 'a', 'password': PASS})
    params['username'] = 'b'
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-篡改业务参数', r.get('code') == 20011 and '不匹配' in r.get('msg', ''))

    # 未注册 app_id
    params = _signed(other_app, {'username': 'a', 'password': PASS})
    params['app_id'] = 'NONE_APP_999'
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-未注册 app_id', r.get('code') == 20011 and '未注册' in r.get('msg', ''))

    # 停用项目
    disabled = _create_app(status=False)
    params = _signed(disabled, {'username': 'a', 'password': PASS})
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-停用项目', r.get('code') == 20011 and '停用' in r.get('msg', ''))

    # 使用其他项目密钥签名的参数，用本项目 app_id 提交 → sign 不匹配
    params = _signed(other_app, {'username': 'a', 'password': PASS})
    params['app_id'] = app[0]
    r = _response(Client().post(f'{BASE}/users/register', params))
    _check('签名-跨项目密钥伪造', r.get('code') == 20011 and '不匹配' in r.get('msg', ''))

    # 项目信息接口签名
    r = _response(Client().get(f'{BASE}/projects/info', _signed(app)))
    _check('项目信息-正确签名', _is_success(r))
    r = _response(Client().get(f'{BASE}/projects/info', {'app_id': app[0]}))
    _check('项目信息-缺签名参数', r.get('code') == 20011)

    # nonce 去重（S-05 整改：nonce 服务端落库去重，同 nonce 即使更换时间戳也必须拒绝）
    nonce = 'same-nonce'
    params = _signed(app, {'username': '重放', 'password': PASS})
    params['nonce'] = nonce
    params['sign'] = build_sign(params, app[1])  # 覆盖 nonce 后必须重算签名
    r1 = _response(Client().post(f'{BASE}/users/register', params))
    _check('重放-首次使用 nonce 正常通过', _is_success(r1), f'code={r1.get("code")} msg={r1.get("msg")}')
    time.sleep(1)
    params2 = _signed(app, {'username': '重放', 'password': PASS})
    params2['nonce'] = nonce
    params2['sign'] = build_sign(params2, app[1])
    r2 = _response(Client().post(f'{BASE}/users/register', params2))
    _check('重放-同 nonce 更换时间戳仍被拒', r2.get('code') == 20011 and 'nonce' in r2.get('msg', ''),
           f'code={r2.get("code")} msg={r2.get("msg")}')


# ───────────────────────── 第四轮：认证安全 ─────────────────────────

def round4():
    _section('第四轮 认证安全')
    app_a = _create_app()
    app_b = _create_app()

    user = _create_user(app=app_a, username='安全测试')
    acc = user.account

    # 错误密码
    r = _login(app_a, acc, 'wrong-pass-000')
    _check('登录-错误密码', r.get('code') == 20011 and '账号或密码错误' in r.get('msg', ''))

    # 不存在账号（与错误密码提示一致，不泄露账号是否存在）
    r = _login(app_a, '00000000', PASS)
    _check('登录-不存在账号', r.get('code') == 20011 and '账号或密码错误' in r.get('msg', ''))

    # 正常登录
    r = _login(app_a, acc, PASS)
    token_a = (r.get('data') or {}).get('token')
    _check('登录-正常获取 token', bool(token_a))

    # 跨项目验证：token_a 在项目 B 验证失败
    r = _verify(app_b, token_a)
    _check('验证-跨项目 token 无效', r.get('code') == 20010 and '不属于当前项目' in r.get('msg', ''))

    # 跨项目信息：token_a 在项目 B 查信息失败
    r = _info(app_b, token_a)
    _check('信息-跨项目 token 无效', r.get('code') == 20010)

    # 项目 B 自己的 token 与项目 A 的 token 不同
    r = _login(app_b, acc, PASS)
    token_b = (r.get('data') or {}).get('token')
    _check('同用户不同项目 token 不同', bool(token_b) and token_b != token_a)

    # 伪造 token
    r = _verify(app_a, secrets.token_hex(32))
    _check('验证-伪造 token', r.get('code') == 20010)

    # 超长 token
    r = _verify(app_a, 'x' * 300)
    _check('验证-超长 token', r.get('code') == 20010)

    # 封禁用户
    user.status = False
    user.save()
    r = _login(app_a, acc, PASS)
    _check('登录-封禁用户', r.get('code') == 20011 and '封禁' in r.get('msg', ''))
    r = _verify(app_a, token_a)
    _check('验证-封禁用户 token 失效', r.get('code') == 20010)

    # 恢复用户，再验证 token 恢复有效
    user.status = True
    user.save()
    r = _verify(app_a, token_a)
    _check('验证-解封后 token 恢复有效', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 退出不存在的 token
    r = _logout(app_a, secrets.token_hex(32))
    _check('退出-不存在的 token', r.get('code') == 20003)

    # 停用项目后，该项目连调用验证接口的签名都会被拒（比 token 失效更严格，属正确安全设计）
    app_obj = app_a[2]
    app_obj.status = False
    app_obj.save()
    r = _verify(app_a, token_a)
    _check('验证-项目停用后接口被签名层拒绝', r.get('code') == 20011 and '停用' in r.get('msg', ''))


# ───────────────────────── 第五轮：系统健壮性 ─────────────────────────

def round5():
    _section('第五轮 系统健壮性')
    app = _create_app()

    # 批量注册 50 用户
    accounts = set()
    ok_count = 0
    for i in range(50):
        r = _register(app, f'批量{i}', f'pwd{i:04d}x')
        if _is_success(r):
            ok_count += 1
            acc = (r.get('data') or {}).get('account')
            accounts.add(acc)
            uid = (r.get('data') or {}).get('user_id')
            _created_users.append(uid)
    _check('批量注册 50 个全部成功', ok_count == 50, f'ok={ok_count}')
    _check('批量注册账号全部唯一', len(accounts) == 50)
    _check('批量注册账号均 6-12 位纯数字', all(a.isdigit() and 6 <= len(a) <= 12 for a in accounts))

    # 用户名允许重复
    r1 = _register(app, '同名用户', PASS)
    r2 = _register(app, '同名用户', PASS)
    _check('同用户名重复注册成功', _is_success(r1) and _is_success(r2))
    uid1, uid2 = (r1.get('data') or {}).get('user_id'), (r2.get('data') or {}).get('user_id')
    _check('同用户名不同 user_id', uid1 and uid2 and uid1 != uid2)
    if uid1:
        _created_users.append(uid1)
    if uid2:
        _created_users.append(uid2)

    # 密码不以明文入库
    user = _create_user(app=app, username='明文检查')
    db_user = User.objects.get(id=user.id)
    _check('密码不以明文存储', db_user.password != PASS and not db_user.password.startswith('pwd'))
    _check('密码为加盐哈希格式(含$分隔符)', '$' in db_user.password)

    # 同一用户同项目多 Token 并存（不做数量限制）
    acc = user.account
    tokens = set()
    for i in range(3):
        r = _login(app, acc, PASS)
        tok = (r.get('data') or {}).get('token')
        if tok:
            tokens.add(tok)
    _check('同项目多次登录生成 3 个不同 token', len(tokens) == 3)
    for t in tokens:
        r = _verify(app, t)
        if not _is_success(r):
            _check('并存 token 均有效', False, f'token={t[:8]}')
            break
    else:
        _check('并存 token 均有效', True)

    # 项目 Token 有效期配置生效（1 天 vs 7 天）
    app_short = _create_app(expire_days=1)
    r = _login(app_short, acc, PASS)
    data = (r.get('data') or {})
    _check('短有效期项目登录成功', _is_success(r))
    if data.get('expire_time'):
        from datetime import datetime, timezone as dt_tz
        from django.utils import timezone
        # expire_time 由 Django 存储为 UTC aware，解析后补上 UTC 时区再比较
        dt = datetime.strptime(data['expire_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt_tz.utc)
        span = (dt - timezone.now()).total_seconds()
        _check('短有效期项目 token 约 1 天过期', 86000 < span < 88000, f'span={span:.0f}s')

    # 方法限制：GET 调用 register（POST 接口）→ 认证通过后 Django 返回 405
    # （未带签名的请求会在认证层先被拦截返回 20011，故此处携带有效签名验证方法限制本身）
    r = Client().get(f'{BASE}/users/register', _signed(app, {'username': 'a', 'password': PASS}))
    _check('方法限制-GET 访问 register 返回405', r.status_code == 405, f'status={r.status_code}')

    # POST 调用 info（GET 接口）→ 405
    r = Client().post(f'{BASE}/users/info', _signed(app, {'token': 'x'}))
    _check('方法限制-POST 访问 info 返回405', r.status_code == 405, f'status={r.status_code}')

    # 账号生成格式抽查：注册 20 个验证分布长度覆盖 6-12
    lens = set()
    for i in range(20):
        r = _register(app, f'长度{i}', PASS)
        acc = (r.get('data') or {}).get('account')
        if acc:
            lens.add(len(acc))
            _created_users.append((r.get('data') or {}).get('user_id'))  # 登记清理
    _check('账号长度在 6-12 之间', all(6 <= x <= 12 for x in lens), f'lens={sorted(lens)}')


# ───────────────────────── 第六轮：并发与唯一性 ─────────────────────────

def round6():
    from concurrent.futures import ThreadPoolExecutor

    _section('第六轮 并发与唯一性')

    # 1. 并发创建 15 个项目：APPID/APPSECRET 自动生成、全局唯一、格式正确
    def create_project(i):
        return UserApp.objects.create(
            name=f'{_PREFIX}并发项目{i}', token_expire_days=7, status=True,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        objs = list(pool.map(create_project, range(15)))
    for o in objs:
        _created_apps.append((o.app_id, o.app_secret, o))
    app_ids = [o.app_id for o in objs]
    app_secrets = [o.app_secret for o in objs]
    _check('并发创建 15 个项目全部成功', len(objs) == 15, f'实际={len(objs)}')
    _check('并发创建 app_id 全部唯一', len(set(app_ids)) == 15)
    _check('app_id 均为 app_ 前缀', all(a.startswith('app_') for a in app_ids))
    _check('app_id 长度均为 32', all(len(a) == 32 for a in app_ids), f'lens={sorted({len(a) for a in app_ids})}')
    _check('app_secret 均为 sk_ 前缀', all(s.startswith('sk_') for s in app_secrets))
    _check('app_secret 长度均为 63', all(len(s) == 63 for s in app_secrets), f'lens={sorted({len(s) for s in app_secrets})}')

    # 2. 应用名称全局唯一：重复名称创建必须失败
    app0 = objs[0]
    try:
        UserApp.objects.create(name=app0.name)
        _check('应用名称唯一-重复名称被拒绝', False)
    except IntegrityError:
        _check('应用名称唯一-重复名称被拒绝', True)

    # 3. 创建后密钥固定不可修改：更新名称/手动改密钥均被还原
    app0.name = f'{_PREFIX}改名项目'
    app0.app_id = 'app_' + 'f' * 28
    app0.app_secret = 'sk_' + 'f' * 60
    app0.save()
    app0.refresh_from_db()
    _check('更新名称后密钥保持原值', app0.app_id in app_ids and app0.app_secret in app_secrets)
    _check('手动修改密钥被还原', not app0.app_id.startswith('app_ffff'), f'app_id={app0.app_id}')

    # 4. 并发注册 20 用户：全部成功、账号唯一
    app = _create_app()

    def do_register(i):
        return _register(app, f'并发用户{i}', f'pwd{i:04d}x')

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(do_register, range(20)))
    accs = []
    ok_reg = True
    for r in results:
        if not _is_success(r):
            ok_reg = False
            break
        accs.append((r.get('data') or {}).get('account'))
        _created_users.append((r.get('data') or {}).get('user_id'))
    _check('并发注册 20 个全部成功', ok_reg, f'code={r.get("code")} msg={r.get("msg")}')
    _check('并发注册账号全部唯一', len(set(accs)) == 20, f'实际={len(set(accs))}')
    _check('并发注册账号均为 6-12 位纯数字', all(a and a.isdigit() and 6 <= len(a) <= 12 for a in accs))

    # 5. 并发登录同一用户 10 次：Token 全部唯一且均有效
    user = _create_user(app=app, username='并发登录用户')
    acc = user.account

    def do_login(i):
        return _login(app, acc, PASS)

    with ThreadPoolExecutor(max_workers=8) as pool:
        login_results = list(pool.map(do_login, range(10)))
    tokens = []
    ok_login = True
    for r in login_results:
        if not _is_success(r):
            ok_login = False
            break
        tokens.append((r.get('data') or {}).get('token'))
    _check('并发登录 10 次全部成功', ok_login)
    _check('并发登录 token 全部唯一', len(set(tokens)) == 10, f'实际={len(set(tokens))}')
    all_valid = all(_is_success(_verify(app, t)) for t in tokens)
    _check('并发登录 token 均有效', all_valid)


# ───────────────────────── 清理与汇总 ─────────────────────────

def cleanup():
    from API.models import User
    # 删除测试用户与测试项目（Token 随 user/app 级联删除）
    deleted_apps = UserApp.objects.filter(id__in=[e[2].id for e in _created_apps]).delete()
    deleted_users = User.objects.filter(id__in=_created_users).delete()
    _log(f'\n[清理] 删除测试项目 {deleted_apps[0]} 个，测试用户 {deleted_users[0]} 个')


def main():
    if os.path.exists(_LOG_FILE):
        os.remove(_LOG_FILE)  # 每次运行前清空上次日志
    _log(f'用户中心 API 多轮测试开始（前缀 {_PREFIX}）')
    try:
        round1()
        round2()
        round3()
        round4()
        round5()
        round6()
    finally:
        cleanup()

    total = _stats['pass'] + _stats['fail']
    _log(f'\n========== 测试汇总 ==========')
    _log(f'通过: {_stats["pass"]}  |  失败: {_stats["fail"]}  |  总计: {total}')
    if _stats['fail']:
        _log('结论: 存在失败用例，请检查 ❌')
        sys.exit(1)
    _log('结论: 全部用例通过 ✅')


if __name__ == '__main__':
    main()
