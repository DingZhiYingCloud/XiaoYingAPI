"""消息推送 push · 邮件定时推送线路 视图层

对外端点（均需项目签名，按服务策略 fail-closed；任务按 app_id 隔离）：
    POST /api/push/email_task/create  新建任务
    GET  /api/push/email_task/list    分页列出本项目的任务
    GET  /api/push/email_task/detail  查单个任务
    POST /api/push/email_task/update  修改任务（含启停）
    POST /api/push/email_task/delete  删除任务（支持批量）

任务语义：`interval_minutes=0` 只发一次；`>0` 每 N 分钟重复，直到停用或删除。
"""
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from API.common import StatusCode

from . import utils

# first_send_at 允许的写法（不带时区，按 settings.TIME_ZONE 解释）
_DT_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M')
_TRUTHY = ('1', 'true', 'yes', 'on')
_FALSY = ('0', 'false', 'no', 'off')


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _parse_bool(value):
    """表单布尔解析；无法识别返回 None"""
    text = (value or '').strip().lower()
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    return None


def _collect_recipients(request):
    """解析收件人（逗号 / 换行分隔，兼容同名字段多次传递）

    :return: (list, None) 或 (None, (状态码, 提示))
    """
    addresses = []
    for item in request.POST.getlist('recipients'):
        addresses.extend([a.strip() for a in item.replace('\n', ',').split(',') if a.strip()])
    addresses = list(dict.fromkeys(addresses))
    if not addresses:
        return None, (StatusCode.PARAM_MISSING, '参数缺失: recipients(收件人邮箱)')
    if len(addresses) > utils.MAX_RECIPIENTS:
        return None, (StatusCode.PARAM_VALUE_INVALID,
                      f'参数值非法: 收件人最多 {utils.MAX_RECIPIENTS} 个')
    invalid = []
    for addr in addresses:
        try:
            validate_email(addr)
        except ValidationError:
            invalid.append(addr)
    if invalid:
        return None, (StatusCode.PARAM_FORMAT_ERROR, f'邮箱格式错误: {", ".join(invalid)}')
    return addresses, None


def _resolve_interval(request):
    """按 repeat / interval_minutes 推导发送间隔（分钟）

    规则：repeat=false（仅一次）时 interval 必须为 0；repeat=true 时 interval 必须 ≥1；
    未传 repeat 时由 interval 推导（>0 即重复）。
    :return: (interval_minutes, None) 或 (None, (状态码, 提示))
    """
    repeat_raw = (request.POST.get('repeat') or '').strip()
    interval_raw = (request.POST.get('interval_minutes') or '').strip()

    repeat = None
    if repeat_raw:
        repeat = _parse_bool(repeat_raw)
        if repeat is None:
            return None, (StatusCode.PARAM_FORMAT_ERROR,
                          '参数格式错误: repeat 只能为 true / false')

    interval = None
    if interval_raw:
        if not interval_raw.isdigit():
            return None, (StatusCode.PARAM_FORMAT_ERROR,
                          '参数格式错误: interval_minutes 必须为非负整数')
        interval = int(interval_raw)
        if interval > utils.MAX_INTERVAL_MINUTES:
            return None, (StatusCode.PARAM_VALUE_INVALID,
                          f'参数值非法: interval_minutes 最大 {utils.MAX_INTERVAL_MINUTES} 分钟')

    if repeat is False:
        if interval not in (None, 0):
            return None, (StatusCode.PARAM_VALUE_INVALID,
                          '参数值非法: 仅发送一次时 interval_minutes 必须为 0')
        return 0, None
    if repeat is True:
        if interval is None or interval < 1:
            return None, (StatusCode.PARAM_VALUE_INVALID,
                          '参数值非法: 重复发送时 interval_minutes 必须为大于 0 的整数(分钟)')
        return interval, None
    return (interval or 0), None


def _resolve_first_send_at(request):
    """解析首次发送时间（选填）；为空返回 (None, None)"""
    raw = (request.POST.get('first_send_at') or '').strip()
    if not raw:
        return None, None
    for fmt in _DT_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt, None
    return None, (StatusCode.PARAM_FORMAT_ERROR,
                  '参数格式错误: first_send_at 需形如 2026-10-09 15:30 或 2026-10-09 15:30:00')


def _app_id(request):
    """取当前请求的归属项目 APPID（签名中间件已挂到 request.auth_app）"""
    return getattr(getattr(request, 'auth_app', None), 'app_id', '') or ''


@require_http_methods(['POST'])
def create_view(request):
    """新建一个邮件定时推送任务

    表单参数:
        recipients       (必填): 收件人邮箱，多个用逗号或换行分隔
        subject          (必填): 邮件标题
        body             (必填): 邮件正文
        repeat           (选填): 是否重复发送（true/false）；不传则由 interval_minutes 推导
        interval_minutes (选填): 发送间隔（分钟）；0=只发一次，重复时需 ≥1
        first_send_at    (选填): 首次发送时间，如 2026-10-09 15:30；不传=创建后立即进入调度
    """
    recipients, err = _collect_recipients(request)
    if err:
        return _json_response(err[0], msg=err[1])

    subject = (request.POST.get('subject') or '').strip()
    body = request.POST.get('body') or ''
    if not subject:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: subject(邮件标题)')
    if len(subject) > 255:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: subject 最长 255 个字符')
    if not body.strip():
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: body(邮件正文)')

    interval_minutes, err = _resolve_interval(request)
    if err:
        return _json_response(err[0], msg=err[1])

    first_send_at, err = _resolve_first_send_at(request)
    if err:
        return _json_response(err[0], msg=err[1])

    task = utils.create_task(_app_id(request), recipients, subject, body,
                             interval_minutes, first_send_at=first_send_at)
    return _json_response(StatusCode.SUCCESS, data=utils.serialize(task), msg='任务创建成功')


@require_http_methods(['GET'])
def list_view(request):
    """分页列出本项目的任务

    查询参数:
        page       (选填): 页码，从 1 开始，默认 1
        page_size  (选填): 每页数量，默认 20，1-100
        enabled    (选填): true/false 只看启用/停用的任务
    """
    page_raw = (request.GET.get('page') or '1').strip()
    size_raw = (request.GET.get('page_size') or '20').strip()
    if not page_raw.isdigit() or not size_raw.isdigit():
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg='参数格式错误: page / page_size 必须为整数')
    page, page_size = int(page_raw), int(size_raw)
    if page < 1:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: page 从 1 开始')
    if page_size < 1 or page_size > utils.MAX_PAGE_SIZE:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: page_size 必须在 1-{utils.MAX_PAGE_SIZE} 之间')

    enabled_raw = (request.GET.get('enabled') or '').strip()
    enabled = None
    if enabled_raw:
        enabled = _parse_bool(enabled_raw)
        if enabled is None:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: enabled 只能为 true / false')

    return _json_response(StatusCode.SUCCESS,
                          data=utils.list_tasks(_app_id(request), page, page_size, enabled))


@require_http_methods(['GET'])
def detail_view(request):
    """查询单个任务

    查询参数:
        id (必填): 任务 ID
    """
    task_id = (request.GET.get('id') or '').strip()
    if not task_id:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: id(任务ID)')
    ok, result = utils.get_task(_app_id(request), task_id)
    if not ok:
        return _json_response(StatusCode.NOT_FOUND, msg=result)
    return _json_response(StatusCode.SUCCESS, data=utils.serialize(result))


@require_http_methods(['POST'])
def update_view(request):
    """修改任务（只改传入的字段，未传的保持不变）

    表单参数:
        id               (必填): 任务 ID
        recipients/subject/body      (选填): 修改对应字段
        repeat / interval_minutes    (选填): 修改发送方式（改间隔会按当前时间重排下一次）
        enabled          (选填): true/false 启用 / 停用
    """
    task_id = (request.POST.get('id') or '').strip()
    if not task_id:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: id(任务ID)')
    ok, task = utils.get_task(_app_id(request), task_id)
    if not ok:
        return _json_response(StatusCode.NOT_FOUND, msg=task)

    changes = {}
    if request.POST.getlist('recipients'):
        recipients, err = _collect_recipients(request)
        if err:
            return _json_response(err[0], msg=err[1])
        changes['recipients'] = recipients
    if 'subject' in request.POST:
        subject = (request.POST.get('subject') or '').strip()
        if not subject:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: subject 不能为空')
        if len(subject) > 255:
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: subject 最长 255 个字符')
        changes['subject'] = subject
    if 'body' in request.POST:
        body = request.POST.get('body') or ''
        if not body.strip():
            return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: body 不能为空')
        changes['body'] = body
    if 'repeat' in request.POST or 'interval_minutes' in request.POST:
        interval_minutes, err = _resolve_interval(request)
        if err:
            return _json_response(err[0], msg=err[1])
        changes['interval_minutes'] = interval_minutes
    if 'enabled' in request.POST:
        enabled = _parse_bool(request.POST.get('enabled'))
        if enabled is None:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: enabled 只能为 true / false')
        changes['enabled'] = enabled

    if not changes:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: 至少提供一个要修改的字段')

    utils.update_task(task, **changes)
    return _json_response(StatusCode.SUCCESS, data=utils.serialize(task), msg='任务已更新')


@require_http_methods(['POST'])
def delete_view(request):
    """删除任务（支持批量）

    表单参数:
        id (必填): 任务 ID；可重复传递或用逗号分隔传多个，也兼容 ids 字段名
    """
    ids = []
    for item in request.POST.getlist('id') + request.POST.getlist('ids'):
        ids.extend([x.strip() for x in item.replace('\n', ',').split(',') if x.strip()])
    ids = list(dict.fromkeys(ids))
    if not ids:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: id(任务ID)')

    deleted = utils.delete_tasks(_app_id(request), ids)
    return _json_response(StatusCode.SUCCESS, data={'deleted': deleted}, msg='删除成功')
