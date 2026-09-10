"""官网表单的图形验证（阿里云图形认证）接入

设计要点：
1. **以服务端二次校验为准**：页面提交时把客户端验证通过后拿到的四个参数
   （lot_number / captcha_output / pass_token / gen_time）一并提交，由本模块调用阿里云
   二次校验接口确认有效性。前端的校验回调只用于即时提示，不作为放行依据——否则攻击者
   跳过前端直接 POST 即可绕过，等于没有防护。
2. **凭证一次性**：阿里云二次校验凭证只能消费一次，因此前端调用 XYCaptcha 时必须传
   `autoVerify: false`，避免客户端先校验把凭证用掉、导致服务端复验失败。
3. **密钥缺失时跳过**：`.env` 未配置 CAPTCHA_APP_ID / CAPTCHA_APP_KEY 时（新环境漏配很常见），
   跳过校验并记一条 warning，避免把所有人（含管理员）锁在门外。前端弹出与否也由同一处
   `enabled()` 决定，保证前后端口径一致。
"""
import logging

from django.utils.translation import gettext as _

from API.apis.captcha_auth.aliyun import utils as captcha_utils
from API.common import StatusCode

logger = logging.getLogger(__name__)

# 客户端验证通过后回调返回的四个参数（即阿里云二次校验接口的入参）
PARAM_NAMES = ('lot_number', 'captcha_output', 'pass_token', 'gen_time')

_missing_key_warned = False  # 密钥缺失只提醒一次，避免每次登录都刷日志


def enabled():
    """图形验证是否启用（appId / appKey 齐备即启用）"""
    global _missing_key_warned
    if captcha_utils.CAPTCHA_APP_ID and captcha_utils.CAPTCHA_APP_KEY:
        return True
    if not _missing_key_warned:
        _missing_key_warned = True
        logger.warning('未配置 CAPTCHA_APP_ID / CAPTCHA_APP_KEY，登录、注册与发送验证码将跳过图形验证')
    return False


def verify(request):
    """校验本次请求携带的图形验证参数

    :return: (True, None) 校验通过或未启用；
             (False, (状态码, 提示语)) 未通过（参数缺失 / 校验失败 / 外部服务异常）
    """
    if not enabled():
        return True, None

    params = request.POST.dict()
    if any(not (params.get(name) or '').strip() for name in PARAM_NAMES):
        return False, (StatusCode.PARAM_MISSING, _('请先完成图形验证'))

    ok, data = captcha_utils.verify_captcha(
        params['lot_number'].strip(),
        params['captcha_output'].strip(),
        params['pass_token'].strip(),
        params['gen_time'].strip(),
    )
    if not ok:
        # 阿里云二次校验接口本身异常（网络不通 / 参数非法 / 服务报错）：归为外部依赖失败
        logger.warning('图形验证二次校验调用失败: %s', data)
        return False, (StatusCode.EXTERNAL_API_FAILED, _('图形验证服务暂时不可用，请稍后重试'))
    if not data.get('passed'):
        logger.info('图形验证未通过: %s', data.get('reason') or 'unknown')
        return False, (StatusCode.PARAM_VALUE_INVALID, _('图形验证未通过，请重新验证'))
    return True, None
