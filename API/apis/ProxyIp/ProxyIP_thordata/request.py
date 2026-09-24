"""ProxyIP_thordata API 请求处理视图

提供 Thordata 动态住宅代理接口:
    GET /api/ProxyIp/thordata/proxies  获取住宅代理入口地址（可选验证可用性）
"""
import re

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


# host 只允许域名 / IP 字面量（字母数字与 . - _）
_HOST_RE = re.compile(r'^[A-Za-z0-9._-]+$')
# 网关主机最大长度（域名规范上限 253）
_HOST_MAX_LEN = 253
# 端口合法范围
_PORT_MIN, _PORT_MAX = 1, 65535


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一响应

    爬虫回报的参数类问题（msg 以「参数缺失 / 参数格式错误 / 参数值非法」开头）
    按 2xxxx 返回，其余（代理不可用、平台未配置等）归为外部服务失败。
    """
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    message = result.get("message") or ""
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"), msg=message)
    code = StatusCode.from_message(message, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(code, msg=message or "获取住宅代理失败")


@require_http_methods(["GET"])
def get_thordata_proxies_view(request):
    """获取 Thordata 动态住宅代理

    Thordata 住宅代理是网关型代理：入口主机 / 端口固定，出口 IP 由 Thordata 侧
    按请求轮换，故本接口返回的是「入口地址」（含账号密码的完整代理地址）。

    参数:
        host     (选填, str): 网关主机，如 1rdjtq76.pr.thordata.net；
                              不传则用平台 .env（PROXY_THORDATA_HOST）
        port     (选填, str): 网关端口，如 9999；不传则用平台 .env（PROXY_THORDATA_PORT）
        username (选填, str): 账号，不传则用平台 .env；与 password 必须成对出现
        password (选填, str): 密码，不传则用平台 .env；与 username 必须成对出现
        verify   (选填, bool): 是否真实经代理发一次请求验证可用性，默认 false；
                               true 时额外返回 available / speed_ms / external_ip，
                               并会消耗住宅代理流量
    """
    host = request.GET.get("host", "").strip()
    port = request.GET.get("port", "").strip()
    username = request.GET.get("username", "").strip()
    password = request.GET.get("password", "").strip()
    verify_str = request.GET.get("verify", "false").strip()

    # ── host 校验（只校验调用方传入值；不传则回退平台 .env 配置）──
    if host:
        if len(host) > _HOST_MAX_LEN:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg=f"参数值非法: host 长度不能超过 {_HOST_MAX_LEN}")
        if not _HOST_RE.match(host):
            return _json_response(
                StatusCode.PARAM_FORMAT_ERROR,
                msg="参数格式错误: host 只能是域名或 IP 字面量，不含协议、端口、路径与账号")

    # ── port 校验 ──
    if port:
        if not port.isdigit():
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: port 必须为数字")
        if not _PORT_MIN <= int(port) <= _PORT_MAX:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg=f"参数值非法: port 必须在 {_PORT_MIN}-{_PORT_MAX} 之间")

    # ── 账号密码成对校验 ──
    if bool(username) != bool(password):
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: username 和 password 必须同时传入")

    # ── verify 校验 ──
    if verify_str.lower() in ("true", "1"):
        verify = True
    elif verify_str.lower() in ("false", "0"):
        verify = False
    else:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: verify 只能为 true 或 false")

    # ── 调用爬虫服务 ──
    ok, data = utils.get_thordata_proxies(
        host=host or None, port=port or None,
        username=username or None, password=password or None,
        verify=verify,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
