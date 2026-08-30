"""用户中心 - 用户 API 视图

接口清单（全部 POST + form-urlencoded，需项目签名）：
    POST /api/user_center/users/register  注册（系统分配账号）
    POST /api/user_center/users/login     登录（签发绑定项目的 Token）
    POST /api/user_center/users/logout    退出（删除 Token）
    GET  /api/user_center/users/info      用户信息（携带 Token）—— 查询类，签名参数放 query
    POST /api/user_center/users/verify    验证 Token（供子项目调用）
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


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


@require_http_methods(['POST'])
def register_view(request):
    """用户注册

    表单参数：username, password + 签名参数(app_id/timestamp/nonce/sign)
    """
    params = _parse_params(request)
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
    ok, data = utils.register_user(app, params.get('username'), params.get('password'))
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='注册成功')


@require_http_methods(['POST'])
def login_view(request):
    """用户登录

    表单参数：account, password + 签名参数(app_id/timestamp/nonce/sign)
    成功返回绑定该项目的 Token。
    """
    params = _parse_params(request)
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
    ok, data = utils.login_user(app, params.get('account'), params.get('password'))
    if not ok:
        # 参数问题返回参数码；认证失败（账号/密码错误、封禁）统一 20011，不暴露细节
        if data.startswith('参数'):
            return _fail_response(data)
        return _json_response(StatusCode.AUTH_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='登录成功')


@require_http_methods(['POST'])
def logout_view(request):
    """用户退出

    表单参数：token + 签名参数(app_id/timestamp/nonce/sign)
    删除当前项目下该 Token。
    """
    params = _parse_params(request)
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
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
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
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
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
    ok, data = utils.verify_token(app, params.get('token'))
    if not ok:
        return _fail_response(data, fallback_code=StatusCode.UNAUTHORIZED)
    return _json_response(StatusCode.SUCCESS, data=data, msg='Token 有效')
