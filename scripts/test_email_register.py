"""邮箱注册/登录 端到端测试（使用 minmail 虚拟邮箱接收验证邮件）

覆盖范围：
    第一轮 邮箱两步注册闭环（注册发码暂存意向不建号 → 收验证邮件 → 验证码校验通过才建号 → 邮箱验证码登录）
    第二轮 激活链接激活（GET verify/email?token=xxx，公开访问无需签名，校验通过才建号）
    第三轮 边界与安全（意向查重/重复注册/错误验证码/登录发码/重发冷却）
    第四轮 邮箱唯一性 & 邮件模板后台自定义（创建 EmailTemplate 后渲染生效）

依赖真实 SMTP 发信（settings 中 QQ 邮箱）+ minmail.app 虚拟邮箱收信，
测试结束后自动清理测试数据。

运行方式（使用真实数据库）：
    .venv\\Scripts\\python.exe scripts\\test_email_register.py
"""
import os
import random
import re
import secrets
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

# 测试提速：PBKDF2 默认迭代次数极高，临时切换为 MD5 哈希器（仅影响本进程）
from django.conf import settings
from django.contrib.auth.hashers import MD5PasswordHasher

settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

from django.test import Client
from django.db import IntegrityError

from API.models import EmailTemplate, User, UserApp, UserVerifyRecord
from API.apis.user_center.sign import build_sign
from SpiderServices.VMEmail_minmail.main import VMEmailMinmailSpider

# ───────────────────────── 测试基础设施 ─────────────────────────

BASE = '/api/user_center'
PASS = 'pass123456'
_PREFIX = f'ET{int(time.time())}'

_stats = {'pass': 0, 'fail': 0}
_created_apps = []   # (app_id, app_secret, UserApp)
_created_users = []  # user_id
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_email_register_result.log')


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


def _register(app, email, username=None, password=PASS):
    return _response(Client().post(f'{BASE}/users/register', _signed(app, {
        'username': username, 'email': email, 'password': password,
    })))


def _login_email(app, email):
    """邮箱验证码登录：先发登录验证码，再校验通过签发 Token（两步注册新语义，邮箱登录免密码）"""
    r = _send_login_code(app, email)
    if not _is_success(r):
        return r
    code = _record_code(email, scene='login')
    if not code:
        return r
    return _response(Client().post(f'{BASE}/users/login', _signed(app, {
        'email': email, 'code': code,
    })))


def _send_login_code(app, email):
    """发送邮箱登录验证码"""
    return _response(Client().post(f'{BASE}/users/login/send', _signed(app, {
        'email': email,
    })))


def _record_code(email, scene='login'):
    """从本地 user_verify_record 读取指定场景最近一次未使用的验证码"""
    rec = UserVerifyRecord.objects.filter(
        type='email', credential=email, scene=scene, is_used=False,
    ).order_by('-create_time').first()
    return rec.code if rec else None


def _expire_cooldown(email):
    """模拟冷却已过：将该邮箱全部验证记录创建时间改到 61 秒前

    注册发码与登录发码共用同一凭证的 60 秒冷却（防刷设计），
    注册发码后立即测登录发码需先重置冷却。
    """
    from datetime import timedelta
    from django.utils import timezone
    UserVerifyRecord.objects.filter(type='email', credential=email).update(
        create_time=timezone.now() - timedelta(seconds=61))


def _verify_code(app, email, code):
    return _response(Client().post(f'{BASE}/users/verify/email', _signed(app, {
        'email': email, 'code': code,
    })))


def _resend(app, email):
    return _response(Client().post(f'{BASE}/users/verify/email/resend', _signed(app, {
        'email': email,
    })))


def _wait_for_email(spider, timeout=60, interval=5):
    """轮询 minmail 邮箱直至收到新邮件，返回邮件 dict 或 None"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            emails = spider.get_emails()
            if emails:
                return emails[0]
        except Exception:
            pass
        _log(f'  [wait] 尚未收到邮件，{interval}s 后重试...')
        time.sleep(interval)
    return None


def _extract_code_and_link(content):
    """从邮件正文中提取 6 位验证码与激活链接

    验证码可能独立成段（默认模板 <p>123456</p>）或带前缀文本
    （自定义模板 <p>验证码: 123456</p>），故先精确匹配 p 标签，再回退到任意独立 6 位数字。
    """
    m = re.search(r'<p[^>]*>\s*(\d{6})\s*</p>', content)
    if m:
        code = m.group(1)
    else:
        m = re.search(r'(?<!\d)\d{6}(?!\d)', content)
        code = m.group(0) if m else None
    m = re.search(r'https?://[^\s"\'<>]+token=([0-9a-f]+)', content)
    token = m.group(1) if m else None
    return code, token


# ───────────────────────── 第一轮：邮箱注册完整闭环 ─────────────────────────

def round1():
    _section('第一轮 邮箱注册 → 验证码激活 → 邮箱登录')
    app = _create_app()
    spider = VMEmailMinmailSpider()
    email_info = spider.generate_email()
    addr = email_info['address']
    _log(f'  虚拟邮箱: {addr} (visitor_id={email_info["visitor_id"][:8]}...)')

    # 1. 邮箱注册（两步注册第一步：仅暂存注册意向并下发验证码，不建号）
    r = _register(app, addr, username='邮箱用户')
    _check('邮箱注册成功 code=10000', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    data = r.get('data') or {}
    _check('两步注册第一步不发放账号(user_id 为空)', not data.get('user_id'))
    _check('两步注册第一步不发放账号(account 为空)', not data.get('account'))
    _check('注册返回邮箱', data.get('email') == addr)
    _check('注册标记需验证', data.get('need_verify') is True, f'need_verify={data.get("need_verify")}')
    _check('验证邮件发送成功', data.get('verify_email_sent') is True, f'sent={data.get("verify_email_sent")}')

    # 2. 未获取登录验证码直接邮箱登录应被拒（缺 code）
    r = _response(Client().post(f'{BASE}/users/login', _signed(app, {'email': addr})))
    _check('未获取登录验证码直接邮箱登录被拒', r.get('code') == 20001,
           f'code={r.get("code")} msg={r.get("msg")}')

    # 3. 轮询虚拟邮箱收取验证邮件
    mail = _wait_for_email(spider)
    _check('虚拟邮箱收到验证邮件', mail is not None)
    if mail:
        _log(f'  邮件主题: {mail.get("subject")}')
        _log(f'  发件人: {mail.get("fromAddress")}')
        content = mail.get('content') or mail.get('preview') or ''
        code, token = _extract_code_and_link(content)
        _check('邮件含 6 位验证码', bool(code), f'code={code}')
        _check('邮件含激活链接 token', bool(token), f'token={token[:8] if token else None}...')

        # 4. 验证码激活（两步注册第二步：校验通过才创建账号、发放账号）
        r = _verify_code(app, addr, code)
        _check('验证码激活成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        d = r.get('data') or {}
        _check('激活返回 email', d.get('email') == addr)
        _check('激活后发放账号(user_id)', bool(d.get('user_id')))
        _check('激活后发放账号(account)', bool(d.get('account')))
        uid = d.get('user_id')
        acc = d.get('account')
        if uid:
            _created_users.append(uid)

        # 5. 验证码一次性：重复使用失败
        r = _verify_code(app, addr, code)
        _check('验证码一次性-重复激活失败', not _is_success(r), f'code={r.get("code")}')

        # 6. 邮箱验证码登录成功（免密码，校验通过后签发 Token）
        _expire_cooldown(addr)  # 注册发码在 60 秒冷却内，先重置冷却
        r = _login_email(app, addr)
        _check('邮箱验证码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        token_val = (r.get('data') or {}).get('token')
        _check('邮箱登录返回 token', bool(token_val))
        _check('登录返回 user_id 与激活一致', (r.get('data') or {}).get('user_id') == uid)

        # 7. 账号密码方式仍可登录
        r = _response(Client().post(f'{BASE}/users/login', _signed(app, {
            'account': acc, 'password': PASS,
        })))
        _check('系统账号+密码仍可登录', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
    else:
        _check('验证码激活', False, '未收到邮件，跳过后续激活断言')


# ───────────────────────── 第二轮：激活链接激活 ─────────────────────────

def round2():
    _section('第二轮 激活链接激活（GET 公开访问）')
    app = _create_app()
    spider = VMEmailMinmailSpider()
    addr = spider.generate_email()['address']
    _log(f'  虚拟邮箱: {addr}')

    r = _register(app, addr, username='链接用户')
    _check('邮箱注册成功', _is_success(r), f'msg={r.get("msg")}')

    mail = _wait_for_email(spider)
    _check('收到验证邮件', mail is not None)
    if mail:
        content = mail.get('content') or mail.get('preview') or ''
        code, token = _extract_code_and_link(content)
        _check('邮件含激活链接 token', bool(token))
        if token:
            # 模拟浏览器点击邮件内链接（无需签名），校验通过后创建账号、发放账号
            resp = Client().get(f'{BASE}/users/verify/email', {'token': token})
            r = _response(resp)
            _check('链接激活成功(公开访问)', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
            d = r.get('data') or {}
            _check('激活返回 email 正确', d.get('email') == addr)
            _check('链接激活后发放账号(user_id)', bool(d.get('user_id')))
            _check('链接激活后发放账号(account)', bool(d.get('account')))
            if d.get('user_id'):
                _created_users.append(d.get('user_id'))

            # 链接一次性
            r = _response(Client().get(f'{BASE}/users/verify/email', {'token': token}))
            _check('激活链接一次性-重复使用失效', not _is_success(r), f'code={r.get("code")}')

            # 激活后邮箱验证码登录成功
            _expire_cooldown(addr)  # 注册发码在 60 秒冷却内，先重置冷却
            r = _login_email(app, addr)
            _check('链接激活后邮箱验证码登录成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        else:
            _check('链接激活', False, '未提取到 token')
    else:
        _check('链接激活', False, '未收到邮件')


# ───────────────────────── 第三轮：边界与安全 ─────────────────────────

def round3():
    _section('第三轮 边界与安全')
    app = _create_app()
    spider = VMEmailMinmailSpider()
    addr = spider.generate_email()['address']
    _log(f'  虚拟邮箱: {addr}')

    # 1. 首次注册成功（两步注册第一步：仅暂存意向不建号）
    r = _register(app, addr, username='重复1')
    _check('首次注册成功', _is_success(r), f'msg={r.get("msg")}')
    _check('注册仅暂存意向不建号', not (r.get('data') or {}).get('user_id'))

    # 2. 意向查重：未完成验证前重复注册同一邮箱 → 已发起注册
    r = _register(app, addr, username='重复2')
    _check('未完成验证重复注册被拒', not _is_success(r) and '已发起注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 3. 大小写/空格邮箱归一化（小写去空格后仍判重）
    r = _register(app, f'  {addr.upper()}  ', username='重复3')
    _check('大小写+空格邮箱仍判重', not _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 4. 格式非法邮箱
    r = _register(app, 'not-an-email', username='非法邮箱')
    _check('非法邮箱格式被拒', r.get('code') == 20002, f'code={r.get("code")} msg={r.get("msg")}')

    # 5. 邮箱+用户名都不提供 → 拒绝
    r = _response(Client().post(f'{BASE}/users/register', _signed(app, {'password': PASS})))
    _check('username/email 均缺失被拒', r.get('code') == 20001)

    # 6. 错误验证码（两步注册第二步校验）
    r = _verify_code(app, addr, '000000')
    _check('错误验证码被拒', not _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')

    # 7. 未注册邮箱登录发码被拒
    r = _send_login_code(app, 'nobody@atminmail.com')
    _check('未注册邮箱登录发码被拒', not _is_success(r) and '未注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 8. 重发冷却（注册邮件已发送，立即重发应被冷却拦截）
    r = _resend(app, addr)
    _check('重发冷却-60秒内被拒', not _is_success(r) and '频繁' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 9. 收件确认：等收到注册邮件验证码后激活（校验通过才建号）
    mail = _wait_for_email(spider)
    if mail:
        content = mail.get('content') or mail.get('preview') or ''
        code, _ = _extract_code_and_link(content)
        r = _verify_code(app, addr, code)
        _check('第三轮邮箱验证码激活成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        _check('激活后发放账号', bool((r.get('data') or {}).get('user_id')))
        if (r.get('data') or {}).get('user_id'):
            _created_users.append((r.get('data') or {}).get('user_id'))

    # 10. 已建号后重复注册 → 已被注册
    r = _register(app, addr, username='重复4')
    _check('已建号重复邮箱注册被拒', not _is_success(r) and '已被注册' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')

    # 11. 已建号后重发 → 无注册意向被拒
    r = _resend(app, addr)
    _check('已建号邮箱重发被拒', not _is_success(r) and '未找到注册意向' in r.get('msg', ''),
           f'code={r.get("code")} msg={r.get("msg")}')


# ───────────────────────── 第四轮：模板后台自定义 ─────────────────────────

def round4():
    _section('第四轮 邮件模板后台自定义')
    app = _create_app()
    spider = VMEmailMinmailSpider()
    addr = spider.generate_email()['address']
    _log(f'  虚拟邮箱: {addr}')

    # 后台创建自定义模板（模拟 admin 后台录入）
    EmailTemplate.objects.create(
        type='email_verify',
        subject='【自定义】{{username}} 请验证邮箱',
        html_body='<html><body><h1>自定义模板</h1><p>验证码: {{code}}</p>'
                  '<a href="{{link}}">点此激活</a><p>{{expire_minutes}}分钟有效</p></body></html>',
        description='测试自定义模板',
    )

    r = _register(app, addr, username='模板用户')
    _check('使用自定义模板注册成功', _is_success(r), f'msg={r.get("msg")}')

    mail = _wait_for_email(spider)
    if mail:
        _log(f'  自定义模板邮件主题: {mail.get("subject")}')
        content = mail.get('content') or mail.get('preview') or ''
        _check('自定义模板标题生效', '自定义' in (mail.get('subject') or ''))
        _check('自定义模板正文生效', '自定义模板' in content)
        code, _ = _extract_code_and_link(content)
        _check('自定义模板渲染验证码', bool(code))
        r = _verify_code(app, addr, code)
        _check('自定义模板验证码激活成功', _is_success(r), f'code={r.get("code")} msg={r.get("msg")}')
        if (r.get('data') or {}).get('user_id'):
            _created_users.append((r.get('data') or {}).get('user_id'))

    # 清理模板记录，恢复内置默认模板（保持环境干净）
    EmailTemplate.objects.filter(type='email_verify').delete()


# ───────────────────────── 清理与汇总 ─────────────────────────

def cleanup():
    from API.models import User
    deleted_apps = UserApp.objects.filter(id__in=[e[2].id for e in _created_apps]).delete()
    deleted_users = User.objects.filter(id__in=_created_users).delete()
    EmailTemplate.objects.filter(type='email_verify').delete()
    _log(f'\n[清理] 删除测试项目 {deleted_apps[0]} 个，测试用户 {deleted_users[0]} 个')


def main():
    if os.path.exists(_LOG_FILE):
        os.remove(_LOG_FILE)
    _log(f'邮箱注册/登录端到端测试开始（前缀 {_PREFIX}）')
    try:
        round1()
        round2()
        round3()
        round4()
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
