"""用户中心 - 用户 API 视图

接口清单（业务接口 POST + form-urlencoded，需项目签名；标注「公开」的除外）：
    POST /api/user_center/users/register              注册（两步注册第一步 / 纯用户名直接建号）
    POST /api/user_center/users/login/send            发送登录验证码（邮箱/手机号验证码登录第一步）
    POST /api/user_center/users/login                 登录（邮箱/手机号验证码登录 / 账号+密码）
    POST /api/user_center/users/logout                退出（删除 Token）
    GET  /api/user_center/users/info                  用户信息（携带 Token）—— 查询类，签名参数放 query
    POST /api/user_center/users/verify                验证 Token（供子项目调用）
    GET  /api/user_center/users/verify/email          邮箱激活链接（邮件内链接，公开访问）
    POST /api/user_center/users/verify/email          邮箱验证码完成两步注册（需项目签名）
    POST /api/user_center/users/verify/email/resend   重新发送两步注册邮箱验证邮件
    POST /api/user_center/users/verify/phone          手机号验证码完成两步注册（需项目签名）
    POST /api/user_center/users/verify/phone/send     发送两步注册手机号短信验证码（需项目签名）
    GET  /api/user_center/users/methods               当前可用的注册/登录方式（公开，免签名）

说明：
- 两步注册：register 提交凭证+密码后仅暂存注册意向并下发验证码（不建号），
  客户端再调用 verify/email 或 verify/phone 校验验证码，通过后才创建账号、发放账号
- 邮箱/手机号等验证方式是否可用由后台 AuthMethod 配置控制（见 utils.get_available_methods），
  客户端先调用 methods 接口获取可用方式，再渲染注册/登录入口
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.common.security_guard import login_clear, login_fail, login_locked
from . import utils


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _client_ip(request):
    """获取客户端 IP（优先反向代理透传头，兜底 REMOTE_ADDR）"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    real_ip = request.META.get('HTTP_X_REAL_IP', '')
    if real_ip:
        return real_ip.strip()
    return request.META.get('REMOTE_ADDR', '')


def _parse_params(request):
    """合并 form body 与 query 参数（签名参数可能在 body 或 query）"""
    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})
    return params


def _fail_response(msg, fallback_code=StatusCode.PARAM_VALUE_INVALID):
    """根据业务错误消息映射状态码：参数缺失→20001，格式错误→20002，其余→fallback"""
    if msg.startswith('参数缺失'):
        return _json_response(StatusCode.PARAM_MISSING, msg=msg)
    if msg.startswith('参数格式错误'):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=msg)
    return _json_response(fallback_code, msg=msg)


def _require_app(request):
    """校验项目签名上下文，返回 (app, None) 或 (None, response)"""
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return None, _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
    return app, None


def _base_url(request):
    """从当前请求自动获取站点基础地址（scheme://host）

    用于拼接邮箱验证激活链接。不依赖任何配置，部署域名变化时无需手动修改。
    """
    return f"{request.scheme}://{request.get_host()}"


@require_http_methods(['POST'])
def register_view(request):
    """用户注册

    表单参数：username(选填), email(选填), phone(选填), password + 签名参数(app_id/timestamp/nonce/sign)
    - 提供 email / phone → 两步注册第一步：校验通过后仅**发送验证码并暂存注册意向（不建号）**，
      客户端随后调用 verify/email 或 verify/phone 校验验证码，**通过后才创建账号、发放账号**
    - 仅提供 username → 用户名 + 密码直接注册（立即建号）
    邮箱/手机号方式是否可用由后台 AuthMethod 配置控制。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.register_user(
        app,
        params.get('username'),
        params.get('email'),
        params.get('phone'),
        params.get('password'),
        _base_url(request),
    )
    if not ok:
        return _fail_response(data)

    # 区分验证内容是否发送成功，便于前端引导用户
    if data.get('need_verify'):
        failed = []
        if 'verify_email_sent' in data and not data['verify_email_sent']:
            failed.append('验证邮件')
        if 'verify_phone_sent' in data and not data['verify_phone_sent']:
            failed.append('短信验证码')
        if failed:
            msg = f'验证信息已提交，但{"、".join(failed)}发送失败，请稍后使用重发接口'
        else:
            msg = '验证信息已发送，请完成验证后发放账号'
        return _json_response(StatusCode.SUCCESS, data=data, msg=msg)
    return _json_response(StatusCode.SUCCESS, data=data, msg='注册成功')


@require_http_methods(['POST'])
def send_login_code_view(request):
    """发送登录验证码（邮箱/手机号验证码登录第一步）

    表单参数：email 或 phone + 签名参数(app_id/timestamp/nonce/sign)
    校验凭证已注册后下发验证码，随后调用 login 接口携带 code 完成登录。
    60 秒冷却防刷。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    method = utils.METHOD_EMAIL if params.get('email') else utils.METHOD_PHONE
    credential = params.get('email') or params.get('phone')
    if not credential:
        return _fail_response('参数缺失: email(邮箱) / phone(手机号) 至少提供一个')
    ok, data = utils.send_login_code(app, method, credential)
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=None, msg='验证码已发送')


@require_http_methods(['POST'])
def login_view(request):
    """用户登录

    表单参数：
    - 邮箱/手机号登录：email 或 phone, code(验证码) + 签名参数(app_id/timestamp/nonce/sign)，
      验证码免密码，校验通过后才签发 Token（需先调用 login/send 获取验证码）
    - 账号登录：account, password + 签名参数(app_id/timestamp/nonce/sign)
    成功返回绑定该项目的 Token。

    防爆破（S-03 整改）：同一「项目+凭证+IP」连续失败 5 次锁定 15 分钟，
    锁定期间返回 20040(RATE_LIMITED)；登录成功后清零失败计数。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp

    principal = (params.get('account') or params.get('email')
                 or params.get('phone') or '').strip()
    guard_key = f'login:{app.app_id}:{principal}:{_client_ip(request)}'

    # 已处于锁定：直接返回限流码，不执行登录逻辑
    locked, minutes_left = login_locked(guard_key)
    if locked:
        return _json_response(
            StatusCode.RATE_LIMITED,
            msg=f'登录失败次数过多，已临时锁定，请约 {minutes_left} 分钟后再试',
        )

    ok, data = utils.login_user(
        app,
        params.get('account'),
        params.get('email'),
        params.get('phone'),
        params.get('password'),
        params.get('code', ''),
    )
    if not ok:
        # 参数问题返回参数码；认证失败（账号/密码错误、封禁、验证码错误等）统一 20011，不暴露细节
        if data.startswith('参数'):
            return _fail_response(data)
        # 认证失败计数：达上限即锁定并返回 20040（不暴露具体是哪种失败）
        locked_now, minutes_left = login_fail(guard_key)
        if locked_now:
            return _json_response(
                StatusCode.RATE_LIMITED,
                msg=f'登录失败次数过多，已临时锁定，请约 {minutes_left} 分钟后再试',
            )
        return _json_response(StatusCode.AUTH_FAILED, msg=data)

    login_clear(guard_key)
    return _json_response(StatusCode.SUCCESS, data=data, msg='登录成功')


@require_http_methods(['POST'])
def logout_view(request):
    """用户退出

    表单参数：token + 签名参数(app_id/timestamp/nonce/sign)
    删除当前项目下该 Token。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, err = utils.logout_user(app, params.get('token'))
    if not ok:
        return _fail_response(err)
    return _json_response(StatusCode.SUCCESS, data=None, msg='退出成功')


@require_http_methods(['GET'])
def info_view(request):
    """获取用户信息

    query 参数：token + 签名参数(app_id/timestamp/nonce/sign)
    需携带有效 Token。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.get_user_info(app, params.get('token'))
    if not ok:
        return _fail_response(data, fallback_code=StatusCode.UNAUTHORIZED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')


@require_http_methods(['POST'])
def verify_view(request):
    """验证 Token（供子项目确认用户身份）

    表单参数：token + 签名参数(app_id/timestamp/nonce/sign)
    成功返回 {valid, user_id, account, username}。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.verify_token(app, params.get('token'))
    if not ok:
        return _fail_response(data, fallback_code=StatusCode.UNAUTHORIZED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='Token 有效')


@require_http_methods(['GET'])
def methods_view(request):
    """获取当前可用的注册/登录方式（公开接口，免签名）

    返回 data: {methods: ['email', 'phone'], username: true}
        methods  - 后台启用的验证方式列表（空列表 = 仅用户名+密码）
        username - 用户名+密码是否可用（永远为 true，作为兜底登录方式）
    """
    return _json_response(StatusCode.SUCCESS, data=utils.get_available_methods(), msg='查询成功')


@require_http_methods(['GET', 'POST'])
def verify_email_view(request):
    """邮箱验证（两步注册第二步）接口

    - GET  ?token=xxx：激活链接（邮件内链接，浏览器直接点击，公开访问无需签名，
      已由 ApiAuthMiddleware 对该路径的 GET 请求免签名），校验通过后创建账号、发放账号
    - POST email, code：验证码校验（需项目签名），通过后创建账号、发放账号
    """
    if request.method == 'GET':
        ok, data = utils.verify_by_token(request.GET.get('token'))
        if not ok:
            return _fail_response(data)
        return _json_response(StatusCode.SUCCESS, data=data, msg='邮箱验证成功')
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.verify_by_code(app, utils.METHOD_EMAIL, params.get('email'), params.get('code'))
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='注册成功')


@require_http_methods(['POST'])
def resend_verify_email_view(request):
    """重新发送两步注册的邮箱验证邮件

    表单参数：email + 签名参数(app_id/timestamp/nonce/sign)
    仅对「已提交注册意向但未完成验证」的邮箱生效，60 秒冷却防刷。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.send_verify_code(app, utils.METHOD_EMAIL, params.get('email'), _base_url(request))
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=None, msg='验证邮件已发送')


@require_http_methods(['POST'])
def verify_phone_view(request):
    """手机号验证（两步注册第二步）

    表单参数：phone, code + 签名参数(app_id/timestamp/nonce/sign)
    校验通过后创建账号、发放账号。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.verify_by_code(app, utils.METHOD_PHONE, params.get('phone'), params.get('code'))
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='注册成功')


@require_http_methods(['POST'])
def send_phone_code_view(request):
    """发送两步注册的手机号短信验证码

    表单参数：phone + 签名参数(app_id/timestamp/nonce/sign)
    仅对「已提交注册意向但未完成验证」的手机号生效，60 秒冷却防刷（防短信轰炸）。
    """
    params = _parse_params(request)
    app, resp = _require_app(request)
    if app is None:
        return resp
    ok, data = utils.send_verify_code(app, utils.METHOD_PHONE, params.get('phone'), _base_url(request))
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=None, msg='短信验证码已发送')
