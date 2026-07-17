"""ProxyIP API 请求处理视图

提供代理IP服务接口:
    GET /api/ProxyIp/66daili/proxies  获取可用代理IP列表
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
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result.get("message", "获取代理失败"))


@require_http_methods(["GET"])
def get_proxies_view(request):
    """获取可用的代理IP列表

    参数:
        count   (选填, int): 需要返回的代理数量，默认 10，必须为正整数
        sources (选填, str): 代理源名称，多个用逗号分隔，默认 "66daili"
        verify  (选填, bool): 是否验证代理可用性，默认 true，
                  true=验证可用（按速度排序返回最快的）、false=不验证直接返回原始数据
    """
    # ── 参数解析 ──
    count_str = request.GET.get("count", "10").strip()
    sources_str = request.GET.get("sources", "66daili").strip()
    verify_str = request.GET.get("verify", "true").strip()

    # ── 参数验证 ──

    # count: 必须为正整数
    try:
        count = int(count_str)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: count 必须为整数")

    if count < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: count 必须大于 0")

    # sources: 逗号分隔，转为列表
    sources = [s.strip() for s in sources_str.split(",") if s.strip()]
    if not sources:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: sources 不能为空")

    # verify: true/false 字符串转 bool
    if verify_str.lower() in ("true", "1"):
        verify = True
    elif verify_str.lower() in ("false", "0"):
        verify = False
    else:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: verify 只能为 true 或 false")

    # ── 调用爬虫服务 ──
    ok, data = utils.get_available_proxies(count=count, sources=sources, verify=verify)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
