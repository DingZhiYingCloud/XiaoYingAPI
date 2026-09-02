"""用户中心 - 用户业务逻辑

功能：
    register_user        - 注册（邮箱/手机号：两步注册第一步，发验证码暂存意向不建号；
                            纯用户名：直接建号）
    verify_by_code       - 两步注册第二步：校验验证码通过后才创建账号、发放账号
    login_user           - 登录（邮箱/手机号：验证码登录免密码；账号：账号+密码）
    send_login_code      - 发送登录验证码（校验通过后签发 Token）
    logout_user          - 退出（删除 Token）
    get_user_info        - 获取用户信息（校验 Token）
    verify_token         - 验证 Token（供子项目调用，返回用户身份）
    send_verify_code     - 重新发送两步注册的验证码（邮箱验证邮件 / 手机短信验证码）
    verify_by_token      - 邮箱激活链接：两步注册第二步（点击链接校验后建号）
    get_available_methods- 当前可用的注册/登录方式（客户端据此渲染入口）

验证方式由 AuthMethod 配置表控制（后台可开关，每种方式控制 注册/登录/验证 一体）：
    email - 邮箱：注册先发验证邮件（验证码+激活链接，形式由 settings.EMAIL_VERIFY_MODE 控制），
            校验通过后才发放账号；登录发验证码，校验通过后签发 Token
    phone - 手机号：注册先发短信验证码（复用阿里云 SendSmsVerifyCode，
            return_verify_code=true 服务端接收验证码后落库，本地比对校验），
            校验通过后才发放账号；登录发验证码，校验通过后签发 Token
全部关闭时降级为「用户名 + 密码」注册/登录（永远可用）。

所有函数返回 (success, data_or_msg) 二元组，异常内部捕获，调用方无需 try/except。
"""
import random
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.template import Context, Template
from django.utils import timezone

from API.apis.emails.v1.utils import send_email
from API.apis.sms_verify.aliyun.utils import send_verify_code as aliyun_send_verify_code
from API.models import AuthMethod, EmailTemplate, User, UserApp, UserToken, UserVerifyRecord

# 系统分配账号长度范围
ACCOUNT_MIN_LEN = 6
ACCOUNT_MAX_LEN = 12

# 密码长度约束
PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 64

# 用户名长度约束
USERNAME_MAX_LEN = 50

# 生成账号最大重试次数（避免极端并发下唯一冲突死循环）
ACCOUNT_RETRY_TIMES = 20

# 邮件模板类型
EMAIL_VERIFY_TEMPLATE_TYPE = 'email_verify'

# 重发验证码冷却时间（秒），防恶意刷信/刷短信
VERIFY_RESEND_COOLDOWN = 60

# ── 验证码场景（UserVerifyRecord.scene，区分验证码用途） ──
SCENE_REGISTER = 'register'  # 两步注册意向：发码暂存（不建号），校验通过后才创建账号
SCENE_LOGIN = 'login'        # 登录验证码：发码校验，通过后签发 Token

# ── 验证方式类型（与 AuthMethod.type 对应，后续新增验证方式在此追加常量 + 校验分支） ──
METHOD_EMAIL = 'email'
METHOD_PHONE = 'phone'
METHOD_NAMES = {
    METHOD_EMAIL: '邮箱',
    METHOD_PHONE: '手机号',
}

# 内置默认邮箱验证邮件模板（后台创建 EmailTemplate 记录后即被覆盖）
DEFAULT_EMAIL_VERIFY_SUBJECT = '{{username}}，验证您的邮箱'
DEFAULT_EMAIL_VERIFY_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{username}}，验证您的邮箱</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
          <tr>
            <td align="center" style="padding-bottom:24px;">
              <span style="font-size:22px;font-weight:700;letter-spacing:1px;background:linear-gradient(90deg,#4f7cff,#8b5cf6);-webkit-background-clip:text;background-clip:text;color:transparent;">小影API</span>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff;border-radius:16px;padding:40px 32px;box-shadow:0 8px 30px rgba(31,35,41,0.08);">
              <h1 style="margin:0 0 8px;font-size:20px;color:#1f2329;text-align:center;">验证您的邮箱</h1>
              <p style="margin:0 0 32px;font-size:14px;color:#8a919f;text-align:center;">欢迎加入小影API，完成验证后即可使用邮箱登录</p>
              {% if code %}
              <p style="margin:0 0 6px;font-size:13px;color:#646a73;text-align:center;">您的验证码为</p>
              <p style="margin:0 0 32px;font-size:32px;font-weight:700;letter-spacing:8px;color:#1f2329;text-align:center;">{{ code }}</p>
              {% endif %}
              {% if link %}
              <div style="text-align:center;margin-bottom:32px;">
                <a href="{{ link }}" style="display:inline-block;padding:12px 40px;border-radius:8px;background:linear-gradient(135deg,#4f7cff,#8b5cf6);color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;">立即验证邮箱</a>
              </div>
              {% endif %}
              <p style="margin:0 0 8px;font-size:13px;color:#8a919f;text-align:center;">验证码与链接 {{ expire_minutes }} 分钟内有效</p>
              <p style="margin:0;font-size:13px;color:#8a919f;text-align:center;">若非本人操作，请忽略此邮件</p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:24px 0 0;">
              <p style="margin:0;font-size:12px;color:#b8beca;">此邮件由小影API系统自动发送，请勿直接回复</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ==================== 验证方式配置 ====================

def get_enabled_methods():
    """当前后台启用的验证方式类型列表，如 ['email', 'phone']；空列表 = 仅用户名+密码"""
    try:
        return list(AuthMethod.objects.filter(enabled=True).values_list('type', flat=True))
    except Exception:
        # 迁移前/表不存在时兜底为空，避免阻塞注册登录
        return []


def is_method_enabled(method):
    """指定验证方式是否启用"""
    return method in get_enabled_methods()


def get_available_methods():
    """公开配置：当前可用的注册/登录方式（客户端据此渲染入口）

    :return: {'methods': ['email', 'phone'], 'username': True}
        methods  - 后台启用的验证方式列表（空列表 = 仅用户名+密码）
        username - 用户名+密码是否可用（永远为 True，作为兜底登录方式）
    """
    return {
        'methods': get_enabled_methods(),
        'username': True,
    }


# ==================== 基础工具 ====================

def generate_account() -> str:
    """随机生成全局唯一的纯数字账号（6-12 位，首位非 0）"""
    for _ in range(ACCOUNT_RETRY_TIMES):
        length = random.randint(ACCOUNT_MIN_LEN, ACCOUNT_MAX_LEN)
        first = random.choice('123456789')
        rest = ''.join(random.choice('0123456789') for _ in range(length - 1))
        account = first + rest
        if not User.objects.filter(account=account).exists():
            return account
    return None


def generate_email_code() -> str:
    """生成 6 位数字验证码"""
    return f'{random.randint(0, 999999):06d}'


def _validate_email(email):
    """校验邮箱格式，合法返回小写清洗后的值，否则返回 None"""
    email = (email or '').strip().lower()
    if not email:
        return None
    try:
        validate_email(email)
    except ValidationError:
        return None
    return email


def _validate_phone(phone):
    """校验手机号（中国大陆 11 位纯数字），合法返回清洗后的值，否则返回 None"""
    phone = (phone or '').strip()
    if not phone:
        return None
    if not (phone.isdigit() and len(phone) == 11):
        return None
    return phone


def _method_expire_minutes(method):
    """各验证方式验证码有效时长（分钟）"""
    if method == METHOD_PHONE:
        return settings.PHONE_VERIFY_EXPIRE_MINUTES
    return settings.EMAIL_VERIFY_EXPIRE_MINUTES


def _render_email_template(template_type, context):
    """渲染邮件模板（后台 EmailTemplate 记录优先，无则内置默认），返回 (subject, html)"""
    try:
        tpl = EmailTemplate.objects.get(type=template_type)
        subject_raw, html_raw = tpl.subject, tpl.html_body
    except EmailTemplate.DoesNotExist:
        subject_raw = DEFAULT_EMAIL_VERIFY_SUBJECT
        html_raw = DEFAULT_EMAIL_VERIFY_HTML
    subject = Template(subject_raw).render(Context(context))
    html = Template(html_raw).render(Context(context))
    return subject, html


# ==================== 验证码生成与发送 ====================

def _issue_verify_record(user, method, credential, base_url='', scene=SCENE_REGISTER,
                         username='', password_hash='', with_link=True, register_batch=None):
    """生成验证记录并发送验证内容（邮箱发验证邮件 / 手机号发短信验证码）

    手机号验证码由阿里云 SendSmsVerifyCode 生成，服务端以 return_verify_code=true
    接收后落库，本地比对校验，与邮箱验证流程保持一致。

    :param user: 关联用户。两步注册意向（scene=register）时为 None，完成注册建号后回填
    :param scene: 验证码场景（SCENE_REGISTER / SCENE_LOGIN）
    :param username / password_hash: 两步注册暂存值，仅 scene=register 时使用
    :param with_link: 邮箱验证邮件是否包含激活链接（登录验证码邮件不发链接，仅验证码）
    :param register_batch: 两步注册批次（同一次注册请求共享，完成注册时合并为同一账号）
    :param base_url: 站点基础地址（scheme://host，由视图层从当前请求自动获取，
                     不依赖配置，避免更换域名时手动修改），仅用于拼接邮箱激活链接

    :return: (True, None) 或 (False, err_msg)
    """
    expire_minutes = _method_expire_minutes(method)
    expire_time = timezone.now() + timedelta(minutes=expire_minutes)

    if method == METHOD_EMAIL:
        code = generate_email_code()
        token = secrets.token_hex(16)
        try:
            UserVerifyRecord.objects.create(
                user=user, scene=scene, register_batch=register_batch,
                username=username, password_hash=password_hash,
                type=method, credential=credential,
                code=code, token=token, expire_time=expire_time, is_used=False,
            )
        except Exception as e:
            return False, f'生成验证记录失败: {e}'

        # 按验证模式决定邮件内容（link/code/both）；登录验证码邮件不发链接
        mode = settings.EMAIL_VERIFY_MODE
        link = None
        if with_link and mode in ('link', 'both') and base_url:
            link = f'{base_url.rstrip("/")}/api/user_center/users/verify/email?token={token}'

        context = {
            'username': (username or (user.username if user else '') or '用户'),
            'code': code if mode in ('code', 'both') else '',
            'link': link or '',
            'expire_minutes': expire_minutes,
        }
        subject, html = _render_email_template(EMAIL_VERIFY_TEMPLATE_TYPE, context)
        # 纯文本回退内容（HTML 邮件不兼容时展示）
        text_body = f'您的验证码为 {code}，{expire_minutes} 分钟内有效。' \
                    + (f'点击链接完成验证: {link}' if link else '')
        return send_email(subject, text_body, [credential], html_body=html)

    if method == METHOD_PHONE:
        # 先落库占位（保证发送失败时无残留记录），发送成功后再用阿里云返回的验证码覆盖
        code = generate_email_code()
        try:
            record = UserVerifyRecord.objects.create(
                user=user, scene=scene, register_batch=register_batch,
                username=username, password_hash=password_hash,
                type=method, credential=credential,
                code=code, token=None, expire_time=expire_time, is_used=False,
            )
        except Exception as e:
            return False, f'生成验证记录失败: {e}'

        ok, data = aliyun_send_verify_code(
            credential,
            code_length=6,
            valid_time=expire_minutes * 60,
            return_verify_code=True,
        )
        if not ok:
            record.delete()  # 发送失败回滚记录，避免留下无效验证码
            return False, data
        aliyun_code = (data or {}).get('verify_code')
        if aliyun_code:
            UserVerifyRecord.objects.filter(pk=record.pk).update(code=aliyun_code)
        return True, None

    return False, f'不支持的验证方式: {method}'


def _cooldown_ok(method, credential, user=None) -> bool:
    """距上次发送不足冷却时间则返回 False（防刷验证码）

    按「验证方式 + 凭证」维度全局冷却（注册/登录共用同一凭证的发送频率），
    user 可空：两步注册意向无用户，登录验证码有用户。
    """
    qs = UserVerifyRecord.objects.filter(type=method, credential=credential)
    if user is not None:
        qs = qs.filter(user=user)
    last = qs.order_by('-create_time').first()
    if last and (timezone.now() - last.create_time).total_seconds() < VERIFY_RESEND_COOLDOWN:
        return False
    return True


def _has_pending_register(method, credential) -> bool:
    """是否存在未过期、未完成的注册意向（两步注册第一步已发起，尚未建号）"""
    return UserVerifyRecord.objects.filter(
        user__isnull=True, scene=SCENE_REGISTER, type=method, credential=credential,
        is_used=False, expire_time__gt=timezone.now(),
    ).exists()


# ==================== 注册 ====================

def register_user(app, username, email, phone, password, base_url=''):
    """注册

    - 提供 email / phone → 两步注册第一步：校验通过后**发送验证码并暂存注册意向（不建号）**，
      客户端随后调用 verify/email 或 verify/phone 校验验证码，**通过后才创建账号、发放账号**
    - 仅提供 username → 用户名 + 密码直接注册（无验证码场景，立即建号）
    邮箱/手机号方式启用与否由 AuthMethod 配置控制（后台开关）。
    base_url：站点基础地址（scheme://host），由视图层从当前请求自动获取，
    用于拼接邮箱验证激活链接。

    :return: (True, data) 或 (False, err_msg)
        - 两步注册：{username?, email?/phone?, need_verify: True, verify_email_sent?/verify_phone_sent?}
        - 纯用户名注册：{user_id, account, username}
    """
    username = (username or '').strip()
    raw_email = (email or '').strip().lower()
    email = _validate_email(email)
    raw_phone = (phone or '').strip()
    phone = _validate_phone(phone)
    password = (password or '').strip()

    if not username and not email and not phone:
        return False, '参数缺失: username(用户名) / email(邮箱) / phone(手机号) 至少提供一个'
    if raw_email and not email:
        # 显式提供了邮箱但格式非法：拒绝而非静默降级，避免用户误以为已绑定邮箱
        return False, '参数格式错误: email 邮箱格式不正确'
    if raw_phone and not phone:
        return False, '参数格式错误: phone 必须为 11 位手机号'
    if username and len(username) > USERNAME_MAX_LEN:
        return False, f'参数格式错误: username 长度不能超过 {USERNAME_MAX_LEN} 字符'
    if not password:
        return False, '参数缺失: password(密码)'
    if not (PASSWORD_MIN_LEN <= len(password) <= PASSWORD_MAX_LEN):
        return False, f'参数格式错误: password 长度必须在 {PASSWORD_MIN_LEN}-{PASSWORD_MAX_LEN} 字符之间'

    if email and not is_method_enabled(METHOD_EMAIL):
        return False, f'{METHOD_NAMES[METHOD_EMAIL]}注册方式未启用，请使用其他方式'
    if phone and not is_method_enabled(METHOD_PHONE):
        return False, f'{METHOD_NAMES[METHOD_PHONE]}注册方式未启用，请使用其他方式'
    if email and User.objects.filter(email=email).exists():
        return False, '该邮箱已被注册'
    if phone and User.objects.filter(phone=phone).exists():
        return False, '该手机号已被注册'
    if email and _has_pending_register(METHOD_EMAIL, email):
        return False, '该邮箱已发起注册，请先完成验证'
    if phone and _has_pending_register(METHOD_PHONE, phone):
        return False, '该手机号已发起注册，请先完成验证'

    # ── 纯用户名 + 密码：无验证码场景，直接创建账号（保持现状） ──
    if not email and not phone:
        for _ in range(3):
            account = generate_account()
            if not account:
                return False, '系统繁忙: 账号生成失败，请重试'
            try:
                user = User.objects.create(
                    account=account,
                    username=username,
                    password=make_password(password),
                    email=None,
                    email_verified=False,
                    phone=None,
                    phone_verified=False,
                    status=True,
                )
            except IntegrityError:
                # 并发下唯一冲突重试（纯用户名场景仅可能账号冲突）
                continue
            except Exception as e:
                return False, f'注册失败: {e}'
            return True, {
                'user_id': str(user.id),
                'account': user.account,
                'username': user.username,
            }
        return False, '注册失败: 账号唯一冲突，请重试'

    # ── 两步注册第一步：发送验证码，暂存注册意向（不建号，账号待校验通过后发放） ──
    password_hash = make_password(password)
    register_batch = str(uuid.uuid4())  # 同一次注册请求（可能同时绑定邮箱+手机号）共享批次
    data = {'username': username} if username else {}
    need_verify = False
    if email:
        if not _cooldown_ok(METHOD_EMAIL, email):
            return False, f'发送过于频繁，请 {VERIFY_RESEND_COOLDOWN} 秒后再试'
        sent, _ = _issue_verify_record(
            None, METHOD_EMAIL, email, base_url, scene=SCENE_REGISTER,
            username=username, password_hash=password_hash, register_batch=register_batch,
        )
        data['email'] = email
        data['verify_email_sent'] = sent
        need_verify = True
    if phone:
        if not _cooldown_ok(METHOD_PHONE, phone):
            return False, f'发送过于频繁，请 {VERIFY_RESEND_COOLDOWN} 秒后再试'
        sent, _ = _issue_verify_record(
            None, METHOD_PHONE, phone, base_url, scene=SCENE_REGISTER,
            username=username, password_hash=password_hash, register_batch=register_batch,
        )
        data['phone'] = phone
        data['verify_phone_sent'] = sent
        need_verify = True
    if need_verify:
        data['need_verify'] = True
    return True, data


# ==================== 登录 ====================

def login_user(app, account, email, phone, password, code=''):
    """登录

    - email / phone → 验证码登录（免密码）：先经 send_login_code 下发验证码，
      校验通过后签发绑定该项目的 Token（凭证未验证的存量用户同时完成验证）
    - account → 账号 + 密码登录（永远可用）

    :return: (True, {user_id, account, username, email?, phone?, token, expire_time})
             或 (False, err_msg)
    """
    account = (account or '').strip()
    email = _validate_email(email)
    phone = _validate_phone(phone)
    password = (password or '').strip()
    code = (code or '').strip()

    if not account and not email and not phone:
        return False, '参数缺失: account(账号) / email(邮箱) / phone(手机号) 至少提供一个'

    # ── 验证码登录（邮箱 / 手机号，免密码） ──
    if email or phone:
        method = METHOD_EMAIL if email else METHOD_PHONE
        credential = email or phone
        if not is_method_enabled(method):
            return False, f'{METHOD_NAMES[method]}登录方式未启用'
        if not code:
            return False, f'参数缺失: code(验证码)，请先通过登录发码接口获取'

        try:
            if method == METHOD_EMAIL:
                user = User.objects.get(email=credential)
            else:
                user = User.objects.get(phone=credential)
        except User.DoesNotExist:
            return False, f'该{METHOD_NAMES[method]}未注册，请先注册'
        except Exception as e:
            return False, f'登录失败: {e}'

        if not user.status:
            return False, '账号已被封禁'

        # 校验登录验证码（一次性原子消费，防并发重放）
        verify = UserVerifyRecord.objects.filter(
            user=user, scene=SCENE_LOGIN, type=method, credential=credential, is_used=False,
        ).order_by('-create_time').first()
        if not verify:
            return False, '验证码不存在或已使用，请先获取'
        if timezone.now() >= verify.expire_time:
            return False, '验证码已过期，请重新获取'
        if verify.code != code:
            return False, '验证码错误'
        try:
            updated = UserVerifyRecord.objects.filter(pk=verify.pk, is_used=False).update(is_used=True)
            if updated == 0:
                return False, '验证码不存在或已使用，请先获取'
            # 存量未验证凭证：校验通过即视为已验证（激活 + 登录一步完成）
            if method == METHOD_EMAIL and not user.email_verified:
                User.objects.filter(pk=user.pk).update(email_verified=True)
            elif method == METHOD_PHONE and not user.phone_verified:
                User.objects.filter(pk=user.pk).update(phone_verified=True)
        except Exception as e:
            return False, f'登录失败: {e}'

        return _issue_login_token(app, user)

    # ── 账号 + 密码登录 ──
    if not password:
        return False, '参数缺失: password(密码)'
    try:
        user = User.objects.get(account=account)
    except User.DoesNotExist:
        # 不暴露凭证是否存在，统一提示
        return False, '账号或密码错误'
    except Exception as e:
        return False, f'登录失败: {e}'

    if not user.status:
        return False, '账号已被封禁'
    # 先校验密码再校验凭证状态：错误密码时统一提示，不向攻击者泄露凭证是否已注册
    if not check_password(password, user.password):
        return False, '账号或密码错误'
    return _issue_login_token(app, user)


def _issue_login_token(app, user):
    """签发绑定指定项目的 Token，返回登录成功数据"""
    # 签发绑定项目的 Token
    token = secrets.token_hex(32)
    expire_time = timezone.now() + timedelta(days=app.token_expire_days)
    try:
        UserToken.objects.create(
            user=user,
            app=app,
            token=token,
            expire_time=expire_time,
        )
    except Exception as e:
        return False, f'登录失败: {e}'

    data = {
        'user_id': str(user.id),
        'account': user.account,
        'username': user.username,
        'token': token,
        'expire_time': expire_time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if user.email:
        data['email'] = user.email
    if user.phone:
        data['phone'] = user.phone
    return True, data


# ==================== 验证码发送与核验 ====================

def send_verify_code(app, method, credential, base_url=''):
    """重新发送两步注册的验证码（注册意向重发）

    仅针对已发起两步注册、尚未完成校验的意向（scene=register, user=None）重发，
    复用意向记录的 username/password_hash/register_batch，60 秒冷却防刷。

    base_url：站点基础地址（scheme://host），由视图层从当前请求自动获取，
    用于拼接邮箱验证激活链接。

    :return: (True, None) 或 (False, err_msg)
    """
    method = (method or '').strip().lower()
    credential = (credential or '').strip()

    if method not in METHOD_NAMES:
        return False, '参数值非法: method 仅支持 ' + '/'.join(METHOD_NAMES)
    if not credential:
        return False, f'参数缺失: {METHOD_NAMES[method]}'
    if not is_method_enabled(method):
        return False, f'{METHOD_NAMES[method]}验证方式未启用'

    if method == METHOD_EMAIL:
        email = _validate_email(credential)
        if not email:
            return False, '参数格式错误: email 邮箱格式不正确'
        credential = email
    else:  # METHOD_PHONE
        phone = _validate_phone(credential)
        if not phone:
            return False, '参数格式错误: phone 必须为 11 位手机号'
        credential = phone

    # 该凭证须存在未完成的注册意向，才允许重发
    verify = UserVerifyRecord.objects.filter(
        scene=SCENE_REGISTER, type=method, credential=credential, is_used=False,
    ).order_by('-create_time').first()
    if not verify:
        return False, '未找到注册意向，请先提交注册'
    if not _cooldown_ok(method, credential):
        return False, f'发送过于频繁，请 {VERIFY_RESEND_COOLDOWN} 秒后再试'

    ok, msg = _issue_verify_record(
        None, method, credential, base_url, scene=SCENE_REGISTER,
        username=verify.username, password_hash=verify.password_hash,
        register_batch=verify.register_batch,
    )
    if not ok:
        return False, msg
    return True, None


def _complete_register(verify):
    """两步注册第二步核心：根据已校验的注册意向记录创建账号并发放（含批次合并）

    :param verify: 已通过校验且已原子消费的注册意向记录（scene=register）
    :return: (True, {user_id, account, username, email?/phone?}) 或 (False, err_msg)
    """
    try:
        # 同批次是否已建号（先校验通过的凭证已建号，本次合并绑定，不重复建号）
        batch_user_id = None
        if verify.register_batch:
            batch_user_id = UserVerifyRecord.objects.filter(
                register_batch=verify.register_batch, user__isnull=False,
            ).values_list('user_id', flat=True).first()

        if batch_user_id:
            user = User.objects.get(pk=batch_user_id)
            update = {
                'email': verify.credential, 'email_verified': True,
            } if verify.type == METHOD_EMAIL else {
                'phone': verify.credential, 'phone_verified': True,
            }
            User.objects.filter(pk=user.pk).update(**update)
        else:
            # 创建新账号（凭证即已绑定并通过验证）
            account = generate_account()
            if not account:
                return False, '系统繁忙: 账号生成失败，请重试'
            user = User.objects.create(
                account=account,
                username=verify.username or '',
                password=verify.password_hash or make_password(secrets.token_hex(16)),
                email=verify.credential if verify.type == METHOD_EMAIL else None,
                email_verified=verify.type == METHOD_EMAIL,
                phone=verify.credential if verify.type == METHOD_PHONE else None,
                phone_verified=verify.type == METHOD_PHONE,
                status=True,
            )

        # 回填同批次其余意向记录的 user（后续校验通过时直接合并到该账号）
        if verify.register_batch:
            UserVerifyRecord.objects.filter(
                register_batch=verify.register_batch, user__isnull=True,
            ).update(user=user)
    except IntegrityError:
        return False, '注册失败: 凭证唯一冲突，请重试'
    except Exception as e:
        return False, f'注册失败: {e}'

    data = {
        'user_id': str(user.id),
        'account': user.account,
        'username': user.username,
    }
    if user.email:
        data['email'] = user.email
        data['email_verified'] = user.email_verified
    if user.phone:
        data['phone'] = user.phone
        data['phone_verified'] = user.phone_verified
    return True, data


def verify_by_code(app, method, credential, code):
    """两步注册第二步：校验注册验证码，通过后才创建账号、发放账号

    验证码与注册意向记录一一对应（scene=register, user=None），校验通过后
    创建账号并绑定凭证；同一次注册同时绑定邮箱+手机号时，后校验的凭证合并到
    先校验通过的账号（register_batch 批次合并）。

    :return: (True, {user_id, account, username, email?/phone?}) 或 (False, err_msg)
    """
    method = (method or '').strip().lower()
    credential = (credential or '').strip()
    code = (code or '').strip()

    if method not in METHOD_NAMES:
        return False, '参数值非法: method 仅支持 ' + '/'.join(METHOD_NAMES)
    if not credential:
        return False, f'参数缺失: {METHOD_NAMES[method]}'
    if not code:
        return False, '参数缺失: code(验证码)'
    if not is_method_enabled(method):
        return False, f'{METHOD_NAMES[method]}验证方式未启用'

    if method == METHOD_EMAIL:
        email = _validate_email(credential)
        if not email:
            return False, '参数格式错误: email 邮箱格式不正确'
        credential = email
    else:  # METHOD_PHONE
        phone = _validate_phone(credential)
        if not phone:
            return False, '参数格式错误: phone 必须为 11 位手机号'
        credential = phone

    # 该凭证须存在未完成的注册意向（两步注册第一步已下发验证码暂存意向；
    # 批次合并时意向可能已被回填 user，故不按 user=None 过滤）
    verify = UserVerifyRecord.objects.filter(
        scene=SCENE_REGISTER, type=method, credential=credential, is_used=False,
    ).order_by('-create_time').first()
    if not verify:
        return False, '未找到注册意向，请先提交注册并获取验证码'
    if timezone.now() >= verify.expire_time:
        return False, '验证码已过期，请重新发送'
    if verify.code != code:
        return False, '验证码错误'

    try:
        # 原子消费验证记录：并发下只有一个请求能把 is_used 置 True，其余判定为已使用
        updated = UserVerifyRecord.objects.filter(pk=verify.pk, is_used=False).update(is_used=True)
        if updated == 0:
            return False, '验证码不存在或已使用'
    except Exception as e:
        return False, f'验证失败: {e}'

    return _complete_register(verify)


def verify_by_token(token):
    """激活链接激活（仅邮箱 link/both 模式，公开接口，token 即一次性凭证）

    两步注册语义：注册意向（scene=register, user=None）的链接被点击 → 校验通过后
    创建账号、发放账号；存量已验证用户的链接（user 非空）→ 保持原逻辑置邮箱已验证。

    :return: (True, {user_id, account, username, email}) 或 (False, err_msg)
    """
    token = (token or '').strip()
    if not token:
        return False, '参数缺失: token(激活链接标识)'

    try:
        verify = UserVerifyRecord.objects.select_related('user').get(token=token)
    except UserVerifyRecord.DoesNotExist:
        return False, '激活链接无效'
    except Exception as e:
        return False, f'查询失败: {e}'

    if verify.type != METHOD_EMAIL:
        return False, '激活链接无效'
    if not verify.is_valid:
        return False, '激活链接已失效（已使用或已过期）'

    try:
        # 原子消费：并发下只有一个请求能成功激活
        updated = UserVerifyRecord.objects.filter(pk=verify.pk, is_used=False).update(is_used=True)
        if updated == 0:
            return False, '激活链接已失效（已使用或已过期）'
    except Exception as e:
        return False, f'验证失败: {e}'

    # 两步注册意向：建号并发放（含批次合并）
    if verify.user_id is None or verify.scene == SCENE_REGISTER:
        return _complete_register(verify)

    # 存量已验证用户：激活邮箱
    try:
        User.objects.filter(pk=verify.user_id).update(email_verified=True)
    except Exception as e:
        return False, f'验证失败: {e}'
    return True, {'user_id': str(verify.user_id), 'email': verify.credential}


def send_login_code(app, method, credential):
    """发送登录验证码（邮箱/手机号验证码登录第一步）

    校验凭证已注册后下发验证码（scene=login，邮件不发激活链接，仅验证码），
    校验通过后才签发 Token（见 login_user）。

    :return: (True, None) 或 (False, err_msg)
    """
    method = (method or '').strip().lower()
    credential = (credential or '').strip()

    if method not in METHOD_NAMES:
        return False, '参数值非法: method 仅支持 ' + '/'.join(METHOD_NAMES)
    if not credential:
        return False, f'参数缺失: {METHOD_NAMES[method]}'
    if not is_method_enabled(method):
        return False, f'{METHOD_NAMES[method]}登录方式未启用'

    if method == METHOD_EMAIL:
        email = _validate_email(credential)
        if not email:
            return False, '参数格式错误: email 邮箱格式不正确'
        credential = email
        lookup = {'email': email}
    else:  # METHOD_PHONE
        phone = _validate_phone(credential)
        if not phone:
            return False, '参数格式错误: phone 必须为 11 位手机号'
        credential = phone
        lookup = {'phone': phone}

    try:
        user = User.objects.get(**lookup)
    except User.DoesNotExist:
        return False, f'该{METHOD_NAMES[method]}未注册，请先注册'
    except Exception as e:
        return False, f'查询失败: {e}'

    if not user.status:
        return False, '账号已被封禁'
    if not _cooldown_ok(method, credential):
        return False, f'发送过于频繁，请 {VERIFY_RESEND_COOLDOWN} 秒后再试'

    ok, msg = _issue_verify_record(user, method, credential, scene=SCENE_LOGIN, with_link=False)
    if not ok:
        return False, msg
    return True, None


# ==================== Token 与用户信息 ====================

def logout_user(app, token):
    """用户退出：删除指定 Token（仅删除当前项目下匹配的 Token）

    :return: (True, None) 或 (False, err_msg)
    """
    token = (token or '').strip()
    if not token:
        return False, '参数缺失: token'

    try:
        deleted, _ = UserToken.objects.filter(app=app, token=token).delete()
        if deleted == 0:
            return False, 'Token 不存在或不属于当前项目'
        return True, None
    except Exception as e:
        return False, f'退出失败: {e}'


def _get_token_record(app, token):
    """查询并校验当前项目下的 Token 记录，返回 (ok, user_or_err)"""
    token = (token or '').strip()
    if not token:
        return False, '参数缺失: token'

    try:
        record = UserToken.objects.select_related('user', 'app').get(app=app, token=token)
    except UserToken.DoesNotExist:
        return False, 'Token 无效: 不存在或不属于当前项目'
    except Exception as e:
        return False, f'查询失败: {e}'

    if not record.is_valid:
        return False, 'Token 已失效: 已过期 / 用户封禁 / 项目停用'
    return True, record


def get_user_info(app, token):
    """获取用户信息（校验 Token）

    :return: (True, {user_id, account, username, email?, email_verified?, phone?, phone_verified?, expire_time})
             或 (False, err_msg)
    """
    ok, result = _get_token_record(app, token)
    if not ok:
        return False, result
    record = result
    data = {
        'user_id': str(record.user.id),
        'account': record.user.account,
        'username': record.user.username,
        'expire_time': record.expire_time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if record.user.email:
        data['email'] = record.user.email
        data['email_verified'] = record.user.email_verified
    if record.user.phone:
        data['phone'] = record.user.phone
        data['phone_verified'] = record.user.phone_verified
    return True, data


def verify_token(app, token):
    """验证 Token（供子项目调用，校验身份并返回用户信息）

    :return: (True, {valid, user_id, account, username}) 或 (False, err_msg)
    """
    ok, result = _get_token_record(app, token)
    if not ok:
        return False, result
    record = result
    # 更新最后活跃时间
    try:
        UserToken.objects.filter(id=record.id).update(last_active_time=timezone.now())
    except Exception:
        pass
    data = {
        'valid': True,
        'user_id': str(record.user.id),
        'account': record.user.account,
        'username': record.user.username,
    }
    if record.user.email:
        data['email'] = record.user.email
        data['email_verified'] = record.user.email_verified
    if record.user.phone:
        data['phone'] = record.user.phone
        data['phone_verified'] = record.user.phone_verified
    return True, data
