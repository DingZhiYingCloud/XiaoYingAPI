"""自研滑块验证码 - 业务封装

流程：
    1. 生成背景图 + 拼图块，缺口横坐标作为答案，只把答案的 HMAC 摘要落库；
    2. 下发背景图、拼图块、拼图块纵坐标与画布尺寸（**不返回横坐标**）；
    3. 校验时按用户提交的 x 在容差范围内枚举摘要比对（库中无明文），
       同时检查拖动轨迹（点数 / 时长 / 时间单调 / 终点一致），过滤脚本瞬移；
    4. 一次性消费：无论成功失败，同一 slider_id 只能校验一次。
"""
import base64
import json
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from API.models.Captcha.slider import SliderChallenge
from SpiderServices.Captcha import slider as slider_gen

from . import guard
from . import stats
from .config import env_int

# 滑块是「即时操作」，有效期比字符验证码短；默认 3 分钟，可用环境变量覆盖
EXPIRE_SECONDS = env_int('CAPTCHA_SELF_SLIDER_EXPIRE_SECONDS', 180)

# 容差来自生成引擎，保证前后端对「对齐」的理解一致
TOLERANCE = slider_gen.TOLERANCE

# 轨迹校验：太少的点或太快的时间都视为脚本行为
MIN_TRACK_POINTS = 5
# 前端做了采样节流（最多约 200 点），这里留足冗余，只防超大 payload
MAX_TRACK_POINTS = 2000
MIN_DURATION_MS = 200
MAX_DURATION_MS = 60_000
TRACK_END_TOLERANCE = 8

_ANSWER_SALT = 'captcha_self.slider.answer.v1'


def _to_data_uri(payload, mime):
    return f'data:{mime};base64,' + base64.b64encode(payload).decode('ascii')


def _digest(challenge_id, x):
    """缺口横坐标摘要：HMAC-SHA256(SECRET_KEY, '挑战ID:横坐标')"""
    return salted_hmac(_ANSWER_SALT, f'{challenge_id}:{int(x)}', algorithm='sha256').hexdigest()


def _parse_track(raw):
    """解析并校验拖动轨迹；不合法返回 None

    轨迹格式：[{"x": 12.3, "t": 0}, {"x": 30.1, "t": 48}, ...]
        x 为换算到画布坐标的横向位置，t 为相对按下时刻的毫秒数。
    """
    try:
        points = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return None
    if not isinstance(points, list) or not (MIN_TRACK_POINTS <= len(points) <= MAX_TRACK_POINTS):
        return None

    cleaned = []
    for point in points:
        if not isinstance(point, dict):
            return None
        try:
            x = float(point.get('x'))
            t = float(point.get('t'))
        except (TypeError, ValueError):
            return None
        if x < -10 or x > slider_gen.CANVAS_WIDTH + 10 or t < 0:
            return None
        cleaned.append((x, t))

    for index in range(len(cleaned) - 1):
        if cleaned[index + 1][1] < cleaned[index][1]:
            return None

    duration = cleaned[-1][1] - cleaned[0][1]
    if not MIN_DURATION_MS <= duration <= MAX_DURATION_MS:
        return None

    if max(p[0] for p in cleaned) - min(p[0] for p in cleaned) < 10:
        return None
    return cleaned


def create_challenge():
    """生成一张滑块验证码并落库

    :return: (data, answer_x) —— data 为下发前端的字段；answer_x 仅供调用方测试使用，不下发。
    """
    background, piece, answer_x, piece_y = slider_gen.new_slider_captcha()

    guard.cleanup_expired(SliderChallenge)

    challenge = SliderChallenge(
        piece_y=piece_y,
        expire_time=timezone.now() + timedelta(seconds=EXPIRE_SECONDS),
    )
    challenge.answer = _digest(challenge.id, answer_x)
    challenge.save(force_insert=True)
    stats.record_generated('slider')

    return {
        'slider_id': str(challenge.id),
        'background': _to_data_uri(background, 'image/jpeg'),
        'piece': _to_data_uri(piece, 'image/png'),
        'piece_y': piece_y,
        'piece_size': slider_gen.PIECE_SIZE,
        'width': slider_gen.CANVAS_WIDTH,
        'height': slider_gen.CANVAS_HEIGHT,
        'expire_in': EXPIRE_SECONDS,
    }, answer_x


def verify_challenge(slider_id, x, track):
    """校验滑块位置与拖动轨迹（一次性消费）

    :param slider_id: 生成接口返回的 slider_id
    :param x: 用户拖动后拼图块左边缘的画布横坐标
    :param track: 前端记录的轨迹 JSON 字符串
    :return: (success, msg)
    """
    try:
        uuid.UUID(str(slider_id))
    except (ValueError, TypeError, AttributeError):
        stats.record_failed('slider', 'invalid')
        return False, '滑块验证不存在或已失效，请重新获取'

    try:
        submitted_x = float(x)
    except (TypeError, ValueError):
        stats.record_failed('slider', 'abnormal')
        return False, '滑动位置无效，请重新拖动'

    challenge = SliderChallenge.objects.filter(id=slider_id).first()
    if challenge is None:
        stats.record_failed('slider', 'invalid')
        return False, '滑块验证不存在或已失效，请重新获取'
    if challenge.expire_time < timezone.now():
        stats.record_failed('slider', 'expired')
        return False, '滑块验证已过期，请重新获取'

    consumed = SliderChallenge.objects.filter(id=challenge.id, used=False).update(used=True)
    if not consumed:
        stats.record_failed('slider', 'used')
        return False, '滑块验证已被使用，请重新获取'

    points = _parse_track(track)
    if points is None:
        stats.record_failed('slider', 'abnormal')
        return False, '滑动轨迹异常，请重新拖动'
    if abs(points[-1][0] - submitted_x) > TRACK_END_TOLERANCE:
        stats.record_failed('slider', 'abnormal')
        return False, '滑动轨迹与提交位置不一致，请重新拖动'

    target = round(submitted_x)
    for candidate in range(target - TOLERANCE, target + TOLERANCE + 1):
        if constant_time_compare(_digest(challenge.id, candidate), challenge.answer):
            stats.record_passed('slider')
            return True, ''
    stats.record_failed('slider', 'wrong')
    return False, '拼图未对齐，请重试'
