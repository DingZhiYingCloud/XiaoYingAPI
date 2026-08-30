"""阿里云图形认证集成 API 视图

接口清单：
    GET  /api/captcha_auth/aliyun/config  获取图形认证配置（appId，公开，供 H5 前端 SDK 初始化）
    POST /api/captcha_auth/aliyun/verify  二次校验（确认用户在客户端完成的图形验证有效）

鉴权: 当前接口开放调用（不做签名校验）；appKey 由服务端持有，
      仅用于生成 sign_token，绝不下发客户端。
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


@require_http_methods(['GET'])
def config_view(request):
    """获取图形认证配置：下发 appId 供 H5 前端初始化 SDK（captchaId）

    前端接入方式：
        const { app_id } = await fetch('/api/captcha_auth/aliyun/config').then(r => r.json());
        initAlicom4({ captchaId: app_id, product: 'bind' }, ...);
    """
    return _json_response(StatusCode.SUCCESS, data={'app_id': utils.CAPTCHA_APP_ID}, msg='获取成功')


@require_http_methods(['POST'])
def verify_view(request):
    """二次校验：上传客户端验证参数，确认用户本次图形验证的有效性

    表单参数：
        lot_number      (必填): 验证流水号（前端 SDK 验证通过后回调返回）
        captcha_output  (必填): 验证输出信息
        pass_token      (必填): 验证通过标识
        gen_time        (必填): 验证通过时间戳

    校验结果语义：接口请求成功即返回 code=10000，业务结果以 data.result 为准：
        success=验证有效 / fail=验证无效（如 pass_token 过期、流水号已用等），
        具体原因见 data.reason。仅当阿里云二次校验接口本身异常时才返回 40001。
    """
    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})

    required = ['lot_number', 'captcha_output', 'pass_token', 'gen_time']
    missing = [k for k in required if not (params.get(k) or '').strip()]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING,
                              msg=f'参数缺失: {", ".join(missing)}')

    lot_number = params['lot_number'].strip()
    captcha_output = params['captcha_output'].strip()
    pass_token = params['pass_token'].strip()
    gen_time = params['gen_time'].strip()

    # 流水号基础校验：阿里云流水号为 32 位小写 hex（如 4dc3cfc2cdff448cad8d13107198d473）
    if not (len(lot_number) == 32 and lot_number.isalnum()):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR,
                              msg='参数格式错误: lot_number 必须为 32 位验证流水号')

    ok, data = utils.verify_captcha(lot_number, captcha_output, pass_token, gen_time)
    if not ok:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data, msg='校验完成')
