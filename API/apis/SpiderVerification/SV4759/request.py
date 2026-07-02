"""4759蜘蛛IP验证 API 请求处理视图

提供 1 个只读查询接口:
    GET /verify  验证 IP 是否为搜索引擎爬虫
"""
import ipaddress

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _is_valid_ip(value):
    """校验 IP 地址格式是否合法（支持 IPv4 和 IPv6）"""
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


@require_http_methods(['GET'])
def verify_view(request):
    """验证 IP 是否为搜索引擎爬虫

    GET 参数:
        ip (必填): 待验证的 IP 地址
    """
    # ---------- 1. 参数获取 ----------
    ip = request.GET.get('ip', '').strip()

    # ---------- 2. 参数校验 ----------
    if not ip:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: ip(待验证的IP地址)')

    if not _is_valid_ip(ip):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=f'参数格式错误: "{ip}" 不是合法的 IP 地址')

    # ---------- 3. 调用爬虫 ----------
    success, data = utils.verify_ip(ip)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _json_response(StatusCode.SUCCESS, data=data)
