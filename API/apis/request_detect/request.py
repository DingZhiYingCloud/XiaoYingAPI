"""请求身份识别 API 请求处理视图

提供 1 个接口:
    POST /api/request_detect/detect  识别请求为爬虫/真人/直接访问

调用方式（特征上报模式）:
    其他项目收到用户请求后，把该请求的请求头信息上报到本接口，
    本接口返回多标签布尔 + 置信度 + 命中原因 + 来源分析。

    参数（全部可选，未传视为「没有」）:
        headers     原请求头 JSON 字符串（推荐，自动提取 UA/Referer/Sec-Fetch-* 等）
        user_agent  User-Agent 字符串（与 headers 二选一，headers 优先）
        referer     Referer 字符串（与 headers 二选一，headers 优先）
        ip          客户端 IP（仅记录输出，不参与判定）
        site        调用方域名（可选），用于判断 referer 是否为同站导航
"""
import ipaddress
import json
import re

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils

# 域名格式校验（简单域名，含端口时取 host 部分）
_SITE_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9-]*(\.[a-zA-Z0-9-]+)+$')


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code, msg, data}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _validate_ip(value):
    """校验 IP 格式（IPv4/IPv6），非法返回 False"""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _validate_site(value):
    """校验域名格式（去除协议与端口后校验 host）"""
    host = value.strip().lower()
    if '://' in host:
        host = host.split('://', 1)[1]
    host = host.split('/', 1)[0].split(':', 1)[0]
    return bool(_SITE_PATTERN.match(host))


@require_http_methods(['POST'])
def detect_view(request):
    """识别请求身份

    表单参数（application/x-www-form-urlencoded），全部可选:
        headers     (选填) 原请求头 JSON 字符串，如 {"User-Agent": "...", "Referer": "..."}
        user_agent  (选填) User-Agent
        referer     (选填) Referer
        ip          (选填) 客户端 IP，仅记录
        site        (选填) 调用方域名，用于同站导航判断
    """
    # ── 1. 参数获取与校验 ──
    headers_raw = request.POST.get('headers', '').strip()
    user_agent = request.POST.get('user_agent', '').strip()
    referer = request.POST.get('referer', '').strip()
    ip = request.POST.get('ip', '').strip()
    site = request.POST.get('site', '').strip()

    headers = None
    if headers_raw:
        try:
            headers = json.loads(headers_raw)
        except json.JSONDecodeError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: headers 不是合法的 JSON')
        if not isinstance(headers, dict):
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: headers 必须为 JSON 对象')

    if ip and not _validate_ip(ip):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: ip 不是合法的 IP 地址')
    if site and not _validate_site(site):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: site 不是合法的域名')

    # ── 2. 调用判定逻辑 ──
    data = utils.detect(
        headers=headers,
        user_agent=user_agent or None,
        referer=referer or None,
        ip=ip or None,
        site=site or None,
    )

    return _json_response(StatusCode.SUCCESS, data=data, msg='识别成功')
