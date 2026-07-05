"""Bing IndexNow URL 提交 API 请求处理视图

提供 2 个接口:
    GET  /generate-key  生成 IndexNow API Key
    POST /submit        提交 URL 到 IndexNow
"""
import json

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


@require_http_methods(['GET'])
def generate_key_view(request):
    """生成 IndexNow API Key

    生成一个 32 位 UUID 格式的 API Key，用于验证域名所有权。
    """
    key = utils.generate_key()
    return _json_response(StatusCode.SUCCESS, data={"key": key})


@require_http_methods(['POST'])
def submit_view(request):
    """提交 URL 到 IndexNow

    表单参数(application/x-www-form-urlencoded):
        host        (必填): 域名, 如 "www.example.com"
        key         (必填): API Key（由 generate-key 接口生成）
        keyLocation (选填): Key 文件完整 URL, 默认自动拼接为 https://{host}/{key}.txt
        url         (选填): 单个 URL 提交
        urlList     (选填): URL 列表（JSON 数组字符串）, 优先级高于 url
                             格式: ["https://example.com/page1", "https://example.com/page2"]

    注意: url 和 urlList 至少提供一个，否则返回参数缺失错误。
    """
    # ---------- 1. 参数获取 ----------
    host = request.POST.get('host', '').strip()
    key = request.POST.get('key', '').strip()
    key_location = request.POST.get('keyLocation', '').strip() or None
    single_url = request.POST.get('url', '').strip()
    url_list_raw = request.POST.get('urlList', '').strip()

    # ---------- 2. 参数校验 ----------
    if not host:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: host(域名)')

    if not key:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: key(API Key)')

    # 解析 urlList
    url_list = None
    if url_list_raw:
        try:
            url_list = json.loads(url_list_raw)
        except json.JSONDecodeError:
            return _json_response(
                StatusCode.PARAM_FORMAT_ERROR,
                msg='参数格式错误: urlList 不是合法的 JSON 数组',
            )
        if not isinstance(url_list, list) or not url_list:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg='参数值非法: urlList 必须为非空 JSON 数组',
            )

    # urlList 优先级高于单条 url
    if url_list:
        final_url_list = url_list
    elif single_url:
        final_url_list = [single_url]
    else:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg='参数缺失: url 或 urlList 至少提供一个',
        )

    # ---------- 3. URL 格式校验 ----------
    invalid_urls = [u for u in final_url_list if not u.startswith(('http://', 'https://'))]
    if invalid_urls:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: URL 必须以 http:// 或 https:// 开头, 请检查: {invalid_urls}',
        )

    # ---------- 4. 调用 IndexNow ----------
    success, data = utils.submit_urls(host, key, final_url_list, key_location)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _json_response(StatusCode.SUCCESS, data=data)
