"""必应搜索 & 网页抓取 API 请求处理视图

提供 2 个接口:
    GET  /api/bing/search  必应中文搜索
    POST /api/bing/crawl   网页内容抓取
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


@require_http_methods(["GET"])
def search_view(request):
    """
    必应中文搜索

    参数 (query string):
        q       (必填): 搜索关键词
        count   (选填): 返回结果数量(1-50)，默认 10
        offset  (选填): 结果偏移量，用于翻页，默认 0
    """
    query = request.GET.get("q", "").strip()
    if not query:
        return _json_response(StatusCode.PARAM_MISSING, msg="参数缺失: q(搜索关键词)")

    # count
    try:
        count_raw = request.GET.get("count", "10").strip()
        count = int(count_raw)
        if count < 1 or count > 50:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg="参数值非法: count 必须在 1-50 之间",
            )
    except ValueError:
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg="参数格式错误: count 必须为整数",
        )

    # offset
    try:
        offset_raw = request.GET.get("offset", "0").strip()
        offset = int(offset_raw)
        if offset < 0:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg="参数值非法: offset 不能为负数",
            )
    except ValueError:
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg="参数格式错误: offset 必须为整数",
        )

    ok, data = utils.search_bing(query, count=count, offset=offset)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)

    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(["POST"])
def crawl_view(request):
    """
    抓取网页内容

    表单参数(application/x-www-form-urlencoded):
        url      (选填): 单个网页 URL
        urls     (选填): URL 列表的 JSON 数组字符串，支持批量抓取
                         格式: ["https://example.com/a", "https://example.com/b"]
    url 和 urls 至少提供一个。都提供时 urls 优先级更高。
    """
    single_url = request.POST.get("url", "").strip()
    urls_json = request.POST.get("urls", "").strip()

    if urls_json:
        # 批量模式
        try:
            url_list = json.loads(urls_json)
        except json.JSONDecodeError:
            return _json_response(
                StatusCode.PARAM_FORMAT_ERROR,
                msg="参数格式错误: urls 不是合法的 JSON 数组",
            )
        if not isinstance(url_list, list) or not url_list:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg="参数值非法: urls 必须为非空 JSON 数组",
            )
        results = utils.crawl_webpages_batch(url_list)
        return _json_response(StatusCode.SUCCESS, data=results)
    elif single_url:
        ok, data = utils.crawl_webpage(single_url)
        if not ok:
            return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
        return _json_response(StatusCode.SUCCESS, data={"url": single_url, "content": data})
    else:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg="参数缺失: url 或 urls 至少提供一个",
        )
