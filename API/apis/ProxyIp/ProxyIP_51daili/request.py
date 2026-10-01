"""ProxyIP_51daili API 请求处理视图

提供 51代理 动态代理IP接口:
    GET /api/ProxyIp/51daili/proxies  获取动态代理IP
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils
from .utils import PARAM_NAMES


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一响应

    参数类问题（msg 以「参数缺失 / 参数格式错误 / 参数值非法」开头）按 2xxxx 返回，
    其余（凭据未配置、上游报错、网络失败等）归为外部服务失败。
    """
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    message = result.get("message") or ""
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"), msg=message)
    code = StatusCode.from_message(message, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(code, msg=message or "获取动态代理失败")


@require_http_methods(["GET"])
def get_51daili_proxies_view(request):
    """获取 51代理 动态代理IP

    API 文档: https://m.51daili.com/wap/api/apinote.html
    参数名与官方提取链接一致，可直接照抄控制台生成的链接里的参数。
    账号凭据（uid / accessName / accessPassword）与套餐标识（packid / rid）
    默认由平台 .env 提供，调用方也可整套传自己的（使用自己购买的套餐）。

    参数:
        uid             (选填, str): 账号 ID；不传则用平台 .env（PROXY_51DAILI_UID）
        accessName      (选填, str): 账号名；不传则用平台 .env（PROXY_51DAILI_ACCESS_NAME）
        accessPassword  (选填, str): 账号密码；不传则用平台 .env（PROXY_51DAILI_ACCESS_PASSWORD）
        packid          (选填, str): 套餐 ID；不传则用平台 .env（PROXY_51DAILI_PACKID）
        rid             (选填, str): 提取链接上的标识；不传则用平台 .env（PROXY_51DAILI_RID）
        qty             (选填, int): 提取数量，默认 1，最大 100
        port            (选填, str): 代理协议 1=HTTP/HTTPS（默认）2=Socks5
        time            (选填, str): 稳定使用时长，默认 31
        format          (选填, str): 返回格式 json（默认）/ txt
        field           (选填, str): 返回字段，逗号分隔，
                                     默认 ipport,expiretime,regioncode,isptype
        linePoolIndex   (选填, str): 线路池索引，默认 -1（不限）
    """
    # 只收集调用方显式传入的参数，其余交给服务层取默认值
    params = {}
    for name in PARAM_NAMES:
        value = request.GET.get(name, "").strip()
        if value:
            params[name] = value

    ok, data = utils.get_51daili_proxies(params)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
