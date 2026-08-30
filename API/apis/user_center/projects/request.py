"""用户中心 - 接入项目 API 视图

接口清单：
    GET /api/user_center/projects/info   查询项目自身信息（需签名）
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


@require_http_methods(['GET'])
def project_info_view(request):
    """查询项目自身信息

    query 参数：签名参数(app_id/timestamp/nonce/sign)
    返回该项目的配置（含 Token 默认有效期等），供项目方核对。
    """
    # 项目签名已由 ApiAuthMiddleware 统一校验；若后台将该接口配置为开放则无 auth_app，业务强依赖项目上下文故仍拒绝
    app = getattr(request, 'auth_app', None)
    if app is None:
        return _json_response(StatusCode.AUTH_FAILED, msg='接口未配置项目认证，无法识别接入项目')
    ok, data = utils.get_project_info(app)
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')
