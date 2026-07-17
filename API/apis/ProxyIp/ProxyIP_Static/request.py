"""ProxyIP_Static API 请求处理视图

提供静态代理IP的管理接口:
    GET    /api/ProxyIp/static/proxies       获取全部静态代理
    POST   /api/ProxyIp/static/proxies       新增静态代理
    DELETE /api/ProxyIp/static/proxies       删除静态代理
    POST   /api/ProxyIp/static/proxies/reload  重新从 JSON 文件加载
"""
import json

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
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result.get("message", "操作失败"))


# ── 统一入口：GET/POST/DELETE /api/ProxyIp/static/proxies ──

@require_http_methods(["GET", "POST", "DELETE"])
def proxies_view(request):
    """静态代理管理入口（按 HTTP 方法分发）

    GET:    获取全部静态代理列表
    POST:   新增静态代理
    DELETE: 删除静态代理（按 ip:port 匹配）
    """
    if request.method == "GET":
        return _get_proxies(request)
    elif request.method == "POST":
        return _add_proxy(request)
    elif request.method == "DELETE":
        return _delete_proxy(request)


def _get_proxies(request):
    """获取全部静态代理列表

    参数:
        json_path (选填, str): 自定义 JSON 文件路径（绝对路径），默认使用配置文件路径
    """
    json_path = request.GET.get("json_path", "").strip() or None

    ok, data = utils.get_proxies(json_path=json_path)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)


def _add_proxy(request):
    """新增静态代理

    参数:
        ip       (必填, str): IP 地址
        port     (必填, str): 端口
        username (选填, str): 用户名
        password (选填, str): 密码
        json_path (选填, str): 自定义 JSON 文件路径（绝对路径）
    """
    # 支持 JSON body 和 form-data
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="请求体 JSON 解析失败")
        ip = (body.get("ip") or "").strip()
        port = (body.get("port") or "").strip()
        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()
        json_path = (body.get("json_path") or "").strip() or None
    else:
        ip = request.POST.get("ip", "").strip()
        port = request.POST.get("port", "").strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        json_path = request.POST.get("json_path", "").strip() or None

    if not ip:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: ip(IP地址)")
    if not port:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: port(端口)")

    ok, data = utils.add_proxy(ip=ip, port=port, username=username, password=password, json_path=json_path)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)


def _delete_proxy(request):
    """删除静态代理（按 ip:port 匹配）

    参数:
        ip       (必填, str): IP 地址
        port     (必填, str): 端口
        json_path (选填, str): 自定义 JSON 文件路径（绝对路径）
    """
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="请求体 JSON 解析失败")
        ip = (body.get("ip") or "").strip()
        port = (body.get("port") or "").strip()
        json_path = (body.get("json_path") or "").strip() or None
    else:
        ip = request.GET.get("ip", "").strip()
        port = request.GET.get("port", "").strip()
        json_path = request.GET.get("json_path", "").strip() or None

    if not ip:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: ip(IP地址)")
    if not port:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: port(端口)")

    ok, data = utils.delete_proxy(ip=ip, port=port, json_path=json_path)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)


# ── 重载：POST /api/ProxyIp/static/proxies/reload ──


@require_http_methods(["POST"])
def reload_proxies_view(request):
    """重新从 JSON 文件加载代理列表

    参数:
        json_path (选填, str): 自定义 JSON 文件路径（绝对路径），默认使用配置文件路径
    """
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="请求体 JSON 解析失败")
        json_path = (body.get("json_path") or "").strip() or None
    else:
        json_path = request.POST.get("json_path", "").strip() or None

    ok, data = utils.reload_proxies(json_path=json_path)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
