"""红果短剧网页版 线路 API 请求处理视图

对外接口:
    GET  /api/dramas/hongguo/rank                 榜单（热播榜 / 真人剧榜 / AI剧榜）
    GET  /api/dramas/hongguo/categories           分类列表
    GET  /api/dramas/hongguo/list                 分类列表（分页）
    GET  /api/dramas/hongguo/search               关键词搜索
    GET  /api/dramas/hongguo/detail               剧集详情
    GET  /api/dramas/hongguo/play                 播放地址（前若干集为源站直链；
                                                  第 4 集及以后返回外链或本站直出地址；
                                                  直出画质由 q 指定，见 utils.QUALITY_WIDTHS）
    GET  /api/dramas/hongguo/stream               网页直出流（明文 H.264，支持 Range；
                                                  画质写在 play 下发的令牌里）

关于第 4 集及以后：源站只对每部剧前 3 集下发明文直链，其余集是 DRM 加密的 H.265，
浏览器在多数机器上完全解不了 HEVC（原生 / MSE / WebCodecs 三条路实测全断），
所以「网页能播」只有两条路：
    ① 人工：预处理解密导出 → 上传外部平台 → 超管控制台登记链接（play 返回 source=external）
    ② 自动：本站按需解密 + 转 H.264 后直出（play 返回 source=stream，走本文件 stream_view）
`play` 按 ①→② 顺序择优。

签名参数（app_id/timestamp/nonce/sign）由 ApiAuthMiddleware 统一校验，视图不重复处理。
`stream` 是给 <video> 标签用的，带不了项目签名，故改用 play 下发的**时效令牌**鉴权。
"""
import os
import re

from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils

# 出流分块大小（256KB：Range 拖动时首包够快，又不至于切太碎）
_CHUNK = 256 * 1024
_RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')


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
def rank_view(request):
    """
    获取榜单（热播榜 / 真人剧榜 / AI剧榜）。

    查询参数:
        type (可选): 榜单类型，默认 hot-drama（取值见 utils.RANK_TYPE_VALUES）
        page (可选): 页码，从 1 开始，默认 1
    """
    rank_type = request.GET.get('type', '').strip() or 'hot-drama'
    if rank_type not in utils.RANK_TYPE_VALUES:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: type 仅支持 ' + ' / '.join(utils.RANK_TYPE_VALUES))

    page_raw = request.GET.get('page', '').strip()
    if page_raw:
        ok, page = _require_int(page_raw, 'page', minimum=1)
        if not ok:
            return _fail(page)
    else:
        page = 1

    ok, data = utils.get_rank(rank_type, page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def categories_view(request):
    """获取分类列表（slug -> 中文名）"""
    ok, data = utils.get_categories()
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def list_view(request):
    """
    获取分类列表（分页）。

    查询参数:
        category (必填): 分类 slug（取值见「分类列表」接口）
        page     (可选): 页码，从 1 开始，默认 1
    """
    category = request.GET.get('category', '').strip()
    if not category:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: category(分类)')
    if category not in utils.CATEGORY_VALUES:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: category 仅支持 ' + ' / '.join(utils.CATEGORY_VALUES))

    page_raw = request.GET.get('page', '').strip()
    if page_raw:
        ok, page = _require_int(page_raw, 'page', minimum=1)
        if not ok:
            return _fail(page)
    else:
        page = 1

    ok, data = utils.get_list(category, page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def search_view(request):
    """
    搜索剧集（站点不支持分页，仅返回单页）。

    查询参数:
        keyword (必填): 搜索关键词
        page    (可选): 页码，从 1 开始，默认 1
    """
    keyword = request.GET.get('keyword', '').strip()
    if not keyword:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: keyword(搜索关键词)')

    page_raw = request.GET.get('page', '').strip()
    if page_raw:
        ok, page = _require_int(page_raw, 'page', minimum=1)
        if not ok:
            return _fail(page)
    else:
        page = 1

    ok, data = utils.get_search(keyword, page=page)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def detail_view(request):
    """
    获取剧集详情（全量集号 + 可播集数）。

    查询参数:
        series_id (必填): 剧集 ID（纯数字）
    """
    ok, series_id = _require_int(request.GET.get('series_id', '').strip(), 'series_id')
    if not ok:
        return _fail(series_id)

    ok, data = utils.get_detail(series_id)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    # 爬虫对不存在的剧集返回 None
    if data is None:
        return _json_response(StatusCode.EXTERNAL_API_FAILED,
                              msg=f'剧集不存在: series_id={series_id}')
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def play_view(request):
    """
    获取某集播放地址。

    前若干集（H5 可播范围）返回源站明文直链；第 4 集及以后返回已登记的外部播放地址，
    没登记则回落到本站「网页直出」，画质由 q 指定（见 utils.QUALITY_WIDTHS）。

    查询参数:
        series_id (必填): 剧集 ID（纯数字）
        ep        (必填): 集数，从 1 开始
        q         (选填): 出流画质（= 输出宽度上限，竖屏即 1080/720/540/480/360），
                          缺省用 settings.HONGGUO_STREAM_QUALITY（默认 1080）
    """
    ok, series_id = _require_int(request.GET.get('series_id', '').strip(), 'series_id')
    if not ok:
        return _fail(series_id)
    ok, ep = _require_int(request.GET.get('ep', '').strip(), 'ep', minimum=1)
    if not ok:
        return _fail(ep)
    ok, quality = utils.parse_quality(request.GET.get('q', ''))
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=quality)

    status, payload = utils.get_play(series_id, ep, quality)
    if status == utils.PLAY_OK:
        # 本站直出地址补成绝对地址（<video> 可能来自其它域名的前端）
        if isinstance(payload, dict) and payload.get('source') == 'stream':
            payload['url'] = request.build_absolute_uri(payload['url'])
        return _json_response(StatusCode.SUCCESS, data=payload)
    if status == utils.PLAY_OUT_OF_RANGE:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: ep 越界，该剧不存在第 {ep} 集')
    if status == utils.PLAY_NOT_LISTED:
        return _json_response(StatusCode.SERVICE_UNAVAILABLE, msg=payload)
    return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=payload)


def _iter_file(handle, remaining):
    """按块读取文件并保证关闭句柄"""
    try:
        while remaining > 0:
            data = handle.read(min(_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        handle.close()


def _unparsable_range(size):
    """区间不合法：按 RFC 7233 返回 416 并告知当前长度"""
    resp = HttpResponse(status=416, content_type='video/mp4')
    resp['Content-Range'] = f'bytes */{size}'
    return resp


def _range_response(request, path):
    """按 HTTP Range 出流（浏览器拖动进度条依赖 206；Django 的 FileResponse 不支持）"""
    size = os.path.getsize(path)
    head_only = request.method == 'HEAD'
    match = _RANGE_RE.match((request.META.get('HTTP_RANGE') or '').strip())

    if match is None:                                   # 无 Range：整文件
        start, end = 0, size - 1
    else:
        start_raw, end_raw = match.group(1), match.group(2)
        if start_raw == '':                             # 后缀区间 bytes=-N
            if end_raw == '':
                return _unparsable_range(size)
            start, end = max(size - int(end_raw), 0), size - 1
        else:
            start = int(start_raw)
            end = min(int(end_raw), size - 1) if end_raw else size - 1
        if start >= size or start > end:
            return _unparsable_range(size)

    length = end - start + 1
    if head_only:
        resp = HttpResponse(status=200 if match is None else 206,
                            content_type='video/mp4')
    elif match is None:
        handle = open(path, 'rb')
        resp = FileResponse(handle, content_type='video/mp4')
    else:
        handle = open(path, 'rb')
        handle.seek(start)
        resp = StreamingHttpResponse(_iter_file(handle, length),
                                     status=206, content_type='video/mp4')
    if match is not None:
        resp['Content-Range'] = f'bytes {start}-{end}/{size}'
    resp['Content-Length'] = str(length)
    resp['Accept-Ranges'] = 'bytes'
    resp['Cache-Control'] = 'private, max-age=600'
    return resp


@require_http_methods(['GET', 'HEAD'])
def stream_view(request):
    """网页直出：按需转码 + 明文 H.264 出流（支持 Range，可拖动进度条）

    鉴权用 `play` 下发的时效令牌（<video> 标签带不了项目签名）。
    画质（输出宽度上限）写在令牌里，跟着令牌走，不用再传参。
    该集该画质首次被点播时返回 202（服务端在后台解密 + 转码，约数十秒），
    前端轮询本地址，返回 200 即可交给 <video> 播放。
    """
    payload, error = utils.parse_stream_token((request.GET.get('token') or '').strip())
    if payload is None:
        return JsonResponse({'code': StatusCode.FORBIDDEN, 'msg': error, 'data': None},
                            status=403)

    from SpiderServices.dramas.hongguo import transcode
    series_id, ep, width = payload['series_id'], payload['ep'], payload['w']
    if not transcode.is_ready(series_id, ep, width):
        state = transcode.job_status(series_id, ep, width)
        if state.get('state') != 'failed':
            transcode.ensure(series_id, ep, width)   # 首次点播触发后台转码
            state = transcode.job_status(series_id, ep, width)
        if state.get('state') == 'failed':
            return JsonResponse({'code': StatusCode.SERVICE_UNAVAILABLE,
                                 'msg': f"该集播放地址生成失败: {state.get('error')}",
                                 'data': state})
        resp = JsonResponse({'code': StatusCode.SUCCESS,
                             'msg': '正在生成播放地址，请稍候重试',
                             'data': state}, status=202)
        resp['Retry-After'] = '3'
        return resp
    return _range_response(request, transcode.stream_path(series_id, ep, width))
