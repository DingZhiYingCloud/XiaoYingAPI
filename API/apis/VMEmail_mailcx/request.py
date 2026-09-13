"""VMEmail 虚拟邮件(mail.cx) API 请求处理视图

提供 4 个接口, 对应爬虫的 4 个对外方法:
    GET  /api/VMEmail_mailcx/domains       获取可用后缀域名列表
    POST /api/VMEmail_mailcx/generate      生成临时邮箱地址
    GET  /api/VMEmail_mailcx/emails        获取邮箱邮件列表(长轮询)
    GET  /api/VMEmail_mailcx/email_detail  获取单封邮件完整详情

会话机制:
    mail.cx 无服务端会话, 邮箱地址本身即唯一标识; client_id 由 generate 返回,
    客户端保存后可在其余接口回传以复用同一客户端身份。
    邮件列表 / 详情接口需显式传入 address / email_id(服务端不保存任何状态)。
"""
import re

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils

# 邮箱地址基本格式校验(本地部分@域名), 不额外限制长度, 真实性交由上游返回结果
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
# 邮件 id 长度上限, 防御超长输入
_EMAIL_ID_MAX_LEN = 128


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体

    :param code: 状态码(参见 StatusCode)
    :param data: 业务数据, 默认为 None
    :param msg:  自定义消息, 未传则使用状态码对应的默认描述
    """
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


@require_http_methods(['GET'])
def domains_view(request):
    """获取可用后缀域名列表接口

    无参数。返回官网当前可用的全部后缀域名, 用于生成邮箱时指定 domain。
    """
    success, data = utils.list_domains()
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['POST'])
def generate_view(request):
    """生成临时邮箱地址接口

    表单参数(application/x-www-form-urlencoded):
        domain    (选填): 指定后缀域名, 需为 domains 接口返回的域名之一, 默认 uqu.me
        client_id (选填): 客户端标识; 不传由服务端随机生成, 传已知值可复用同一客户端身份
    """
    # ---------- 1. 参数获取与校验 ----------
    domain = request.POST.get('domain', '').strip() or None
    client_id = request.POST.get('client_id', '').strip() or None

    if domain is not None and domain not in utils.SUPPORTED_DOMAINS:
        return _json_response(
            StatusCode.PARAM_VALUE_INVALID,
            msg=f'参数值非法: domain 仅支持 {"/".join(utils.SUPPORTED_DOMAINS)}',
        )

    # ---------- 2. 调用爬虫 ----------
    success, data = utils.generate_email(domain=domain, client_id=client_id)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)


@require_http_methods(['GET'])
def emails_view(request):
    """获取邮箱邮件列表接口(长轮询)

    Query 参数:
        address   (必填): 邮箱地址, 如 abc123@uqu.me
        since     (选填): 增量时间戳(秒), 非负整数; 不传返回当前全部邮件,
                          传入后仅返回该时间之后的新邮件
        client_id (选填): 客户端标识, 与生成邮箱时的 client_id 保持一致

    说明: 上游为长轮询, 无新邮件时会挂起约 25 秒后返回空列表。
    """
    # ---------- 1. 参数获取与校验 ----------
    address = request.GET.get('address', '').strip()
    since_raw = request.GET.get('since', '').strip()
    client_id = request.GET.get('client_id', '').strip() or None

    if not address:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: address(邮箱地址)')
    if not _EMAIL_RE.match(address):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: address 必须为合法邮箱地址')

    since = None
    if since_raw:
        try:
            since = int(since_raw)
            if since < 0:
                raise ValueError
        except ValueError:
            return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                                  msg='参数格式错误: since 必须为非负整数(秒级时间戳)')

    # ---------- 2. 调用爬虫 ----------
    success, data = utils.get_emails(address=address, since=since, client_id=client_id)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    msg = f'查询成功，共 {len(data)} 封邮件' if data else '查询成功，暂无新邮件'
    return _json_response(StatusCode.SUCCESS, data=data, msg=msg)


@require_http_methods(['GET'])
def email_detail_view(request):
    """获取单封邮件完整详情接口

    Query 参数:
        email_id  (必填): 邮件 id, 来自邮件列表接口返回的 id 字段
        client_id (选填): 客户端标识, 与生成邮箱时的 client_id 保持一致
    """
    # ---------- 1. 参数获取与校验 ----------
    email_id = request.GET.get('email_id', '').strip()
    client_id = request.GET.get('client_id', '').strip() or None

    if not email_id:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: email_id(邮件 id)')
    if len(email_id) > _EMAIL_ID_MAX_LEN:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg=f'参数格式错误: email_id 长度不能超过 {_EMAIL_ID_MAX_LEN}')

    # ---------- 2. 调用爬虫 ----------
    success, data = utils.get_email_detail(email_id, client_id=client_id)
    if not success:
        # 爬虫对「邮件不存在」返回固定前缀，据此区分资源不存在与上游异常
        if data.startswith('邮件不存在'):
            return _json_response(StatusCode.NOT_FOUND, msg=data)
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
