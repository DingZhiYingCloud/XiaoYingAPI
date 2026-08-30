"""阿里云短信验证码认证 API 视图

接口清单（全部 POST + form-urlencoded，需用户中心项目签名）：
    POST /api/sms_verify/aliyun/send   发送短信验证码
    POST /api/sms_verify/aliyun/check  核验短信验证码

鉴权: 复用用户中心项目签名（APPID + APPSECRET + timestamp/nonce/sign），
      只有已注册的接入项目才能调用，防止短信被滥用（短信轰炸）。
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


def _parse_params(request):
    """合并 form body 与 query 参数（签名参数可能在 body 或 query）"""
    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})
    return params


def _fail_response(msg):
    """根据错误消息映射状态码：参数类→2xxxx，阿里云调用失败→40001"""
    if msg.startswith('参数缺失'):
        return _json_response(StatusCode.PARAM_MISSING, msg=msg)
    if msg.startswith('参数格式错误'):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg=msg)
    if msg.startswith('参数值非法'):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg=msg)
    return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=msg)


def _valid_phone(phone):
    """手机号基础校验：11 位纯数字（国内）"""
    return phone.isdigit() and len(phone) == 11


@require_http_methods(['POST'])
def send_view(request):
    """发送短信验证码

    表单参数：
        phone             (必填): 11 位手机号
        code_length       (选填): 验证码长度 4-8，默认 4
        valid_time        (选填): 验证码有效时长秒，默认 300
        duplicate_policy  (选填): 重复发送处理，1=覆盖旧码 2=保留，默认 1
        interval          (选填): 发送间隔秒（频控），默认 60
        code_type         (选填): 验证码类型 1-7（1=纯数字），默认 1
        return_verify_code(选填): true 时响应返回验证码（仅测试场景建议开启），默认 false
        scheme_name       (选填): 方案名称，留空使用默认方案
        out_id            (选填): 外部流水号（透传）
    另有签名参数：app_id / timestamp / nonce / sign
    """
    params = _parse_params(request)
    # 项目签名已由 ApiAuthMiddleware 统一校验（sms_verify 服务级策略要求认证）
    phone = (params.get('phone') or '').strip()
    if not phone:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: phone(手机号)')
    if not _valid_phone(phone):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: phone 必须为 11 位手机号')

    try:
        code_length = int(params.get('code_length', 4))
        valid_time = int(params.get('valid_time', 300))
        duplicate_policy = int(params.get('duplicate_policy', 1))
        interval = int(params.get('interval', 60))
        code_type = int(params.get('code_type', 1))
    except (ValueError, TypeError):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg='参数格式错误: code_length/valid_time/duplicate_policy/interval/code_type 必须为整数')

    if not (4 <= code_length <= 8):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: code_length 仅支持 4-8')
    if duplicate_policy not in (1, 2):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: duplicate_policy 仅支持 1(覆盖)或 2(保留)')
    if code_type not in (1, 2, 3, 4, 5, 6, 7):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: code_type 仅支持 1-7')

    return_verify_code = str(params.get('return_verify_code', 'false')).lower() in ('true', '1', 'yes')

    ok, data = utils.send_verify_code(
        phone,
        code_length=code_length,
        valid_time=valid_time,
        duplicate_policy=duplicate_policy,
        interval=interval,
        code_type=code_type,
        return_verify_code=return_verify_code,
        scheme_name=params.get('scheme_name', ''),
        out_id=params.get('out_id', ''),
    )
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='发送成功')


@require_http_methods(['POST'])
def check_view(request):
    """核验短信验证码

    表单参数：
        phone             (必填): 11 位手机号
        verify_code       (必填): 验证码
        case_auth_policy  (选填): 大小写核验策略，1=不区分 2=区分，默认 1
        scheme_name       (选填): 方案名称（必须与发送时一致），留空使用默认方案
        out_id            (选填): 外部流水号
    另有签名参数：app_id / timestamp / nonce / sign

    核验结果语义：接口请求成功即返回 code=10000，data.verify_result 为
    PASS(核验成功)/UNKNOWN(核验失败)，业务结果由调用方根据该字段判断。
    """
    params = _parse_params(request)
    # 项目签名已由 ApiAuthMiddleware 统一校验（sms_verify 服务级策略要求认证）
    phone = (params.get('phone') or '').strip()
    verify_code = (params.get('verify_code') or '').strip()
    if not phone:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: phone(手机号)')
    if not verify_code:
        return _json_response(StatusCode.PARAM_MISSING, msg='参数缺失: verify_code(验证码)')
    if not _valid_phone(phone):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: phone 必须为 11 位手机号')

    try:
        case_auth_policy = int(params.get('case_auth_policy', 1))
    except (ValueError, TypeError):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: case_auth_policy 必须为整数')
    if case_auth_policy not in (1, 2):
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='参数值非法: case_auth_policy 仅支持 1(不区分大小写)或 2(区分大小写)')

    ok, data = utils.check_verify_code(
        phone,
        verify_code,
        case_auth_policy=case_auth_policy,
        scheme_name=params.get('scheme_name', ''),
        out_id=params.get('out_id', ''),
    )
    if not ok:
        return _fail_response(data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='核验完成')
