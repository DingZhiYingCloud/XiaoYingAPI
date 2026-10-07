"""消息推送 push · QQBot 线路 视图层

`POST /api/push/qqbot/send`：通过 NapCat（OneBot 11 HTTP）把一条纯文本消息发到 QQ 群 / 好友。
HTTP 地址与 token 由服务端托管（控制台「QQBot」页），调用方只传目标与内容。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode

from . import utils


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


@require_http_methods(['POST'])
def send_view(request):
    """发送一条 QQ 消息（纯文本）

    表单参数:
        target_type (必填): 目标类型，group=群聊 / private=私聊
        target_id   (必填): 群号 / 好友 QQ 号（纯数字）
        message     (必填): 消息正文（纯文本，按原样发送，不会解析 CQ 码）

    返回 data: {message_id}（上游返回的消息 ID）
    """
    target_type = (request.POST.get('target_type') or '').strip()
    target_id = (request.POST.get('target_id') or '').strip()
    message = request.POST.get('message') or ''

    missing = [name for name, value in (('target_type', target_type), ('target_id', target_id),
                                        ('message', message.strip())) if not value]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, msg=f"参数缺失: {'、'.join(missing)}")
    if target_type not in utils.TARGET_TYPES:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: target_type 只能为 group / private')
    if not target_id.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg='参数格式错误: target_id 必须是数字（群号 / QQ 号）')

    app_id = getattr(getattr(request, 'auth_app', None), 'app_id', '')
    ok, result = utils.send(message, target_type, target_id, app_id=app_id or '')
    if not ok:
        # 未配置地址 / 上游拒绝 / 网络异常，统一归为外部服务错误，msg 带回原因
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result['message'])
    return _json_response(StatusCode.SUCCESS, data=result)
