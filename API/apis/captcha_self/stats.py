"""自研验证码 - 统计埋点

埋点位置刻意放在**服务层**（`utils` / `slider` / `click_word`）而不是接口视图：
官网登录、注册、发码与反馈表单是直接调用服务层校验的，不走 `/api/captcha_self/*`；
埋点放服务层，接口调用与官网表单才会进同一本账。

写入规则：
- 按「天 + 线路」一行，`F()` 原子累加，并发安全；
- 首次写当天该线路时先试插入，撞唯一约束（并发首写）再改回累加；
- 统计是旁路能力：任何异常只记日志，**绝不影响验证码本身的生成与校验**。
"""
import logging

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from API.models.Captcha.stat import CaptchaStat

logger = logging.getLogger('captcha_self.stats')

#: 线路（与模型 choices 一致）
KINDS = tuple(kind for kind, _label in CaptchaStat.KIND_CHOICES)
#: 失败原因 → 模型字段
REASON_FIELDS = {
    'expired': 'fail_expired',
    'used': 'fail_used',
    'wrong': 'fail_wrong',
    'abnormal': 'fail_abnormal',
    'invalid': 'fail_invalid',
}
#: 失败原因展示顺序
REASON_ORDER = tuple(REASON_FIELDS)


def _bump(kind, **fields):
    """把若干计数累加到「今天 + 线路」这一行（失败只记日志）"""
    if kind not in KINDS:
        kind = CaptchaStat.KIND_CHAR
    day = timezone.localdate()
    increments = {name: F(name) + value for name, value in fields.items()}
    try:
        if CaptchaStat.objects.filter(day=day, kind=kind).update(**increments):
            return
        try:
            CaptchaStat.objects.create(day=day, kind=kind, **fields)
        except IntegrityError:
            # 并发首写：另一进程已插入该行，改为累加
            CaptchaStat.objects.filter(day=day, kind=kind).update(**increments)
    except Exception:
        logger.exception('验证码统计写入失败：kind=%s fields=%s', kind, fields)


def record_generated(kind):
    """记一次生成"""
    _bump(kind, generated=1)


def record_passed(kind):
    """记一次校验通过"""
    _bump(kind, passed=1)


def record_failed(kind, reason):
    """记一次业务失败（答案错 / 过期 / 已使用 / 轨迹异常 / 不存在）"""
    field = REASON_FIELDS.get(reason)
    if not field:
        field = 'fail_wrong'
    _bump(kind, failed=1, **{field: 1})


def record_blocked(kind):
    """记一次拦截（IP 限流 / 连续失败冷却）"""
    _bump(kind, blocked=1)
