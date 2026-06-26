"""Seekin 视频解析 API 请求处理视图

提供 3 个接口,对应爬虫的 3 个对外方法:
    POST /api/video_analysis/seekin/parse              解析抖音视频
    POST /api/video_analysis/seekin/parse/xiaohongshu  解析小红书内容
    POST /api/video_analysis/seekin/parse/bilibili     解析哔哩哔哩视频
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


def _get_share_text_or_error(request, platform_label):
    """
    从 POST 表单提取并校验 share_text 参数。

    :param request: HTTP 请求对象
    :param platform_label: 平台中文名(用于错误提示),如 "抖音"
    :return: tuple[bool, str|JsonResponse]
        - 校验通过: (True, share_text)
        - 校验失败: (False, 错误响应对象)
    """
    share_text = request.POST.get('share_text', '').strip()
    if not share_text:
        return False, _json_response(
            StatusCode.PARAM_MISSING,
            msg=f'参数缺失: share_text({platform_label}分享文本)',
        )
    return True, share_text


@require_http_methods(['POST'])
def parse_view(request):
    """
    解析抖音视频接口

    表单参数(application/x-www-form-urlencoded):
        share_text (必填): 抖音分享文本(完整复制内容,含链接和描述)
            示例: "5.89 dAT:/ ... https://v.douyin.com/xxxxx/ 复制此链接,打开Dou音搜索,直接观看视频！"
            只需把分享弹窗里复制的全部文本传入即可
    """
    ok, result = _get_share_text_or_error(request, '抖音')
    if not ok:
        return result
    share_text = result

    success, data = utils.parse_video(share_text)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def parse_xiaohongshu_view(request):
    """
    解析小红书内容接口

    支持视频笔记和图文笔记两种类型:
        - 视频笔记: 返回的 medias 含视频下载链接,images 为空
        - 图文笔记: 返回的 medias 为空,images 含图片下载链接

    表单参数(application/x-www-form-urlencoded):
        share_text (必填): 小红书分享文本(完整复制内容,含链接和描述)
            示例: "13 【标题 - 作者 | 小红书 - 你的生活兴趣社区】 😆 xxx 😆 https://www.xiaohongshu.com/..."
    """
    ok, result = _get_share_text_or_error(request, '小红书')
    if not ok:
        return result
    share_text = result

    success, data = utils.parse_xiaohongshu(share_text)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def parse_bilibili_view(request):
    """
    解析哔哩哔哩视频接口

    表单参数(application/x-www-form-urlencoded):
        share_text (必填): 哔哩哔哩分享文本(完整复制内容,含链接和描述)
            示例: "【标题】 https://www.bilibili.com/video/BVxxxx/?share_source=copy_web&..."
    """
    ok, result = _get_share_text_or_error(request, '哔哩哔哩')
    if not ok:
        return result
    share_text = result

    success, data = utils.parse_bilibili(share_text)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
