"""ProxyIP_juliang API 请求处理视图

提供巨量代理IP接口:
    GET /api/ProxyIp/juliang/proxies  获取动态代理IP（独享代理产品）
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils
from .utils import MAX_NUM, PASSTHROUGH_ENUM, PASSTHROUGH_TEXT


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        "code": code,
        "msg": msg or StatusCode.get_message(code),
        "data": data,
    })


def _spider_result(result):
    """将爬虫的 {code, message, data} 映射为项目统一响应

    爬虫回报的参数类问题（msg 以「参数缺失 / 参数格式错误 / 参数值非法」开头）
    按 2xxxx 返回，其余（签名校验失败、平台未配置等）归为外部服务失败。
    """
    if not isinstance(result, dict):
        return _json_response(StatusCode.UNKNOWN_ERROR, msg=str(result))
    message = result.get("message") or ""
    if result.get("code") == 0:
        return _json_response(StatusCode.SUCCESS, data=result.get("data"), msg=message)
    code = StatusCode.from_message(message, fallback=StatusCode.EXTERNAL_API_FAILED)
    return _json_response(code, msg=message or "获取动态代理失败")


@require_http_methods(["GET"])
def get_juliang_proxies_view(request):
    """获取巨量代理动态IP

    API 文档: https://www.juliangip.com/help/api/sign/
    业务编号 / API Key / 代理账密默认由平台 .env 提供，调用方也可传自己的。
    官方签名与参数集严格绑定，故提供两种模式（二选一）:
        - key 模式：传 key（业务密钥），服务端代算 sign，可自由传 num/area/isp 等参数；
        - custom_sign 模式：传自己算好的 sign，参数原样透传，服务端不补任何默认值。

    注意：本接口对外的签名参数名为 custom_sign，而非官方文档里的 sign——
    平台自身的鉴权参数就叫 sign（app_id/timestamp/nonce/sign），同名会在网关层被占用，
    服务端会把 custom_sign 原样传给巨量官方接口的 sign 字段。

    参数:
        trade_no    (选填, str): 业务编号；不传则用平台 .env（PROXY_JULIANG_TRADE_NO）
        key         (选填, str): 业务密钥；不传则用平台 .env（PROXY_JULIANG_KEY）
        custom_sign (选填, str): 自算签名；与 key 二选一
        num         (选填, int): 提取数量，默认 1，最大 100
        username    (选填, str): 代理认证账号；不传则用平台 .env；与 password 成对
        password    (选填, str): 代理认证密码；不传则用平台 .env；与 username 成对
        pt / split / auto_white / city_name / city_code / ip_remain / auth_info / filter
                    (选填, int): 官方透传参数，取值见官方文档
        area        (选填, str): 按地区筛选，多个用英文逗号分隔，如「北京,上海」
        isp         (选填, str): 按运营商筛选（电信 / 联通 / 移动）
    """
    trade_no = request.GET.get("trade_no", "").strip()
    key = request.GET.get("key", "").strip()
    sign = request.GET.get("custom_sign", "").strip()
    username = request.GET.get("username", "").strip()
    password = request.GET.get("password", "").strip()
    num_str = request.GET.get("num", "").strip()

    # ── 凭据：key 与 custom_sign 二选一（两个都给会产生签名歧义）──
    if key and sign:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg="参数值非法: key 与 custom_sign 只能二选一"
                "（key=服务端代算签名，custom_sign=参数原样透传）")

    # ── 代理账密成对 ──
    if bool(username) != bool(password):
        return _json_response(StatusCode.PARAM_MISSING,
                              msg="参数缺失: username 和 password 必须同时传入")

    # ── num 校验 ──
    num = None
    if num_str:
        try:
            num = int(num_str)
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg="参数格式错误: num 必须为整数")
        if num < 1:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg="参数值非法: num 必须大于 0")
        if num > MAX_NUM:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg=f"参数值非法: num 最大为 {MAX_NUM}")

    # ── 透传业务参数校验（只收集调用方显式传入的）──
    extras = {}
    for name, allowed in PASSTHROUGH_ENUM.items():
        value = request.GET.get(name, "").strip()
        if not value:
            continue
        if value not in allowed:
            return _json_response(StatusCode.PARAM_VALUE_INVALID,
                                  msg=f"参数值非法: {name} 仅支持 {'/'.join(allowed)}")
        extras[name] = value
    for name in PASSTHROUGH_TEXT:
        value = request.GET.get(name, "").strip()
        if value:
            extras[name] = value

    # ── 调用爬虫服务 ──
    ok, data = utils.get_juliang_proxies(
        trade_no=trade_no or None, key=key or None, sign=sign or None, num=num,
        extras=extras, username=username or None, password=password or None,
    )
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _spider_result(data)
