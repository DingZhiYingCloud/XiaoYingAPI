"""消息推送 push 视图层 —— Server酱线路

对外端点（均需项目签名，按服务策略 fail-closed）：
    POST /api/push/serverchan/send    发送消息
    GET  /api/push/serverchan/status  查询推送送达状态
SendKey 由服务端托管（控制台「账号管理」，platform=serverchan），调用方不传。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode

from . import utils

# noip 的真值写法（表单过来的都是字符串）
_TRUTHY = ('1', 'true', 'yes', 'on')


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


@require_http_methods(['POST'])
def send_view(request):
    """发送一条消息到 Server酱

    表单参数:
        title            (必填): 消息标题，最长 32 个字符、不能含换行
        desp             (选填): 消息正文，支持 Markdown
        channel          (选填): 指定消息通道（通道值见文档；不传用后台设置的默认通道）
        short            (选填): 卡片消息的短链标题
        tags             (选填): 标签，多个用 | 分隔
        openid           (选填): 企业微信通道抄送的成员 openid，多个用 | 分隔
        noip             (选填): 传 1 / true / yes / on 时隐藏调用方 IP
        encrypt_password (选填): 阅读密码；填了即对 desp 端对端加密后再推送

    返回 data: {pushid, readkey, encrypted}
    """
    title = (request.POST.get('title') or '').strip()
    desp = request.POST.get('desp') or ''
    encrypt_password = request.POST.get('encrypt_password') or ''

    if not title:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: title(消息标题)')
    if len(title) > utils.TITLE_MAX_LEN:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: title 最长 {utils.TITLE_MAX_LEN} 个字符')
    if '\n' in title or '\r' in title:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: title 不能包含换行')
    if encrypt_password and not desp.strip():
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg='参数值非法: 端对端加密需要提供非空的 desp(消息正文)')

    app_id = getattr(getattr(request, 'auth_app', None), 'app_id', '')
    ok, result = utils.send(
        title, desp,
        channel=(request.POST.get('channel') or '').strip(),
        short=(request.POST.get('short') or '').strip(),
        tags=(request.POST.get('tags') or '').strip(),
        openid=(request.POST.get('openid') or '').strip(),
        noip=(request.POST.get('noip') or '').strip().lower() in _TRUTHY,
        encrypt_password=encrypt_password,
        app_id=app_id or '',
    )
    if not ok:
        # 未配置 SendKey / 上游拒绝 / 网络异常，统一归为外部服务错误，msg 带回原因
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result['message'])
    return _json_response(StatusCode.SUCCESS, data=result)


@require_http_methods(['GET'])
def status_view(request):
    """查询一条推送的送达状态

    查询参数:
        pushid  (必填): 发送消息返回的 pushid
        readkey (必填): 发送消息返回的 readkey

    返回 data 为上游推送详情（wxstatus 即微信接口的返回结果，为空表示可能还未执行）。
    """
    pushid = (request.GET.get('pushid') or '').strip()
    readkey = (request.GET.get('readkey') or '').strip()
    missing = [name for name, value in (('pushid', pushid), ('readkey', readkey)) if not value]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, msg=f"参数缺失: {'、'.join(missing)}")

    ok, result = utils.query_status(pushid, readkey)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=result['message'])
    return _json_response(StatusCode.SUCCESS, data=result)
