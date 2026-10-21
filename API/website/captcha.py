"""官网表单的图形验证（自研验证码）

设计要点：
1. **以服务端二次校验为准**：页面提交时把前端弹窗收集的参数随表单一起提交，由本模块校验。
   前端弹窗自身的校验结果只用于即时提示，不作为放行依据——否则攻击者跳过前端直接 POST
   即可绕过，等于没有防护。
2. **凭证一次性**：验证码用过即废，因此前端调用 `XYCaptchaSelf` 时必须传 `autoVerify: false`，
   由前端只负责收集参数、交本模块校验；若客户端先行校验会把凭证消费掉，
   导致服务端复验失败。
3. **随机类型**：官网登录 / 注册 / 发码 / 重置密码 / 反馈统一传 `kind: 'random'`，
   每次从字符、算术、滑块、汉字点选中随机抽一种。前端回传 `captcha_type` 与对应字段，
   本模块按类型路由到对应服务校验：
       char / arithmetic → captcha_id + answer
       slider           → slider_id + x + track
       click            → challenge_id + points
   未带 `captcha_type` 时按 char 处理（兼容旧缓存页面）。
4. **开关**：`.env` 设 `CAPTCHA_SELF_ENABLED=false` 可关闭（本地开发、自动化测试或验证码服务
   故障时临时关闭）；`enabled()` 是前后端唯一口径——前端据 `captcha_enabled` 决定是否弹窗，
   与这里是否校验始终一致。反馈中心另有自己的 `captcha_required` 开关，不走这里。

历史：本模块原先接入阿里云图形认证（4 个参数 lot_number / captcha_output / pass_token / gen_time）。
自研验证码上线后改由自研模块承担官网表单的防护；阿里云线路仍作为 API 服务保留在
`/api/captcha_auth/aliyun/`（`.env` 的 CAPTCHA_APP_ID / CAPTCHA_APP_KEY 仅供该服务使用）。
"""
import logging
import os

from django.utils.translation import gettext as _

from API.apis.captcha_self import click_word as captcha_click
from API.apis.captcha_self import slider as captcha_slider
from API.apis.captcha_self import utils as captcha_self_utils
from API.common import StatusCode

logger = logging.getLogger(__name__)

#: 文本类（同一张表、同一个校验函数）
TEXT_TYPES = ('char', 'arithmetic')
#: 全部支持的验证码类型
CAPTCHA_TYPES = TEXT_TYPES + ('slider', 'click')

# 开关：默认启用；设 false 时跳过校验（前后端同口径）
_SELF_ENABLED = os.getenv('CAPTCHA_SELF_ENABLED', 'true').lower() in ('true', '1', 'yes')


def enabled():
    """图形验证是否启用（默认启用，`CAPTCHA_SELF_ENABLED=false` 关闭）"""
    if _SELF_ENABLED:
        return True
    logger.warning('CAPTCHA_SELF_ENABLED=false，登录、注册与发送验证码将跳过图形验证')
    return False


def check_params(params):
    """按 `captcha_type` 路由校验表单里的验证码参数

    :param params: `request.POST` 或任意字典
    :return: (ok, reason, detail)
        ok      是否通过
        reason  'missing'（参数不全）/ 'invalid_type'（类型非法）/ 'failed'（校验未通过）
        detail  可直接展示给用户的失败原因
    """
    kind = (params.get('captcha_type') or 'char').strip().lower()
    if kind not in CAPTCHA_TYPES:
        return False, 'invalid_type', _('图形验证类型无效，请重新验证')

    if kind in TEXT_TYPES:
        captcha_id = (params.get('captcha_id') or '').strip()
        answer = (params.get('answer') or '').strip()
        if not captcha_id or not answer:
            return False, 'missing', _('请先完成图形验证')
        ok, detail = captcha_self_utils.verify_challenge(captcha_id, answer, kind=kind)
        return (True, '', '') if ok else (False, 'failed', detail or _('图形验证未通过，请重新验证'))

    if kind == 'slider':
        slider_id = (params.get('slider_id') or '').strip()
        x = (params.get('x') or '').strip()
        track = params.get('track') or ''
        if not slider_id or not x or not track:
            return False, 'missing', _('请先完成图形验证')
        ok, detail = captcha_slider.verify_challenge(slider_id, x, track)
        return (True, '', '') if ok else (False, 'failed', detail or _('图形验证未通过，请重新验证'))

    challenge_id = (params.get('challenge_id') or '').strip()
    points = params.get('points') or ''
    if not challenge_id or not points:
        return False, 'missing', _('请先完成图形验证')
    ok, detail = captcha_click.verify_challenge(challenge_id, points)
    return (True, '', '') if ok else (False, 'failed', detail or _('图形验证未通过，请重新验证'))


def verify(request):
    """校验本次请求携带的图形验证参数

    :return: (True, None) 校验通过或未启用；
             (False, (状态码, 提示语)) 未通过（参数缺失 / 校验失败）
    """
    if not enabled():
        return True, None

    ok, reason, detail = check_params(request.POST)
    if ok:
        return True, None

    # 具体原因（答案错误 / 已过期 / 已使用 / 轨迹异常）只记日志，对外统一提示，避免成为探测口
    logger.info('图形验证未通过（%s）: %s', reason, detail)
    if reason in ('missing', 'invalid_type'):
        return False, (StatusCode.PARAM_MISSING, _('请先完成图形验证'))
    return False, (StatusCode.PARAM_VALUE_INVALID, _('图形验证未通过，请重新验证'))
