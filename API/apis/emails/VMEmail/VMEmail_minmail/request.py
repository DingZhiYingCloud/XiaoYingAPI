"""VMEmail 虚拟邮件(minmail.app) API 请求处理视图

提供 2 个接口,对应爬虫的 2 个对外方法:
    POST /api/emails/VMEmail/minmail/generate  生成/获取临时邮箱
    GET  /api/emails/VMEmail/minmail/emails     获取当前邮箱的邮件列表

会话机制:
    临时邮箱通过 visitor_id(UUID) 标识。generate 接口返回 visitor_id,
    客户端需妥善保存,后续查询邮件时通过 visitor_id 复用同一邮箱。
"""
import uuid

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


def _is_valid_uuid(value):
    """校验字符串是否为合法的 UUID 格式。

    :param value: 待校验的字符串
    :return: bool
    """
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


@require_http_methods(['POST'])
def generate_view(request):
    """
    生成/获取临时邮箱接口

    表单参数(application/x-www-form-urlencoded):
        visitor_id (选填): 访客标识(UUID)。
            - 不传: 随机生成,对应一个全新的临时邮箱
            - 传入已知值: 复用过期期内的已有邮箱
        expire     (选填): 邮箱过期时间(分钟),正整数,默认 1440(24小时)
        refresh    (选填): 是否强制生成新邮箱,接受 "true"/"false",默认 "false"
                           注意: refresh=true 时原邮箱及其邮件将被丢弃
    """
    # ---------- 1. 参数获取与校验 ----------
    visitor_id = request.POST.get('visitor_id', '').strip()
    if visitor_id:
        if not _is_valid_uuid(visitor_id):
            return _json_response(
                StatusCode.PARAM_FORMAT_ERROR,
                msg='参数格式错误: visitor_id 必须为合法 UUID',
            )
    else:
        visitor_id = None  # 空字符串视为未传,交由爬虫随机生成

    # expire: 选填,默认1440,必须为正整数
    expire_str = request.POST.get('expire', '').strip()
    expire = 1440  # 默认24小时
    if expire_str:
        try:
            expire = int(expire_str)
            if expire <= 0:
                raise ValueError
        except ValueError:
            return _json_response(
                StatusCode.PARAM_FORMAT_ERROR,
                msg='参数格式错误: expire 必须为正整数(分钟)',
            )

    # refresh: 选填,默认 False,接受 "true"/"false"(大小写不敏感)
    refresh_str = request.POST.get('refresh', 'false').strip().lower()
    if refresh_str not in ('true', 'false'):
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: refresh 仅接受 true 或 false',
        )
    refresh = refresh_str == 'true'

    # ---------- 2. 调用爬虫 ----------
    success, data = utils.generate_email(
        visitor_id=visitor_id, expire=expire, refresh=refresh
    )
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def emails_view(request):
    """
    获取邮件列表接口

    Query 参数:
        visitor_id (必填): 访客标识(UUID),需为 generate 接口返回的 visitor_id
    """
    # ---------- 1. 参数获取与校验 ----------
    visitor_id = request.GET.get('visitor_id', '').strip()
    if not visitor_id:
        return _json_response(
            StatusCode.PARAM_MISSING,
            msg='参数缺失: visitor_id(访客标识)',
        )
    if not _is_valid_uuid(visitor_id):
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg='参数格式错误: visitor_id 必须为合法 UUID',
        )

    # ---------- 2. 调用爬虫 ----------
    success, data = utils.get_emails(visitor_id)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
