"""ProxyIP_qy API 请求处理视图

提供青雨动态代理IP接口:
    GET /api/ProxyIp/qy/proxies  获取动态代理IP（存活 1-3 分钟）
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一响应"""
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"), msg=result.get("message"))
    else:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result.get("message", "获取动态代理失败"))


@require_http_methods(["GET"])
def get_qy_proxies_view(request):
    """获取青雨动态代理IP

    从青雨代理 API (qydailiip.com) 获取国内动态短期代理IP，存活约 1-3 分钟。
    每次调用会返回全新的 IP，如需多个请调大 num。

    参数:
        num    (选填, int): 返回 IP 数量，默认 1，必须 >= 1
        order  (选填, str): 订单号，默认使用配置文件中的 DEFAULT_ORDER
        apikey (选填, str): 账户 token，默认使用配置文件中的 DEFAULT_APIKEY
    """
    # ── 参数解析 ──
    num_str = request.GET.get("num", "1").strip()
    order = request.GET.get("order", "").strip() or None
    apikey = request.GET.get("apikey", "").strip() or None

    # ── num 验证 ──
    try:
        num = int(num_str)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: num 必须为整数")

    if num < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: num 必须大于 0")

    # ── 调用爬虫服务 ──
    ok, data = utils.get_qy_proxies(num=num, order=order, apikey=apikey)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
