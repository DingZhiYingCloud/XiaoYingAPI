"""微博 API 请求处理视图

提供 4 个接口（前三个 **GET 与 POST 都接受**，POST 时参数走表单体，便于传较长的 Cookie）:
    /api/weibo/channels  频道分类（「我的频道」+「频道推荐」）
    /api/weibo/feed      按频道取内容（图片 / 视频直链 / 转发原微博 / 长文展开）
    /api/weibo/check     校验微博登录凭据是否有效
    /api/weibo/video     视频代理播放（GET / HEAD；免项目签名，用时效令牌自证）

凭据说明：前三个接口都接受可选参数 `cookie`（调用方自带的微博登录 Cookie）——
**传了就用它，只本次生效、不落库**；没传则回落到平台统一托管的账号
（后台「账号管理」`/console/accounts/` 维护，加密落库）。
文档页 `/docs/weibo/` 右侧栏「本机凭据」可粘贴并保存到本机，调试时自动带上。
"""
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from SpiderServices.weibo.utils import DEFAULT_CHANNEL, DEFAULT_LIMIT, MAX_LIMIT

from . import utils


def _json_response(code, data=None, msg=None):
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _param(request, name):
    """取请求参数：POST 表单体优先，其次 GET query（同一请求只会落在其中一处）"""
    if request.method == 'POST':
        value = request.POST.get(name)
        if value not in (None, ''):
            return value
    return request.GET.get(name)


def _error_response(msg):
    """业务层的中文失败说明 → 统一响应码

    区分三类，避免把「平台自己没配账号」误报成「上游调用失败」：
        · 未配置账号 / 未提供 Cookie → 50002 服务不可用（平台侧问题，接入方重试无意义）
        · 找不到该频道               → 20003 参数值非法（调用方传错了 channel）
        · 其它（凭据过期 / 上游异常） → 40001 外部服务调用失败
    """
    if '尚未配置' in msg or '未提供 Cookie' in msg:
        return _json_response(StatusCode.SERVICE_UNAVAILABLE, msg=msg)
    if '未找到该频道' in msg:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=msg)
    return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=msg)


def _optional_int(raw, name, default, minimum, maximum):
    """可选整数参数校验

    :return: (值, 错误响应)；错误响应非 None 表示参数非法
    """
    if raw is None or str(raw).strip() == '':
        return default, None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None, _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                    msg=f'参数格式错误: {name} 必须为整数')
    if value < minimum or value > maximum:
        return None, _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: {name} 必须在 {minimum}~{maximum} 之间')
    return value, None


def _fill_stream_urls(request, feed):
    """给带视频的条目补上本站「代理播放」地址

    微博视频直链有 **Referer 防盗链**（第三方页面的 `<video>` 一律 403）且是 http，
    所以另外给一个本站代理地址 —— `<video>` 可直接播、长期有效
    （令牌里只放微博 id，播放时按 id 现场解析新鲜直链）。
    """
    base = request.build_absolute_uri(utils.VIDEO_STREAM_PATH)
    for item in feed.get('list') or []:
        for node in (item, item.get('retweeted')):
            if not isinstance(node, dict) or not node.get('video'):
                continue
            status_id = str(node.get('id') or '')
            if status_id:
                node['video']['stream_url'] = (
                    f'{base}?token={utils.make_video_token(status_id)}')


@require_http_methods(['GET', 'POST'])
def channels_view(request):
    """微博频道分类（「我的频道」+「频道推荐」）

    :param cookie: 可选，调用方自带的微博登录 Cookie；留空用平台托管的账号
    :return: data = {count, groups: [{section, count, channels: [...]}]}
    """
    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.get_channels(cookie=cookie)
    if not ok:
        return _error_response(result)
    return _json_response(StatusCode.SUCCESS, data={
        'count': sum(group['count'] for group in result),
        'groups': result,
    })


@require_http_methods(['GET', 'POST'])
def feed_view(request):
    """按频道取内容

    :param channel:     可选，频道 gid（网页 /hot/weibo/{id} 里的数字），默认 102803（热门）
    :param containerid: 可选，频道 containerid；留空则按 channel 自动解析
    :param limit:       可选，返回条数，1~50（默认 20）
    :param since_id:    可选，翻页游标，首次传 0；下一页传上次返回的 next_since_id
    :param cookie:      可选，调用方自带的微博登录 Cookie
    """
    channel = str(_param(request, 'channel') or DEFAULT_CHANNEL).strip() or DEFAULT_CHANNEL
    if not channel.isdigit():
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg='参数值非法: channel 需为频道 ID（纯数字），可用 /api/weibo/channels 获取')

    containerid = (_param(request, 'containerid') or '').strip()
    limit, error = _optional_int(_param(request, 'limit'), 'limit',
                                 DEFAULT_LIMIT, 1, MAX_LIMIT)
    if error:
        return error

    since_id = str(_param(request, 'since_id') or '0').strip() or '0'
    if not since_id.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg='参数格式错误: since_id 必须为整数')

    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.get_feed(channel, containerid, limit, since_id, cookie=cookie)
    if not ok:
        return _error_response(result)
    _fill_stream_urls(request, result)
    return _json_response(StatusCode.SUCCESS, data=result)


@require_http_methods(['GET', 'POST'])
def check_view(request):
    """校验微博登录凭据是否有效

    :param cookie: 可选，调用方自带的微博登录 Cookie；留空则校验平台托管的账号
    :return: data = {valid: bool, account: 账号标识（自带 Cookie 时为空）, message: 说明}
    """
    cookie = (_param(request, 'cookie') or '').strip()
    ok, result = utils.check_credential(cookie=cookie)
    if not ok:
        return _error_response(result)
    # 凭据无效不是「请求失败」——接口本身调通了，所以仍返回成功码，
    # 把 valid / message 放在 data 里，由调用方决定怎么处理。
    return _json_response(StatusCode.SUCCESS, data=result,
                          msg=result.get('message') or None)


@require_http_methods(['GET', 'HEAD'])
def video_view(request):
    """微博视频代理播放：本站带 Referer 取流后转发，`<video>` 标签可直接播放

    为什么需要代理：微博视频 CDN 有 **Referer 防盗链**，只认微博系域名 —— 第三方页面的
    `<video>` 带的是自己的域名，一律 403；直链又是 `http://`，https 页面还会被浏览器按
    混合内容直接拦掉。本端点带 `Referer` 取流后原样转发，调用方拿到的就是可直接播的地址。

    鉴权：URL 里是 `/api/weibo/feed` 下发的**时效令牌**（`<video>` 带不了项目签名），
    令牌里只有微博 id，播放时按 id 现场解析**新鲜**直链（微博直链带 Expires 会过期）；
    本路径另在代码内免签名单里（见 `API/common/middleware.py` 的 `PUBLIC_PATHS`）。

    HTTP 契约（**不是**统一 JSON 信封）：成功返回 `video/mp4` 二进制流，
    200 整段 / 206 分片，**支持 Range**（可拖进度条、可断点续传）；
    令牌无效或过期返回 403，上游取流失败走统一错误码（40001 / 50002）。

    :param token: 必填，由 `/api/weibo/feed` 返回的 `video.stream_url` 携带
    """
    status_id, error = utils.parse_video_token((request.GET.get('token') or '').strip())
    if status_id is None:
        return JsonResponse({'code': StatusCode.FORBIDDEN, 'msg': error, 'data': None},
                            status=403)

    ok, upstream = utils.open_video(
        status_id, range_header=request.META.get('HTTP_RANGE') or '')
    if not ok:
        return _error_response(upstream)

    def _stream(resp, chunk_size=64 * 1024):
        """边收边发；无论正常结束还是中断，都要关掉上游连接"""
        try:
            for chunk in resp.iter_content(chunk_size):
                if chunk:
                    yield chunk
        finally:
            resp.close()

    response = StreamingHttpResponse(
        _stream(upstream), status=upstream.status_code,
        content_type=upstream.headers.get('Content-Type') or 'video/mp4')
    # 透传分片相关响应头，浏览器才能拖动进度条 / 断点续传
    for header in ('Content-Length', 'Content-Range'):
        if upstream.headers.get(header):
            response[header] = upstream.headers[header]
    response['Accept-Ranges'] = upstream.headers.get('Accept-Ranges', 'bytes')
    response['Cache-Control'] = 'private, max-age=600'
    return response
