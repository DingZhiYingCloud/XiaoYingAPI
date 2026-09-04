"""认证方式（邮箱/手机号/用户名）多轮极端/边缘/安全/并发测试

覆盖范围（两步注册 + 验证码登录语义）：
    第一轮 手机号两步注册完整闭环（发码暂存意向不建号 → 校验通过才建号发放账号 → 验证码登录）
    第二轮 邮箱两步注册闭环（含激活链接建号）+ 邮箱验证码登录
    第三轮 邮箱+手机号双凭证同时注册（批次合并同一账号）
    第四轮 后台开关切换（AuthMethod 控制：邮箱/手机号可单独开/关/全关降级用户名）
    第五轮 边界与安全（格式/重复/意向/过期/错误码/冷却防刷/登录不泄露凭证）
    第六轮 并发与唯一性（并发验证原子消费/并发注册/并发登录/冷却拦截）
    第七轮 methods 公开配置接口（免签名可访问、状态与后台一致）

说明：
    - 发信层使用 mock（send_email / 阿里云短信），聚焦逻辑与安全，
      真实 SMTP 端到端收发由 scripts/test_email_register.py 覆盖
    - 验证码从 user_verify_record 记录中读取（本地落库校验）
    - 使用真实数据库，测试结束自动清理测试数据并恢复 AuthMethod 原开关状态

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_auth_methods.py
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

# 测试提速：临时切换为 MD5 哈希器（仅影响本进程）
from django.conf import settings
from django.contrib.auth.hashers import MD5PasswordHasher

settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

from django.test import Client

from API.apis.user_center import users
from API.apis.user_center.users import utils as user_utils
from API.apis.user_center.sign import build_sign
from API.common.credential_crypto import hash_token
from API.models import AuthMethod, User, UserApp, UserVerifyRecord

# ───────────────────────── 发信层 mock ─────────────────────────

def _mock_send_email(subject, text, to_list, html_body=None):
    """mock 发信：不真正发送，返回成功（测试聚焦业务逻辑）"""
    return True, 'mock-sent'


def _mock_aliyun_send(phone, **kwargs):
    """mock 阿里云短信：生成并返回验证码（模拟 return_verify_code=true 服务端接收）"""
    code_length = kwargs.get('code_length', 6)
    code = ''.join(random.choices('0123456789', k=code_length))
    return True, {'biz_id': 'mock-biz', 'verify_code': code}


# 在模块加载时替换 utils 中的发信函数（对全部测试线程生效）
user_utils.send_email = _mock_send_email
user_utils.aliyun_send_verify_code = _mock_aliyun_send

# ───────────────────────── 测试基础设施 ─────────────────────────

BASE = '/api/user_center'
PASS = 'pass123456'
_PREFIX = f'AT{int(time.time())}'

_stats = {'pass': 0, 'fail': 0}
_created_apps = []         # (app_id, app_secret, UserApp)
_created_users = []        # user_id
_created_credentials = []  # (type, credential) 用于清理含 user=None 的注册意向记录
_orig_methods = {}         # AuthMethod 原开关快照 {type: enabled}
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_auth_methods_result.log')


def _log(msg):
    print(msg)
    with open(_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def _section(title):
    _log(f'\n===== {title} =====')


def _check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        _log(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        _log(f'  [FAIL] {name} {extra}')


def _signed(app, extra=None):
    """构造签名参数"""
    extra = {k: v for k, v in (extra or {}).items() if v is not None}
    params = {
        'app_id': app[0],
        'timestamp': str(int(time.time())),
        'nonce': secrets.token_hex(8),
    }
    if extra:
        params.update(extra)
    params['sign'] = build_sign(params, app[1])
    return params


def _create_app(name=None, status=True):
    obj = UserApp.objects.create(
        name=name or f'{_PREFIX}项目{len(_created_apps)}',
        token_expire_days=7, status=status,
    )
    entry = (obj.app_id, obj.app_secret, obj)
    _created_apps.append(entry)
    return entry


def _response(resp):
    import json
    return json.loads(resp.content.decode('utf-8'))


def _is_success(resp):
    return resp.get('code') == 10000


def _register(app, email=None, phone=None, username=None, password=PASS):
    return _response(Client().post(f'{BASE}/users/register', _signed(app, {
        'username': username, 'email': email, 'phone': phone, 'password': password,
    })))


def _login(app, account=None, email=None, phone=None, password=PASS, code=None):
    return _response(Client().post(f'{BASE}/users/login', _signed(app, {
        'account': account, 'email': email, 'phone': phone, 'password': password, 'code': code,
    })))


def _send_login_code(app, email=None, phone=None):
    """发送登录验证码（邮箱/手机号验证码登录第一步）"""
    return _response(Client().post(f'{BASE}/users/login/send', _signed(app, {
        'email': email, 'phone': phone,
    })))


def _verify_phone(app, phone, code):
    return _response(Client().post(f'{BASE}/users/verify/phone', _signed(app, {
        'phone': phone, 'code': code,
    })))


def _send_phone(app, phone):
    return _response(Client().post(f'{BASE}/users/verify/phone/send', _signed(app, {
        'phone': phone,
    })))


def _verify_email(app, email, code):
    return _response(Client().post(f'{BASE}/users/verify/email', _signed(app, {
        'email': email, 'code': code,
    })))


def _resend_email(app, email):
    return _response(Client().post(f'{BASE}/users/verify/email/resend', _signed(app, {
        'email': email,
    })))


def _methods():
    """公开接口（免签名）"""
    return _response(Client().get(f'{BASE}/users/methods'))


def _info(app, token):
    return _response(Client().get(f'{BASE}/users/info', _signed(app, {'token': token})))


def _verify_token(app, token):
    return _response(Client().post(f'{BASE}/users/verify', _signed(app, {'token': token})))


def _random_phone():
    """随机生成测试手机号（11 位，首位 1）"""
    return '1' + ''.join(random.choices('0123456789', k=10))


def _random_email(prefix='t'):
    return f'{prefix}_{_PREFIX.lower()}{random.randint(1000, 9999)}@example.com'.lower()


def _record_code(method, credential, scene=None):
    """读取最近一次未使用的验证码（本地落库，从 user_verify_record 读取）"""
    qs = UserVerifyRecord.objects.filter(type=method, credential=credential, is_used=False)
    if scene:
        qs = qs.filter(scene=scene)
    rec = qs.order_by('-create_time').first()
    return rec.code if rec else None


def _set_method(mtype, enabled):
    """后台切换验证方式开关"""
    AuthMethod.objects.filter(type=mtype).update(enabled=enabled)


def _expire_cooldown(method, credential):
    """模拟冷却已过：将该凭证全部验证记录创建时间改到 61 秒前

    注册发码与登录发码共用同一凭证的 60 秒冷却（防刷设计），
    测试在注册发码后立即测登录发码需先重置冷却。
    """
    from datetime import timedelta
    from django.utils import timezone
    UserVerifyRecord.objects.filter(type=method, credential=credential).update(
        create_time=timezone.now() - timedelta(seconds=61))


# ───────────────────────── 第一轮：手机号两步注册完整闭环 ─────────────────────────

def round1():
    _section('第一轮 手机号两步注册完整闭环')
    app = _create_app()
    phone = _random_phone()
    _created_credentials.append(('phone', phone))

    # 1. 两步注册第一步：仅暂存意向，不建号、不发放账号
    r = _register(app, phone=phone, username='手机用户')
    _check('手机号两步注册第一步成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    data = r.get('data') or {}
    _check('未发放账号(user_id 为空)', not data.get('user_id'), f'data={data}')
    _check('未发放账号(account 为空)', not data.get('account'))
    _check('标记需验证', data.get('need_verify') is True)
    _check('短信发送成功', data.get('verify_phone_sent') is True)
    _check('返回 phone', data.get('phone') == phone)
    _check('DB 中尚无该手机号用户', not User.objects.filter(phone=phone).exists())

    # 2. 重复发起注册被拒（意向查重）
    r = _register(app, phone=phone, username='重复')
    _check('重复发起注册被拒', not _is_success(r) and '已发起注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 3. 未发起意向的手机号验证被拒
    r = _verify_phone(app, _random_phone(), '123456')
    _check('无意向手机号验证被拒', not _is_success(r) and '未找到注册意向' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 4. 错误验证码
    r = _verify_phone(app, phone, '000000')
    _check('错误验证码被拒', not _is_success(r) and '验证码错误' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 5. 校验正确验证码 → 才建号、发放账号
    code = _record_code('phone', phone, scene='register')
    _check('注册验证码已落库', bool(code), f'code={code}')
    r = _verify_phone(app, phone, code)
    _check('两步注册第二步成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    d = r.get('data') or {}
    uid = d.get('user_id')
    _check('返回 user_id', bool(uid))
    _check('返回 account', bool(d.get('account')))
    _check('返回 phone', d.get('phone') == phone)
    _check('DB 已建号且手机号已验证',
           bool(uid) and User.objects.filter(id=uid, phone=phone, phone_verified=True).exists())
    if uid:
        _created_users.append(uid)

    # 6. 验证码一次性
    r = _verify_phone(app, phone, code)
    _check('验证码一次性-重复校验失败', not _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 7. 未获取登录码直接登录 → 参数缺失
    r = _login(app, phone=phone)
    _check('未获取登录码直接登录被拒', r.get('code') == 20001, f'code={r.get("code")}')

    # 8. 登录发码 → 校验 → 签发 Token
    _expire_cooldown('phone', phone)  # 注册发码在 60 秒冷却内，先重置冷却
    r = _send_login_code(app, phone=phone)
    _check('登录发码成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    r = _login(app, phone=phone, code='000000')
    _check('登录-错误验证码被拒', not _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    lcode = _record_code('phone', phone, scene='login')
    _check('登录验证码已落库', bool(lcode))
    r = _login(app, phone=phone, code=lcode)
    _check('验证码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    token = (r.get('data') or {}).get('token')
    _check('登录返回 token', bool(token))
    _check('登录返回 user_id 与注册一致', (r.get('data') or {}).get('user_id') == uid)

    # 9. 登录验证码一次性
    r = _login(app, phone=phone, code=lcode)
    _check('登录验证码一次性-重复登录失败', not _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 10. info / verify 携带手机号信息
    r = _info(app, token)
    _check('info 返回 phone', (r.get('data') or {}).get('phone') == phone)
    _check('info 返回 phone_verified=True', (r.get('data') or {}).get('phone_verified') is True)
    r = _verify_token(app, token)
    _check('verify 返回 phone_verified=True', (r.get('data') or {}).get('phone_verified') is True)


# ───────────────────────── 第二轮：邮箱两步注册闭环 ─────────────────────────

def round2():
    _section('第二轮 邮箱两步注册闭环（含激活链接）')
    app = _create_app()
    email = _random_email('reg')
    _created_credentials.append(('email', email))

    # 1. 两步注册第一步
    r = _register(app, email=email, username='邮箱用户')
    _check('邮箱两步注册第一步成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    data = r.get('data') or {}
    _check('未发放账号', not data.get('user_id'))
    _check('标记需验证', data.get('need_verify') is True)
    _check('验证邮件发送成功', data.get('verify_email_sent') is True)
    _check('返回 email', data.get('email') == email)
    _check('DB 中尚无该邮箱用户', not User.objects.filter(email=email).exists())

    # 2. 激活链接建号（link/both 模式下邮件含 token 链接）
    email2 = _random_email('link')
    _created_credentials.append(('email', email2))
    r = _register(app, email=email2, username='链接用户')
    _check('链接场景-第一步成功', _is_success(r))
    link = UserVerifyRecord.objects.filter(
        scene='register', type='email', credential=email2, is_used=False,
    ).order_by('-create_time').first()
    _check('意向含激活 token', bool(link and link.token))
    if link:
        # S-06: 激活 token 落库存哈希。模拟"邮件中携带的明文令牌"：
        # 自行生成已知明文并落库对应哈希，再以明文走公开 GET 激活链路
        raw_link = secrets.token_hex(16)
        UserVerifyRecord.objects.filter(pk=link.pk).update(token=hash_token(raw_link))
        r = _response(Client().get(f'{BASE}/users/verify/email', {'token': raw_link}))
        _check('激活链接校验后建号成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        _check('链接建号返回 account', bool((r.get('data') or {}).get('account')))
        _check('DB 已建号且邮箱已验证',
               User.objects.filter(email=email2, email_verified=True).exists())
        _created_users.append(str(User.objects.get(email=email2).id))

    # 3. 邮箱验证码完成注册
    code = _record_code('email', email, scene='register')
    _check('邮箱验证码已落库', bool(code))
    r = _verify_email(app, email, code)
    _check('邮箱验证码完成注册成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    uid = (r.get('data') or {}).get('user_id')
    if uid:
        _created_users.append(uid)

    # 4. 邮箱验证码登录
    _expire_cooldown('email', email)  # 注册发码在 60 秒冷却内，先重置冷却
    r = _send_login_code(app, email=email)
    _check('邮箱登录发码成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    r = _login(app, email=email, code=_record_code('email', email, scene='login'))
    _check('邮箱验证码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    _check('邮箱登录返回 user_id 与注册一致', (r.get('data') or {}).get('user_id') == uid)


# ───────────────────────── 第三轮：双凭证注册（批次合并） ─────────────────────────

def round3():
    _section('第三轮 邮箱+手机号双凭证注册（批次合并同一账号）')
    app = _create_app()
    phone = _random_phone()
    email = _random_email('dual')
    _created_credentials.append(('phone', phone))
    _created_credentials.append(('email', email))

    # 1. 双凭证第一步：共享批次、双验证码
    r = _register(app, email=email, phone=phone, username='双凭证用户')
    _check('双凭证第一步成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    data = r.get('data') or {}
    _check('未发放账号', not data.get('user_id'))
    _check('双验证信息均发送成功',
           data.get('verify_email_sent') is True and data.get('verify_phone_sent') is True)
    e_batch = UserVerifyRecord.objects.filter(
        scene='register', type='email', credential=email, is_used=False,
    ).values_list('register_batch', flat=True).first()
    p_batch = UserVerifyRecord.objects.filter(
        scene='register', type='phone', credential=phone, is_used=False,
    ).values_list('register_batch', flat=True).first()
    _check('双凭证共享同一批次', bool(e_batch) and e_batch == p_batch, f'e={e_batch} p={p_batch}')

    # 2. 先邮箱后手机号 → 合并为同一账号（不重复建号）
    r = _verify_email(app, email, _record_code('email', email, scene='register'))
    _check('邮箱校验建号成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    uid1 = (r.get('data') or {}).get('user_id')
    if uid1:
        _created_users.append(uid1)
    r = _verify_phone(app, phone, _record_code('phone', phone, scene='register'))
    _check('手机号校验合并成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    uid2 = (r.get('data') or {}).get('user_id')
    _check('合并为同一账号', uid1 == uid2 and bool(uid1), f'uid1={uid1} uid2={uid2}')

    user = User.objects.get(id=uid1)
    _check('同一账号同时绑定邮箱+手机号', user.email == email and user.phone == phone)
    _check('两个凭证均已验证', user.email_verified and user.phone_verified)

    # 3. 邮箱/手机号/账号三种方式均可登录
    _expire_cooldown('email', email)  # 注册发码在 60 秒冷却内，先重置冷却
    r = _send_login_code(app, email=email)
    _check('邮箱登录发码成功', _is_success(r))
    r = _login(app, email=email, code=_record_code('email', email, scene='login'))
    _check('邮箱验证码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    _expire_cooldown('phone', phone)  # 注册发码在 60 秒冷却内，先重置冷却
    r = _send_login_code(app, phone=phone)
    _check('手机号登录发码成功', _is_success(r))
    r = _login(app, phone=phone, code=_record_code('phone', phone, scene='login'))
    _check('手机号验证码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    r = _login(app, account=user.account, password=PASS)
    _check('账号+密码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')


# ───────────────────────── 第四轮：后台开关切换 ─────────────────────────

def round4():
    _section('第四轮 后台开关切换（AuthMethod）')
    app = _create_app()
    phone = _random_phone()
    email = _random_email('switch')
    _created_credentials.append(('phone', phone))
    _created_credentials.append(('email', email))

    # 先造一个邮箱已验证 + 一个手机号已验证用户（两步注册+verify）
    r = _register(app, email=email, username='开关邮箱用户')
    _check('开关测试-邮箱第一步', _is_success(r))
    r = _verify_email(app, email, _record_code('email', email, scene='register'))
    _check('开关测试-邮箱用户已建号', _is_success(r))
    _created_users.append((r.get('data') or {}).get('user_id'))
    r = _register(app, phone=phone, username='开关手机用户')
    _check('开关测试-手机第一步', _is_success(r))
    r = _verify_phone(app, phone, _record_code('phone', phone, scene='register'))
    _check('开关测试-手机用户已建号', _is_success(r))
    _created_users.append((r.get('data') or {}).get('user_id'))

    # 1. 仅关闭邮箱
    _set_method('email', False)
    r = _methods()
    _check('关闭邮箱后 methods=[phone]', (r.get('data') or {}).get('methods') == ['phone'],
           f'methods={(r.get("data") or {}).get("methods")}')
    r = _register(app, email=_random_email('x'), username='a')
    _check('邮箱注册被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _send_login_code(app, email=email)
    _check('邮箱登录发码被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _login(app, email=email, code='123456')
    _check('邮箱验证码登录被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _verify_email(app, email, '000000')
    _check('邮箱验证被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _resend_email(app, email)
    _check('邮箱重发被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    # 关闭邮箱时手机号注册/登录仍可用
    _phone2 = _random_phone()
    _created_credentials.append(('phone', _phone2))
    r = _register(app, phone=_phone2, username='关邮箱时手机注册')
    _check('关闭邮箱时手机号注册仍可用', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    if _is_success(r):
        r = _verify_phone(app, _phone2, _record_code('phone', _phone2, scene='register'))
        _check('关闭邮箱时手机号可完成注册', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        d = r.get('data') or {}
        _created_users.append(d.get('user_id'))
        r = _login(app, account=d.get('account'), password=PASS)
        _check('关闭邮箱时账号登录仍可用', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 2. 恢复邮箱，仅关闭手机号
    _set_method('email', True)
    _set_method('phone', False)
    r = _methods()
    _check('仅关闭手机号后 methods=[email]', (r.get('data') or {}).get('methods') == ['email'],
           f'methods={(r.get("data") or {}).get("methods")}')
    r = _register(app, phone=_random_phone(), username='b')
    _check('手机号注册被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _send_login_code(app, phone=phone)
    _check('手机号登录发码被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _verify_phone(app, phone, '000000')
    _check('手机号验证被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _send_phone(app, phone)
    _check('手机号重发被拒', not _is_success(r) and '未启用' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    # 关闭手机号时邮箱注册仍可用
    _email3 = _random_email('y')
    _created_credentials.append(('email', _email3))
    r = _register(app, email=_email3, username='关手机时邮箱注册')
    _check('关闭手机号时邮箱注册仍可用', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    if _is_success(r):
        r = _verify_email(app, _email3, _record_code('email', _email3, scene='register'))
        _check('关闭手机号时邮箱可完成注册', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        _created_users.append((r.get('data') or {}).get('user_id'))

    # 3. 全部关闭 → 降级用户名+密码
    _set_method('email', False)
    _set_method('phone', False)
    r = _methods()
    _check('全部关闭后 methods=[]', (r.get('data') or {}).get('methods') == [],
           f'methods={(r.get("data") or {}).get("methods")}')
    _check('methods 返回 username=True', (r.get('data') or {}).get('username') is True)
    r = _register(app, email=_random_email('z'), username='c')
    _check('全部关闭时邮箱注册被拒', not _is_success(r))
    r = _register(app, phone=_random_phone(), username='d')
    _check('全部关闭时手机号注册被拒', not _is_success(r))
    r = _register(app, username='纯用户名注册', password=PASS)
    _check('全部关闭时用户名注册可用', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    if _is_success(r):
        _created_users.append((r.get('data') or {}).get('user_id'))
        r = _login(app, account=(r.get('data') or {}).get('account'), password=PASS)
        _check('全部关闭时账号登录可用', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 4. 恢复全部开启 → 一切恢复
    _set_method('email', True)
    _set_method('phone', True)
    r = _methods()
    _check('恢复后 methods=[email, phone]', (r.get('data') or {}).get('methods') == ['email', 'phone'],
           f'methods={(r.get("data") or {}).get("methods")}')
    _phone5 = _random_phone()
    _created_credentials.append(('phone', _phone5))
    r = _register(app, phone=_phone5, username='恢复后注册')
    _check('恢复后手机号注册可用', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    if _is_success(r):
        r = _verify_phone(app, _phone5, _record_code('phone', _phone5, scene='register'))
        _check('恢复后手机号可完成注册', _is_success(r))
        _created_users.append((r.get('data') or {}).get('user_id'))


# ───────────────────────── 第五轮：边界与安全 ─────────────────────────

def round5():
    _section('第五轮 边界与安全')
    app = _create_app()

    # 1. 手机号格式边界（两步注册第一步同样校验）
    phone_cases = [
        ('phone 缺失(纯用户名注册)', {'username': 'x', 'password': PASS}, 10000),
        ('phone 10位', {'username': 'x', 'phone': '1380013800', 'password': PASS}, 20002),
        ('phone 12位', {'username': 'x', 'phone': '138001380000', 'password': PASS}, 20002),
        ('phone 含字母', {'username': 'x', 'phone': '1380013800a', 'password': PASS}, 20002),
        ('phone 含空格', {'username': 'x', 'phone': '138 0013 8000', 'password': PASS}, 20002),
        ('phone 非11位数字开头非1', {'username': 'x', 'phone': '23800138000', 'password': PASS}, 10000),
    ]
    for name, extra, expect in phone_cases:
        r = _register(app, **extra)
        _check(f'注册-{name}', r.get('code') == expect, f'code={r.get("code")} msg={r.get("msg")}')
        uid = (r.get('data') or {}).get('user_id')
        if r.get('code') == 10000 and uid:
            _created_users.append(uid)
        # 两步注册成功会暂存意向（不建号），纳入清理范围防残留影响下次运行
        if r.get('code') == 10000 and (r.get('data') or {}).get('phone'):
            _created_credentials.append(('phone', (r.get('data') or {}).get('phone')))

    # 2. 重复手机号 / 重复邮箱（完成注册建号后再次注册）
    phone = _random_phone()
    _created_credentials.append(('phone', phone))
    r = _register(app, phone=phone, username='重复1')
    _check('手机号首次注册成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    r = _verify_phone(app, phone, _record_code('phone', phone, scene='register'))
    _created_users.append((r.get('data') or {}).get('user_id'))
    r = _register(app, phone=phone, username='重复2')
    _check('重复手机号注册被拒', not _is_success(r) and '已被注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    email = _random_email('dup')
    _created_credentials.append(('email', email))
    r = _register(app, email=email, username='重复E1')
    _check('邮箱首次注册成功', _is_success(r))
    r = _verify_email(app, email, _record_code('email', email, scene='register'))
    _created_users.append((r.get('data') or {}).get('user_id'))
    r = _register(app, email=email.upper(), username='重复E2')
    _check('重复邮箱(大小写)注册被拒', not _is_success(r) and '已被注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 3. 验证码边界
    phone2 = _random_phone()
    _created_credentials.append(('phone', phone2))
    r = _register(app, phone=phone2, username='验证边界')
    _check('验证边界-第一步成功', _is_success(r))
    r = _verify_phone(app, phone2, '')
    _check('验证-缺 code', r.get('code') == 20001, f'code={r.get("code")}')
    r = _verify_phone(app, '', '123456')
    _check('验证-缺 phone', r.get('code') == 20001, f'code={r.get("code")}')
    r = _verify_phone(app, phone2, '000000')
    _check('验证-错误验证码', not _is_success(r) and '验证码错误' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _verify_phone(app, _random_phone(), '123456')
    _check('验证-未发起意向手机号', not _is_success(r) and '未找到注册意向' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 4. 验证码过期（直接改库制造过期记录）
    from datetime import timedelta
    from django.utils import timezone
    code = _record_code('phone', phone2, scene='register')
    UserVerifyRecord.objects.filter(scene='register', type='phone', credential=phone2, is_used=False).update(
        expire_time=timezone.now() - timedelta(minutes=1))
    r = _verify_phone(app, phone2, code)
    _check('验证-过期验证码被拒', not _is_success(r) and '过期' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 5. 重发边界
    r = _send_phone(app, _random_phone())
    _check('重发-未发起意向手机号被拒', not _is_success(r) and '未找到注册意向' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    phone3 = _random_phone()
    _created_credentials.append(('phone', phone3))
    r = _register(app, phone=phone3, username='重发用户')
    _check('重发用户-第一步成功', _is_success(r))
    r = _send_phone(app, phone3)
    _check('重发-60秒冷却被拒', not _is_success(r) and '频繁' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _verify_phone(app, phone3, _record_code('phone', phone3, scene='register'))
    _check('重发用户完成注册', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    _created_users.append((r.get('data') or {}).get('user_id'))
    r = _send_phone(app, phone3)
    _check('重发-完成注册后无意向被拒', not _is_success(r) and '未找到注册意向' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 6. 登录安全（不泄露凭证是否存在）
    r = _send_login_code(app, phone=_random_phone())
    _check('登录发码-未注册手机号被拒', not _is_success(r) and '未注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    r = _login(app, account='12345678', password='whatever')
    _check('登录-错误账号统一提示', r.get('code') == 20011 and '账号或密码错误' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')
    acc = User.objects.get(phone=phone3).account
    r = _login(app, account=acc, password='wrong-pass-999')
    _check('登录-错误密码统一提示', r.get('code') == 20011 and '账号或密码错误' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 7. 注册-密码缺失 / 过短（带手机号时同样生效）
    r = _register(app, phone=_random_phone(), username='x', password='')
    _check('注册-手机号+缺密码', r.get('code') == 20001, f'code={r.get("code")}')
    r = _register(app, phone=_random_phone(), username='x', password='12345')
    _check('注册-手机号+密码过短', r.get('code') == 20002, f'code={r.get("code")}')

    # 8. 登录参数缺失
    r = _login(app, password=PASS)
    _check('登录-账号/邮箱/手机号全缺失', r.get('code') == 20001, f'code={r.get("code")}')


# ───────────────────────── 第六轮：并发与唯一性 ─────────────────────────

def round6():
    from concurrent.futures import ThreadPoolExecutor

    _section('第六轮 并发与唯一性')
    app = _create_app()

    # 1. 并发验证同一注册验证码：仅 1 个成功（原子消费）
    phone = _random_phone()
    _created_credentials.append(('phone', phone))
    r = _register(app, phone=phone, username='并发验证')
    _check('并发验证-第一步成功', _is_success(r))
    code = _record_code('phone', phone, scene='register')
    _check('并发验证-验证码已落库', bool(code))

    def do_verify(i):
        return _verify_phone(app, phone, code)

    with ThreadPoolExecutor(max_workers=6) as pool:
        v_results = list(pool.map(do_verify, range(6)))
    ok_cnt = sum(1 for r in v_results if _is_success(r))
    _check('并发验证同一注册码仅1个成功', ok_cnt == 1, f'success={ok_cnt}')
    _check('并发验证后仅建1个号', User.objects.filter(phone=phone).count() == 1)
    u = User.objects.get(phone=phone)
    _check('并发验证后手机号已验证', u.phone_verified is True)
    _created_users.append(str(u.id))

    # 2. 并发注册不同手机号：第一步全部成功
    def do_register_many(i):
        return _register(app, phone=_random_phone(), username=f'并发多号{i}')

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(do_register_many, range(15)))
    _check('并发注册15个不同手机号全部成功(第一步)', all(_is_success(r) for r in results),
           f'code={results[0].get("code")} msg={results[0].get("msg")}')

    # 3. 并发完成注册：账号唯一
    def do_complete(i):
        d = results[i].get('data') or {}
        ph = d.get('phone')
        _created_credentials.append(('phone', ph))
        return _verify_phone(app, ph, _record_code('phone', ph, scene='register'))

    with ThreadPoolExecutor(max_workers=8) as pool:
        c_results = list(pool.map(do_complete, range(15)))
    accs = []
    ok_all = True
    for r in c_results:
        if not _is_success(r):
            ok_all = False
            break
        accs.append((r.get('data') or {}).get('account'))
        _created_users.append((r.get('data') or {}).get('user_id'))
    _check('并发完成15个注册全部成功', ok_all, f'code={r.get("code")} msg={r.get("msg")}')
    _check('并发注册账号全部唯一', len(set(accs)) == 15, f'实际={len(set(accs))}')

    # 4. 并发账号密码登录同一用户：全部成功、token 唯一
    user = User.objects.filter(phone__isnull=False).first()
    acc = user.account

    def do_login(i):
        return _login(app, account=acc, password=PASS)

    with ThreadPoolExecutor(max_workers=8) as pool:
        login_results = list(pool.map(do_login, range(10)))
    tokens = []
    ok_login = True
    for r in login_results:
        if not _is_success(r):
            ok_login = False
            break
        tokens.append((r.get('data') or {}).get('token'))
    _check('并发登录10次全部成功', ok_login, f'code={r.get("code")} msg={r.get("msg")}')
    _check('并发登录 token 全部唯一', len(set(tokens)) == 10, f'实际={len(set(tokens))}')

    # 5. 并发登录发码：制造刚发送记录，冷却拦截全部
    from datetime import timedelta
    from django.utils import timezone
    phone2 = _random_phone()
    _created_credentials.append(('phone', phone2))
    r = _register(app, phone=phone2, username='并发发码')
    r = _verify_phone(app, phone2, _record_code('phone', phone2, scene='register'))
    _created_users.append((r.get('data') or {}).get('user_id'))
    u2 = User.objects.get(phone=phone2)
    # 手动创建一条「刚刚发送」的登录验证记录，确保 60 秒冷却生效（与测试执行时间无关）
    UserVerifyRecord.objects.create(
        user=u2, scene='login', type='phone', credential=phone2,
        code='123456', expire_time=timezone.now() + timedelta(minutes=5),
    )

    def do_send(i):
        return _send_login_code(app, phone=phone2)

    with ThreadPoolExecutor(max_workers=6) as pool:
        s_results = list(pool.map(do_send, range(6)))
    ok_cnt = sum(1 for r in s_results if _is_success(r))
    _check('并发登录发码全部被冷却拦截', ok_cnt == 0, f'success={ok_cnt}')


# ───────────────────────── 第七轮：methods 公开接口 ─────────────────────────

def round7():
    _section('第七轮 methods 公开配置接口')
    r = _methods()
    _check('methods 免签名可访问', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    data = r.get('data') or {}
    _check('methods 返回列表', isinstance(data.get('methods'), list))
    _check('methods 返回 username=True', data.get('username') is True)
    _check('methods 与后台一致',
           sorted(data.get('methods')) == sorted(user_utils.get_enabled_methods()),
           f'api={data.get("methods")} db={user_utils.get_enabled_methods()}')
    # GET 非公开接口仍要求签名（methods 免签名不影响 verify/email 链接路径）
    r = _response(Client().get(f'{BASE}/users/info', {'token': 'x'}))
    _check('info 无签名仍被拒', r.get('code') == 20011, f'code={r.get("code")} msg={r.get("msg")}')


# ───────────────────────── 清理与汇总 ─────────────────────────

def cleanup():
    # 恢复 AuthMethod 原始开关状态（测试期间可能被 round4 改动）
    for mtype, enabled in _orig_methods.items():
        AuthMethod.objects.filter(type=mtype).update(enabled=enabled)
    deleted_apps = UserApp.objects.filter(id__in=[e[2].id for e in _created_apps]).delete()
    deleted_users = User.objects.filter(id__in=_created_users).delete()
    # 清理验证记录（含两步注册意向 user=None 的记录）
    deleted_verify = 0
    for mtype, cred in _created_credentials:
        deleted_verify += UserVerifyRecord.objects.filter(type=mtype, credential=cred).delete()[0]
    _log(f'\n[清理] 删除测试项目 {deleted_apps[0]} 个，测试用户 {deleted_users[0]} 个，'
         f'验证记录 {deleted_verify} 条，恢复 AuthMethod 开关 {dict(_orig_methods)}')


def main():
    if os.path.exists(_LOG_FILE):
        os.remove(_LOG_FILE)
    _log(f'认证方式多轮测试开始（前缀 {_PREFIX}）')
    try:
        for m in AuthMethod.objects.all():
            _orig_methods[m.type] = m.enabled
        round1()
        round2()
        round3()
        round4()
        round5()
        round6()
        round7()
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