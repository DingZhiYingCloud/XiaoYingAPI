"""555电影 线路 API 请求处理视图

提供 6 个接口（均为 GET，查询类）:
    GET /api/movies/movie_555/categories  分类列表
    GET /api/movies/movie_555/home        首页聚合
    GET /api/movies/movie_555/list        分类列表（分页 / 排序 / 年份）
    GET /api/movies/movie_555/detail      影片详情
    GET /api/movies/movie_555/play        播放地址（m3u8）
    GET /api/movies/movie_555/search      搜索

签名参数（app_id/timestamp/nonce/sign）由 ApiAuthMiddleware 统一校验，视图不重复处理。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体
    :param code: 状态码(参见 StatusCode)
    :param data: 业务数据,默认为 None
    :param msg:  自定义消息,未传则使用状态码对应的默认描述
    """
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _require_int(value, name, minimum=None):
    """校验并转换整数参数。

    :return: (True, int) 或 (False, (状态码, 提示))
    """
    if not value:
        return False, (StatusCode.PARAM_MISSING, f'参数缺失: {name}')
    try:
        num = int(value)
    except (TypeError, ValueError):
        return False, (StatusCode.PARAM_FORMAT_ERROR, f'参数格式错误: {name} 必须为整数')
    if minimum is not None and num < minimum:
        return False, (StatusCode.PARAM_VALUE_INVALID, f'参数值非法: {name} 必须 >= {minimum}')
    return True, num


def _fail(fail):
    """把 _require_int 的失败元组转为响应"""
    code, msg = fail
    return _json_response(code, msg=msg)


@require_http_methods(['GET'])
def categories_view(request):
    """获取分类列表（主分类 + 榜单 + 专题）"""
    ok, data = utils.get_categories()
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def home_view(request):
    """获取首页聚合（轮播 + 各推荐区块）"""
    ok, data = utils.get_home()
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def list_view(request):
    """
    获取分类列表。

    查询参数:
        type_id (必填): 分类 ID，1=电影 2=连续剧 3=综艺纪录 4=动漫（或榜单 ID）
        page    (可选): 页码，从 1 开始，默认 1
        order   (可选): 排序方式 time(时间) / hits(人气) / score(评分)
        year    (可选): 年份筛选，如 2026（与 order 同时传时以 year 为准）
    """
    ok, type_id = _require_int(request.GET.get('type_id', '').strip(), 'type_id')
    if not ok:
        return _fail(type_id)

    page_raw = request.GET.get('page', '').strip()
    if page_raw:
        ok, page = _require_int(page_raw, 'page', minimum=1)
        if not ok:
            return _fail(page)
    else:
        page = 1

    order = request.GET.get('order', '').strip() or None
    if order and order not in ('time', 'hits', 'score'):
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: order 仅支持 time / hits / score')

    year_raw = request.GET.get('year', '').strip()
    if year_raw:
        ok, year = _require_int(year_raw, 'year')
        if not ok:
            return _fail(year)
    else:
        year = None

    ok, data = utils.get_list(type_id, page=page, order=order, year=year)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def detail_view(request):
    """
    获取影片详情（含播放源与选集）。

    查询参数:
        vod_id (必填): 影片 ID（纯数字）
    """
    ok, vod_id = _require_int(request.GET.get('vod_id', '').strip(), 'vod_id')
    if not ok:
        return _fail(vod_id)

    ok, data = utils.get_detail(vod_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    # 源站对不存在的影片仍返回 200 的空壳页，这里显式判空，避免「空壳成功」
    if not data.get('name') and not data.get('sources'):
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=f'影片不存在: vod_id={vod_id}')
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def play_view(request):
    """
    获取某集/某播放源的 m3u8 播放地址。

    查询参数:
        vod_id (必填): 影片 ID
        sid    (必填): 播放源序号（取自详情接口 sources[].sid）
        nid    (必填): 集数序号（取自选集 episodes[].nid）
    """
    ok, vod_id = _require_int(request.GET.get('vod_id', '').strip(), 'vod_id')
    if not ok:
        return _fail(vod_id)
    ok, sid = _require_int(request.GET.get('sid', '').strip(), 'sid')
    if not ok:
        return _fail(sid)
    ok, nid = _require_int(request.GET.get('nid', '').strip(), 'nid')
    if not ok:
        return _fail(nid)

    ok, data = utils.get_play(vod_id, sid, nid)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    # 源站对越界的播放源/集数仍返回 200 的空壳页，无 m3u8 一律视为无效
    if not data.get('m3u8'):
        return _json_response(StatusCode.EXTERNAL_API_FAILED,
                              msg='播放地址不存在: 请检查 vod_id / sid / nid 是否正确')
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def search_view(request):
    """
    搜索影片。

    查询参数:
        keyword (必填): 搜索关键词
    """
    keyword = request.GET.get('keyword', '').strip()
    if not keyword:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: keyword(搜索关键词)')

    ok, data = utils.search(keyword)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
