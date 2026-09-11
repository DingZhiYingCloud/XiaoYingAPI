"""抖音评论发布 API 请求处理视图

提供 1 个接口,对应爬虫的对外方法:
    POST /api/douyin/comment/publish   发布一条抖音一级评论
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
def publish_view(request):
    """发布一条抖音一级评论

    表单参数(application/x-www-form-urlencoded):
        cookie   (必填): 抖音登录 Cookie 完整字符串(浏览器登录抖音后复制)
        aweme_id (必填): 目标视频 ID(纯数字,取自视频页 URL /video/<aweme_id>)
        text     (必填): 评论内容(一级纯文本评论)
    """
    cookie = request.POST.get('cookie', '').strip()
    aweme_id = request.POST.get('aweme_id', '').strip()
    text = request.POST.get('text', '').strip()

    missing = [name for name, value in
               (('cookie', cookie), ('aweme_id', aweme_id), ('text', text)) if not value]
    if missing:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg=f"参数缺失: {', '.join(missing)}",
        )

    if not aweme_id.isdigit():
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: aweme_id 必须为纯数字视频ID',
        )

    success, data = utils.publish_comment(cookie, aweme_id, text)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
