"""ProxyIP_91http API 请求处理视图

提供 91HTTP 动态代理IP接口:
    GET /api/ProxyIp/91http/proxies  获取动态代理IP
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
def get_91http_proxies_view(request):
    """获取 91HTTP 动态代理IP

    从 91HTTP API (api.91http.com) 获取国内动态代理IP。
    支持自定义订单号、密钥、协议类型等参数。

    参数:
        num        (选填, int): 返回 IP 数量，默认 10，必须 >= 1
        trade_no   (选填, str): 订单号，默认使用配置文件中的 DEFAULT_TRADE_NO
        secret     (选填, str): 密钥，默认使用配置文件中的 DEFAULT_SECRET
        protocol   (选填, int): 协议类型，1=HTTP 2=HTTPS 3=SOCKS5 4=HTTP(S)，默认 1
        auto_white (选填, int): 自动添加白名单，1=是 0=否，默认 1
        time       (选填, int): 返回过期时间，1=是 0=否，默认 1
    """
    # ── 参数解析 ──
    num_str = request.GET.get("num", "10").strip()
    trade_no = request.GET.get("trade_no", "").strip() or None
    secret = request.GET.get("secret", "").strip() or None
    protocol_str = request.GET.get("protocol", "").strip() or None
    auto_white_str = request.GET.get("auto_white", "").strip() or None
    time_str = request.GET.get("time", "").strip() or None

    # ── num 验证 ──
    try:
        num = int(num_str)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: num 必须为整数")
    if num < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: num 必须大于 0")

    # ── protocol 验证 ──
    protocol = None
    if protocol_str is not None:
        try:
            protocol = int(protocol_str)
            if protocol not in (1, 2, 3, 4):
                return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                       msg="参数值非法: protocol 可选值 1=HTTP 2=HTTPS 3=SOCKS5 4=HTTP(S)")
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: protocol 必须为整数")

    # ── auto_white 验证 ──
    auto_white = None
    if auto_white_str is not None:
        try:
            auto_white = int(auto_white_str)
            if auto_white not in (0, 1):
                return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: auto_white 仅支持 0 或 1")
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: auto_white 必须为整数")

    # ── time 验证 ──
    time = None
    if time_str is not None:
        try:
            time = int(time_str)
            if time not in (0, 1):
                return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: time 仅支持 0 或 1")
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: time 必须为整数")

    # ── 调用爬虫服务 ──
    ok, data = utils.get_91http_proxies(
        num=num, trade_no=trade_no, secret=secret,
        protocol=protocol, auto_white=auto_white, time=time,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
