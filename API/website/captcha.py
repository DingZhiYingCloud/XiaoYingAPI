"""官网表单的图形验证（自研验证码）

设计要点：
1. **以服务端二次校验为准**：页面提交时把用户填写的验证码参数（`captcha_id` + `answer`）
   随表单一起提交，由本模块调用自研验证码服务校验。前端弹窗自身的校验结果只用于即时提示，
   不作为放行依据——否则攻击者跳过前端直接 POST 即可绕过，等于没有防护。
2. **凭证一次性**：验证码用过即废，因此前端调用 `XYCaptchaSelf` 时必须传 `autoVerify: false`，
   由前端只负责收集 `captcha_id` + `answer`、交本模块校验；若客户端先行校验会把凭证消费掉，
   导致服务端复验失败。
3. **开关**：`.env` 设 `CAPTCHA_SELF_ENABLED=false` 可关闭（本地开发、自动化测试或验证码服务
   故障时临时关闭）；`enabled()` 是前后端唯一口径——前端据 `captcha_enabled` 决定是否弹窗，
   与这里是否校验始终一致。

历史：本模块原先接入阿里云图形认证（4 个参数 lot_number / captcha_output / pass_token / gen_time）。
自研验证码上线后改由自研模块承担官网表单的防护；阿里云线路仍作为 API 服务保留在
`/api/captcha_auth/aliyun/`（`.env` 的 CAPTCHA_APP_ID / CAPTCHA_APP_KEY 仅供该服务使用）。
"""
import logging
import os

from django.utils.translation import gettext as _

from API.apis.captcha_self import utils as captcha_self_utils
from API.common import StatusCode

logger = logging.getLogger(__name__)

# 前端弹窗收集、随表单一并提交的两个参数（即自研验证码 generate 返回的 captcha_id 与用户答案）
PARAM_NAMES = ('captcha_id', 'answer')

# 开关：默认启用；设 false 时跳过校验（前后端同口径）
_SELF_ENABLED = os.getenv('CAPTCHA_SELF_ENABLED', 'true').lower() in ('true', '1', 'yes')


def enabled():
    """图形验证是否启用（默认启用，`CAPTCHA_SELF_ENABLED=false` 关闭）"""
    if _SELF_ENABLED:
        return True
    logger.warning('CAPTCHA_SELF_ENABLED=false，登录、注册与发送验证码将跳过图形验证')
    return False


def verify(request):
    """校验本次请求携带的图形验证参数

    :return: (True, None) 校验通过或未启用；
             (False, (状态码, 提示语)) 未通过（参数缺失 / 校验失败）
    """
    if not enabled():
        return True, None

    params = request.POST.dict()
    if any(not (params.get(name) or '').strip() for name in PARAM_NAMES):
        return False, (StatusCode.PARAM_MISSING, _('请先完成图形验证'))

    ok, err = captcha_self_utils.verify_challenge(
        params['captcha_id'].strip(), params['answer'].strip())
    if not ok:
        # 具体原因（答案错误 / 已过期 / 已使用 / 不存在）只记日志，对外统一提示，避免成为探测口
        logger.info('图形验证未通过: %s', err)
        return False, (StatusCode.PARAM_VALUE_INVALID, _('图形验证未通过，请重新验证'))
    return True, None
