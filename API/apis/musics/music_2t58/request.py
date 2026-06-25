"""爱听音乐网(2t58.com) API 请求处理视图

提供 4 个只读接口,对应爬虫的 4 个对外方法:
    GET /api/music/2t58/home      首页数据(热门歌手/榜单)
    GET /api/music/2t58/singer    歌手详情(基本信息+歌曲列表+分页)
    GET /api/music/2t58/song      歌曲详情(基本信息+播放链接+歌词+每日推荐)
    GET /api/music/2t58/search    搜索音乐(歌曲列表+分页+总条数)
"""
from urllib.parse import urlparse

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


def _is_valid_2t58_url(url):
    """校验 URL 是否属于 2t58.com 域名(防止误用与SSRF)。

    :param url: 待校验的完整 URL
    :return: bool
    """
    try:
        parsed = urlparse(url)
        # 网站仅支持 https/http,netloc 形如 "www.2t58.com" 或 "2t58.com"
        host = parsed.netloc.lower()
        return parsed.scheme in ('http', 'https') and (
            host == 'www.2t58.com' or host == '2t58.com'
        )
    except (ValueError, AttributeError):
        return False


@require_http_methods(['GET'])
def home_view(request):
    """
    首页数据接口
    返回热门歌手、歌曲飙升榜、流行趋势榜三个模块。
    """
    success, data = utils.fetch_home_data()
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def singer_view(request):
    """
    歌手详情接口
    Query 参数:
        url (必填): 歌手歌曲列表页完整 URL
                   示例: https://www.2t58.com/singer/bm1z/1.html
    """
    url = request.GET.get('url', '').strip()
    if not url:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: url(歌手页URL)')
    if not _is_valid_2t58_url(url):
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg='参数值非法: url 必须为 2t58.com 域名下的歌手页地址',
        )

    success, data = utils.fetch_singer_detail(url)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def song_view(request):
    """
    歌曲详情接口
    Query 参数:
        url (必填): 歌曲详情页完整 URL
                   示例: https://www.2t58.com/song/d3dkc2t3.html
    """
    url = request.GET.get('url', '').strip()
    if not url:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: url(歌曲页URL)')
    if not _is_valid_2t58_url(url):
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg='参数值非法: url 必须为 2t58.com 域名下的歌曲页地址',
        )

    success, data = utils.fetch_song_detail(url)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def search_view(request):
    """
    搜索音乐接口
    Query 参数:
        keyword (必填): 搜索关键词,如 "王小草"
        page    (选填): 页码,正整数,默认 1
    """
    keyword = request.GET.get('keyword', '').strip()
    if not keyword:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: keyword(搜索关键词)')

    # 页码参数校验:选填,默认1,必须为正整数
    page_str = request.GET.get('page', '1').strip()
    try:
        page = int(page_str)
        if page < 1:
            raise ValueError
    except ValueError:
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: page 必须为正整数',
        )

    success, data = utils.search_music(keyword, page=page)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
