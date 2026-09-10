"""官网前台视图：页面渲染 + 用户中心服务端代理（会话化）

设计说明：
- 官网作为用户中心的一个「接入项目」；前端页面不直接携带签名调用 /api/ 用户中心接口
  （APPSECRET 严禁进前端），而是由本模块在服务端调用用户中心业务逻辑完成
  注册 / 登录 / 发码 / 退出，登录态存 Django 会话（Session）。
- 页面路由：/ 、/login/ 、/register/ ；其余均为页面 JS 调用的 JSON 动作接口。
- 登录/注册响应沿用项目统一格式 {"code", "msg", "data"}。
"""
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from API.apis.user_center.users import utils as uc_utils
from API.common import StatusCode
from API.common.security_guard import login_clear, login_fail, login_locked
from API.models import UserApp

from . import captcha
from .service_status import annotate as _annotate_service_status
from .services import SERVICES, localize

logger = logging.getLogger(__name__)

# 会话中保存官网登录态的 key
_SESSION_USER_KEY = 'website_user'


def guide_view(request):
    """接入向导页（互动式多步骤引导）"""
    return render(request, 'guide.html', {})


# ==================== 多语言切换 ====================

def set_language(request):
    """切换界面语言：?lang=<语言码>[&next=<站内地址>]

    - lang 必须是 settings.LANGUAGES 中声明的语言码，非法值直接回首页（不写 Cookie）；
    - 切换后写入语言 Cookie，后续请求由 LocaleMiddleware 按 Cookie 激活该语言；
    - 回跳目标优先取 next，其次 Referer，仅允许站内地址，并剥离其中的 lang 参数，
      避免 URL 上残留的旧 lang 与刚写入的 Cookie 不一致。
    """
    code = (request.GET.get('lang') or '').strip()
    if code not in dict(settings.LANGUAGES):
        return redirect('/')
    response = redirect(_lang_target(request))
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME, code,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path='/', samesite='Lax', secure=settings.SESSION_COOKIE_SECURE,
    )
    return response


def _lang_target(request):
    """语言切换后的回跳地址（站内相对路径，已剥离 lang 参数）"""
    raw = (request.GET.get('next') or '').strip()
    if not raw:
        ref = urlsplit(request.META.get('HTTP_REFERER', ''))
        # Referer 为跨站地址时不回跳，避免开放重定向
        if ref.path and (not ref.netloc or ref.netloc == request.get_host()):
            raw = ref.path + (f'?{ref.query}' if ref.query else '')
    if not raw.startswith('/') or raw.startswith('//'):
        return '/'
    parts = urlsplit(raw)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != 'lang'])
    return parts.path + (f'?{query}' if query else '')


# ==================== 工具 ====================

def _json(code, msg='', data=None):
    return JsonResponse({'code': code, 'msg': msg, 'data': data})


def _client_ip(request):
    """客户端 IP（优先反向代理透传头，兜底 REMOTE_ADDR），用于登录防爆破计数"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('HTTP_X_REAL_IP', '') or request.META.get('REMOTE_ADDR', '')


def _base_url(request):
    """站点基础地址（scheme://host），用于拼接邮箱验证激活链接"""
    return request.build_absolute_uri('/').rstrip('/')


def _web_app():
    """官网对应的接入项目 UserApp（按 settings.WEB_APP_NAME 惰性创建一次）

    用户中心 Token 需绑定一个项目，官网自身即注册为「接入项目」。
    首次使用若后台未创建该项目则自动创建（复用项目模型自动生成 APPID/APPSECRET 逻辑）。
    注：项目 APPSECRET 以 SECRET_KEY 派生密钥加密落库（credential_crypto），
    更换 SECRET_KEY 后旧密文无法解密（MAC check failed）。官网接入项目为本模块
    自动管理的内部项目（密钥仅服务端内部使用，不对外发放），故读取失败时删除重建即可自愈。
    """
    name = settings.WEB_APP_NAME
    try:
        app = UserApp.objects.filter(name=name).first()
        if app is not None:
            return app
    except Exception as exc:
        logger.warning('读取官网接入项目失败（可能 SECRET_KEY 已更换），准备重建: %s', exc)
        UserApp.objects.filter(name=name).delete()
    try:
        app = UserApp.objects.create(name=name)
    except IntegrityError:
        # 并发创建兜底：别人已建好则直接复用
        app = UserApp.objects.get(name=name)
    logger.info('官网接入项目已自动创建: name=%s app_id=%s', app.name, app.app_id)
    return app


def _error_code(msg):
    """根据业务错误消息映射状态码（与用户中心接口语义一致，前端主要读 msg）"""
    if msg.startswith('参数缺失'):
        return StatusCode.PARAM_MISSING
    if msg.startswith('参数格式错误'):
        return StatusCode.PARAM_FORMAT_ERROR
    if msg.startswith('参数值非法'):
        return StatusCode.PARAM_VALUE_INVALID
    return StatusCode.PARAM_VALUE_INVALID


def _establish_session(request, data):
    """登录成功后将用户态写入会话"""
    request.session[_SESSION_USER_KEY] = {
        'user_id': data.get('user_id'),
        'account': data.get('account'),
        'username': data.get('username'),
        'token': data.get('token'),
        'expire_time': data.get('expire_time'),
        'email': data.get('email'),
        'phone': data.get('phone'),
    }
    request.session.modified = True


def _current_user(request):
    """读取会话中的登录态（未登录返回 None）"""
    return request.session.get(_SESSION_USER_KEY)


def _auth_page_context():
    """渲染登录/注册页所需的可用认证方式（由后台 AuthMethod 开关动态决定）"""
    methods = uc_utils.get_available_methods().get('methods', [])
    return {
        'email_enabled': 'email' in methods,
        'phone_enabled': 'phone' in methods,
        'username_enabled': True,  # 用户名+密码兜底方式，永远可用
        # 图形验证是否启用（密钥齐备即启用）；前端据此决定是否弹验证，与后端校验口径一致
        'captcha_enabled': captcha.enabled(),
    }


# ==================== 页面 ====================

def index(request):
    """官网首页（服务能力卡片带对外状态徽标，状态见 service_status）"""
    from .docs import all_docs as _all_docs
    prefixes = {d.prefix for d in _all_docs()}
    return render(request, 'index.html',
                  {'services': _annotate_service_status(localize(SERVICES), lambda p: p in prefixes)})


def _safe_web_next(request, fallback='/'):
    """读取登录成功后的回跳地址（仅允许站内相对路径）"""
    nxt = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback


def login_view(request):
    """统一登录页 / 登录动作

    GET：渲染登录页（已是超管会话或已登录则回跳）。
    POST：JSON 提交，返回 {"code","msg","data"}。account 分支先判断“管理员”：
        - 输入的是后台超管账号（python manage.py createsuperuser 创建）
          → 走 Django 超管会话登录，成功后前端自动出现「超级管理员」入口；
        - 否则再走用户中心“账号+密码”普通登录。
        email/phone 分支为用户中心验证码登录，与管理员无关。
    """
    next_url = _safe_web_next(request)

    if request.method == 'GET':
        is_admin = bool(request.user.is_authenticated and request.user.is_superuser)
        # 防死循环：只有超管才允许按 next 回跳。
        # next 通常来自超管页（superadmin_required 跳转过来），普通用户的 next 多半也是超管页，
        # 回跳会被再次打回登录页 → 无限重定向；故普通用户一律回首页。
        if is_admin:
            return redirect(next_url if request.GET.get('next') else '/')
        if _current_user(request):
            return redirect('/')
        ctx = _auth_page_context()
        ctx['next'] = next_url
        return render(request, 'account/login.html', ctx)

    login_type = (request.POST.get('login_type') or '').strip()
    if login_type not in ('account', 'email', 'phone'):
        return _json(StatusCode.PARAM_VALUE_INVALID, '参数值非法: login_type')

    # 图形验证（服务端二次校验，防密码暴力破解；密钥未配置时自动跳过）
    ok, err = captcha.verify(request)
    if not ok:
        return _json(err[0], err[1])

    app = _web_app()
    account = (request.POST.get('account') or '').strip()
    email = (request.POST.get('email') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    password = (request.POST.get('password') or '').strip()
    code = (request.POST.get('code') or '').strip()

    # ---------- 账号 + 密码：先判断是否“管理员”（Django 超管） ----------
    if login_type == 'account':
        admin = authenticate(request, username=account, password=password)
        if admin is not None:
            if admin.is_superuser and admin.is_active:
                django_login(request, admin)
                logger.info('超管账号登录成功: %s', admin.username)
                return _json(StatusCode.SUCCESS, '登录成功', {'redirect': next_url})
            # 是 Django 账号但不是超管：不静默降级，明确提示
            return _json(StatusCode.FORBIDDEN, '该账号不是超级管理员，无管理权限')

        # 非管理员账号 → 尝试用户中心“账号+密码”
        guard_key = f'weblogin:{app.app_id}:{account}:{_client_ip(request)}'
        locked, minutes_left = login_locked(guard_key)
        if locked:
            return _json(StatusCode.RATE_LIMITED,
                         f'登录失败次数过多，已临时锁定，请约 {minutes_left} 分钟后再试')
        ok, result = uc_utils.login_user(
            app, account=account, email=None, phone=None, password=password)
        if not ok:
            login_fail(guard_key)
            return _json(_error_code(result) if result.startswith('参数') else StatusCode.AUTH_FAILED,
                         result)
        login_clear(guard_key)
        _establish_session(request, result)
        return _json(StatusCode.SUCCESS, '登录成功', {'redirect': '/'})

    # ---------- 邮箱 / 手机号验证码登录（用户中心，免密码） ----------
    credential = email or phone
    guard_key = f'weblogin:{app.app_id}:{credential}:{_client_ip(request)}'
    locked, minutes_left = login_locked(guard_key)
    if locked:
        return _json(StatusCode.RATE_LIMITED,
                     f'登录失败次数过多，已临时锁定，请约 {minutes_left} 分钟后再试')

    ok, result = uc_utils.login_user(
        app, account=None, email=email or None, phone=phone or None,
        password='', code=code)
    if not ok:
        login_fail(guard_key)
        return _json(_error_code(result) if result.startswith('参数') else StatusCode.AUTH_FAILED,
                     result)
    login_clear(guard_key)
    _establish_session(request, result)
    return _json(StatusCode.SUCCESS, '登录成功', {'redirect': '/'})


def register_view(request):
    """注册页 / 注册动作

    GET：渲染注册页（已登录则回首页）。
    POST：两步注册第一步 / 纯用户名直接建号。
        - 提供 email/phone → 校验后发验证码并暂存注册意向（不建号），返回 step=verify
        - 仅提供 username → 直接建号，返回 step=done（含 user_id/account/username）
    """
    if request.method == 'GET':
        if _current_user(request):
            return redirect('/')
        return render(request, 'account/register.html', _auth_page_context())

    # 图形验证（服务端二次校验，防批量注册与验证码轰炸；密钥未配置时自动跳过）
    ok, err = captcha.verify(request)
    if not ok:
        return _json(err[0], err[1])

    app = _web_app()
    ok, result = uc_utils.register_user(
        app,
        username=(request.POST.get('username') or '').strip(),
        email=(request.POST.get('email') or '').strip(),
        phone=(request.POST.get('phone') or '').strip(),
        password=(request.POST.get('password') or '').strip(),
        base_url=_base_url(request),
    )
    if not ok:
        return _json(_error_code(result), result)

    if result.get('need_verify'):
        # 待验证码校验（两步注册第二步由 register_verify 完成）
        return _json(StatusCode.SUCCESS, '验证信息已发送，请完成验证后发放账号',
                     {'step': 'verify', **result})
    # 纯用户名注册：直接建号完成
    return _json(StatusCode.SUCCESS, '注册成功', {'step': 'done', **result})


@require_POST
def register_verify_view(request):
    """两步注册第二步：校验验证码，通过后才创建账号、发放账号

    POST 表单：method(email|phone)、credential、code
    """
    method = (request.POST.get('method') or '').strip().lower()
    credential = (request.POST.get('credential') or '').strip()
    code = (request.POST.get('code') or '').strip()

    ok, result = uc_utils.verify_by_code(_web_app(), method, credential, code)
    if not ok:
        return _json(_error_code(result), result)
    return _json(StatusCode.SUCCESS, '注册成功', {'step': 'done', **result})


@require_POST
def register_resend_view(request):
    """重发两步注册验证码（邮箱验证邮件 / 手机短信验证码）

    POST 表单：method(email|phone)、credential
    """
    method = (request.POST.get('method') or '').strip().lower()
    credential = (request.POST.get('credential') or '').strip()

    # 图形验证（服务端二次校验，防短信/邮件轰炸；密钥未配置时自动跳过）
    ok, err = captcha.verify(request)
    if not ok:
        return _json(err[0], err[1])

    ok, err = uc_utils.send_verify_code(_web_app(), method, credential, _base_url(request))
    if not ok:
        return _json(_error_code(err), err)
    msg = '验证邮件已发送' if method == 'email' else '短信验证码已发送'
    return _json(StatusCode.SUCCESS, msg)


@require_POST
def login_send_code_view(request):
    """发送登录验证码（邮箱/手机号验证码登录第一步）

    POST 表单：method(email|phone)、credential
    """
    method = (request.POST.get('method') or '').strip().lower()
    credential = (request.POST.get('credential') or '').strip()

    # 图形验证（服务端二次校验，防短信/邮件轰炸；密钥未配置时自动跳过）
    ok, err = captcha.verify(request)
    if not ok:
        return _json(err[0], err[1])

    ok, err = uc_utils.send_login_code(_web_app(), method, credential)
    if not ok:
        return _json(_error_code(err), err)
    msg = '邮件验证码已发送' if method == 'email' else '短信验证码已发送'
    return _json(StatusCode.SUCCESS, msg)


@require_POST
def logout_view(request):
    """退出登录：注销用户中心 Token 并清空本地会话，回到首页"""
    user = _current_user(request)
    if user and user.get('token'):
        try:
            uc_utils.logout_user(_web_app(), user['token'])
        except Exception as exc:  # 退出为尽力而为，失败不阻塞本地退出
            logger.warning('官网退出注销 Token 失败: %s', exc)
    request.session.flush()
    return redirect('/')


# ==================== 重置密码（忘记密码） ====================

def reset_password_view(request):
    """忘记密码页 / 发送重置验证码

    GET ：渲染重置密码页（已登录则回首页）
    POST：发送重置验证码（邮箱/手机号），需先通过图形验证（与登录/注册发码口径一致）
    """
    if request.method == 'GET':
        if _current_user(request):
            return redirect('/')
        return render(request, 'account/reset_password.html', _auth_page_context())

    # 图形验证（服务端二次校验，防短信/邮件轰炸；密钥未配置时自动跳过）
    ok, err = captcha.verify(request)
    if not ok:
        return _json(err[0], err[1])

    method = (request.POST.get('method') or '').strip().lower()
    credential = (request.POST.get('email') or request.POST.get('phone') or '').strip()
    ok, err = uc_utils.send_reset_code(_web_app(), method, credential, _base_url(request))
    if not ok:
        return _json(_error_code(err), err)
    msg = _('邮件验证码已发送') if method == 'email' else _('短信验证码已发送')
    return _json(StatusCode.SUCCESS, msg)


@require_POST
def reset_password_submit_view(request):
    """提交重置密码：校验验证码通过后设置新密码

    POST 表单：method(email|phone)、email 或 phone、code、password
    重置成功会作废该用户全部已签发 Token（所有已登录设备需重新登录）。
    """
    method = (request.POST.get('method') or '').strip().lower()
    credential = (request.POST.get('email') or request.POST.get('phone') or '').strip()

    ok, result = uc_utils.reset_password(
        _web_app(), method, credential,
        (request.POST.get('code') or '').strip(),
        (request.POST.get('password') or '').strip(),
    )
    if not ok:
        return _json(_error_code(result), result)
    return _json(StatusCode.SUCCESS, _('密码已重置，请用新密码登录'), {'account': result.get('account')})
