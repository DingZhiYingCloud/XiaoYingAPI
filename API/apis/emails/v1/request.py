"""邮箱服务请求处理视图

提供发送邮件的 API,接收 POST 表单数据。
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from API.common import StatusCode
from .utils import send_email


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


@require_http_methods(['POST'])  # 仅允许 POST 请求,其他方法返回 405
def send_email_view(request):
    """
    发送邮件 API

    请求方式: POST (application/x-www-form-urlencoded 表单)

    表单参数:
        subject    : 邮件标题 (必填)
        body       : 邮件正文内容 (必填)
        recipients : 收件人邮箱 (必填,支持多个)
                     - 方式1: 同一字段重复传递多次  recipients=a@xx.com&recipients=b@xx.com
                     - 方式2: 单个字段用逗号分隔    recipients=a@xx.com,b@xx.com

    返回示例 (成功):
        {"code": 10000, "msg": "成功", "data": {"recipients": ["a@xx.com"], "subject": "..."}}
    """
    # ---------- 1. 参数获取 ----------
    subject = request.POST.get('subject')
    body = request.POST.get('body')
    # getlist: 获取同名字段的多个值;同时兼容单个字段中用逗号分隔的情况
    recipients_raw = request.POST.getlist('recipients')

    # ---------- 2. 参数校验 ----------
    # 2.1 必填校验
    if not subject:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: subject(邮件标题)')
    if not body:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: body(邮件正文内容)')
    if not recipients_raw:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: recipients(收件人邮箱)')

    # 2.2 解析收件人列表(兼容逗号分隔与多字段两种方式)
    recipients = []
    for item in recipients_raw:
        # 按逗号拆分并去除首尾空白,过滤空字符串
        recipients.extend([addr.strip() for addr in item.split(',') if addr.strip()])

    # 去重,避免向同一收件人重复发送
    recipients = list(dict.fromkeys(recipients))

    if not recipients:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='收件人邮箱列表为空')

    # 2.3 邮箱格式校验
    invalid_emails = []
    for addr in recipients:
        try:
            validate_email(addr)
        except ValidationError:
            invalid_emails.append(addr)
    if invalid_emails:
        return _json_response(
            StatusCode.PARAM_FORMAT_ERROR,
            msg=f'邮箱格式错误: {", ".join(invalid_emails)}',
        )

    # ---------- 3. 发送邮件 ----------
    success, message = send_email(subject, body, recipients)
    if not success:
        # 发送失败归为外部服务错误
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=message)

    # ---------- 4. 返回成功结果 ----------
    return _json_response(
        StatusCode.SUCCESS,
        data={
            'subject': subject,
            'recipients': recipients,
            'count': len(recipients),
        },
    )
