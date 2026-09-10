"""自研图形验证码 API 视图

接口清单：
    GET  /api/captcha_self/generate  生成验证码（返回 captcha_id + base64 图片）
    POST /api/captcha_self/verify    校验验证码（一次性，校验后立即失效）

鉴权: 分类树将该服务配置为开放（open），无需项目签名——与阿里云图形认证一致，
      便于任意接入方在登录/注册/提交等表单前直接调用。
"""
import uuid

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.models.Captcha.captcha import CaptchaChallenge
from SpiderServices.Captcha import generator

from . import utils

# 支持的验证码类型（唯一来源：模型 choices，避免多处硬编码）
VALID_KINDS = tuple(value for value, _label in CaptchaChallenge.KIND_CHOICES)


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


@require_http_methods(['GET'])
def generate_view(request):
    """生成验证码

    query 参数：
        kind   (选填): 类型，char=字符图片（默认）/ arithmetic=算术
        length (选填): 字符个数，仅 kind=char 生效，取值 4-6（默认 4）

    返回 data = {captcha_id, kind, image, expire_in}：
        captcha_id 校验时必须回传；image 为 base64 data URI，可直接用于 <img src>；
        expire_in 为有效期（秒）。
    """
    kind = (request.GET.get('kind') or CaptchaChallenge.KIND_CHAR).strip()
    if kind not in VALID_KINDS:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: kind 仅支持 {"/".join(VALID_KINDS)}')

    length = None
    raw_length = (request.GET.get('length') or '').strip()
    if raw_length:
        if not raw_length.isdigit():
            return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: length 必须为正整数')
        length = int(raw_length)
        if not generator.MIN_LENGTH <= length <= generator.MAX_LENGTH:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg=f'参数值非法: length 取值范围 {generator.MIN_LENGTH}-{generator.MAX_LENGTH}')

    return _json_response(StatusCode.SUCCESS, data=utils.create_challenge(kind, length), msg='生成成功')


@require_http_methods(['POST'])
def verify_view(request):
    """校验验证码（一次性，校验后立即失效）

    表单参数：
        captcha_id (必填): 生成接口返回的验证码 ID
        answer     (必填): 用户填写的答案（字符不区分大小写）

    结果语义：校验通过返回 code=10000 且 data.passed=true；未通过（答案错误 / 已过期 /
    已使用 / 不存在）返回 code=20003 且 data.passed=false，原因见 msg。
    """
    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})

    captcha_id = (params.get('captcha_id') or '').strip()
    answer = (params.get('answer') or '').strip()
    missing = [name for name, value in (('captcha_id', captcha_id), ('answer', answer)) if not value]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, data={'passed': False},
                              msg=f'参数缺失: {", ".join(missing)}')

    try:
        uuid.UUID(captcha_id)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, data={'passed': False},
                              msg='参数格式错误: captcha_id 必须为 UUID')

    ok, result = utils.verify_challenge(captcha_id, answer)
    if not ok:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, data={'passed': False}, msg=result)
    return _json_response(StatusCode.SUCCESS, data={'passed': True}, msg='校验通过')
