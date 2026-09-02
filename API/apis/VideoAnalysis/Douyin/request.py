"""抖音视频/图文解析 API 请求处理视图

提供 1 个接口,对应爬虫的对外方法:
    POST /api/video_analysis/douyin/parse   解析抖音视频/图文
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


@require_http_methods(['POST'])
def parse_view(request):
    """
    解析抖音视频/图文接口

    表单参数(application/x-www-form-urlencoded):
        share_text (必填): 抖音分享文本(完整复制内容,含链接和描述)
            支持三种输入:
            1. 完整分享文本 - 抖音App分享弹窗复制的全部内容
               示例: "5.89 dAT:/ ... https://v.douyin.com/xxxxx/ 复制此链接,打开Dou音搜索,直接观看视频！"
            2. 链接 - 短链(v.douyin.com/xxx)或完整视频页链接(www.douyin.com/video/xxx)
            3. 纯数字 aweme_id(视频ID)
    """
    share_text = request.POST.get('share_text', '').strip()
    if not share_text:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg='参数缺失: share_text(抖音分享文本)',
        )

    success, data = utils.parse_video(share_text)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
