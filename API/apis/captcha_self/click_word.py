"""自研汉字点选验证码 - 业务封装

流程：
    1. 生成包含 8 个候选汉字的图片，随机抽 2-4 个作为目标（顺序随机）；
    2. 只把「目标字文本 + 图片」下发给前端，目标坐标只落库；
    3. 用户按提示依次点击，前端按顺序回传点击点（画布坐标 + 相对毫秒）；
    4. 服务端校验点数、点击时长与每个点是否命中对应目标字的命中圆；
    5. 一次性消费：无论成功失败，同一 challenge_id 只能校验一次。
"""
import base64
import json
import uuid
from datetime import timedelta

from django.utils import timezone

from API.models.Captcha.click_word import ClickWordChallenge
from SpiderServices.Captcha import click_word as word_gen

from . import guard
from . import stats
from .config import env_int

# 点选是即时操作，有效期比字符验证码短；默认 3 分钟，可用环境变量覆盖
EXPIRE_SECONDS = env_int('CAPTCHA_SELF_CLICK_EXPIRE_SECONDS', 180)

# 点击总时长下限（毫秒）：脚本瞬点会低于这个值
MIN_TOTAL_DURATION_MS = 300
MAX_POINTS = 10


def create_challenge():
    """生成一张汉字点选验证码并落库

    :return: (data, targets) —— data 为下发前端的字段；targets 含坐标，仅供调用方测试使用。
    """
    png_bytes, targets = word_gen.new_click_word_captcha()

    guard.cleanup_expired(ClickWordChallenge)

    challenge = ClickWordChallenge(
        targets=targets,
        expire_time=timezone.now() + timedelta(seconds=EXPIRE_SECONDS),
    )
    challenge.save(force_insert=True)
    stats.record_generated('click')

    return {
        'challenge_id': str(challenge.id),
        'image': 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii'),
        'chars': [target['char'] for target in targets],
        'count': len(targets),
        'width': word_gen.CANVAS_WIDTH,
        'height': word_gen.CANVAS_HEIGHT,
        'expire_in': EXPIRE_SECONDS,
    }, targets


def _parse_points(raw):
    """解析点击点；不合法返回 None

    格式：[{"x": 120.5, "y": 66.0, "t": 320}, …]（t 为相对首次点击的毫秒数）
    """
    try:
        points = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return None
    if not isinstance(points, list) or not (1 <= len(points) <= MAX_POINTS):
        return None

    cleaned = []
    last_t = None
    for point in points:
        if not isinstance(point, dict):
            return None
        try:
            x = float(point.get('x'))
            y = float(point.get('y'))
            t = float(point.get('t'))
        except (TypeError, ValueError):
            return None
        if not (0 <= x <= word_gen.CANVAS_WIDTH and 0 <= y <= word_gen.CANVAS_HEIGHT):
            return None
        if t < 0 or (last_t is not None and t < last_t):
            return None
        last_t = t
        cleaned.append({'x': x, 'y': y, 't': t})
    return cleaned


def verify_challenge(challenge_id, points_raw):
    """校验点选顺序与位置（一次性消费）

    :return: (success, msg)
    """
    try:
        uuid.UUID(str(challenge_id))
    except (ValueError, TypeError, AttributeError):
        stats.record_failed('click', 'invalid')
        return False, '验证码不存在或已失效，请重新获取'

    challenge = ClickWordChallenge.objects.filter(id=challenge_id).first()
    if challenge is None:
        stats.record_failed('click', 'invalid')
        return False, '验证码不存在或已失效，请重新获取'
    if challenge.expire_time < timezone.now():
        stats.record_failed('click', 'expired')
        return False, '验证码已过期，请重新获取'

    consumed = ClickWordChallenge.objects.filter(id=challenge.id, used=False).update(used=True)
    if not consumed:
        stats.record_failed('click', 'used')
        return False, '验证码已被使用，请重新获取'

    points = _parse_points(points_raw)
    if points is None:
        stats.record_failed('click', 'abnormal')
        return False, '点击轨迹异常，请重新验证'

    targets = challenge.targets or []
    if len(points) != len(targets):
        stats.record_failed('click', 'abnormal')
        return False, f'请依次点击 {len(targets)} 个字'

    duration = points[-1]['t'] - points[0]['t']
    if duration < MIN_TOTAL_DURATION_MS:
        stats.record_failed('click', 'abnormal')
        return False, '点击速度过快，请重新验证'

    for index, (point, target) in enumerate(zip(points, targets), start=1):
        distance = ((point['x'] - target['x']) ** 2 + (point['y'] - target['y']) ** 2) ** 0.5
        if distance > target['r']:
            stats.record_failed('click', 'wrong')
            return False, f'第 {index} 个点击位置未命中目标字'

    stats.record_passed('click')
    return True, ''
