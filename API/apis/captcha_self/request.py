"""自研图形验证码 API 视图

四条线路：
    GET  /api/captcha_self/generate          字符 / 算术验证码
    POST /api/captcha_self/verify            字符 / 算术校验
    GET  /api/captcha_self/slider/generate   滑块验证码
    POST /api/captcha_self/slider/verify     滑块校验
    GET  /api/captcha_self/click/generate    汉字点选验证码
    POST /api/captcha_self/click/verify      汉字点选校验

鉴权: 服务策略将 /api/captcha_self/ 配置为开放（open），无需项目签名。

安全约束（统一由 API/apis/captcha_self/guard.py 提供）：
    - 按客户端 IP 固定窗口限流，防止匿名脚本反复生成图片或批量撞答案；
    - 连续失败 N 次后短时冷却，冷却期内连正确答案也会被拒；
    - 响应统一 no-store，避免 GET 生成的旧图被浏览器 / 代理缓存复用。
"""
import json
import uuid

from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from API.common import ratelimit as _rl
from API.common.ip_guard import client_ip
from API.common.responses import json_response as _json_response
from API.models.Captcha.behavior import BehaviorSample
from API.models.Captcha.captcha import CaptchaChallenge
from SpiderServices.Captcha import generator

from . import behavior
from . import click_word as click_word_service
from . import guard
from . import slider as slider_service
from . import stats
from . import utils

# 支持的验证码类型（唯一来源：模型 choices，避免多处硬编码）
VALID_KINDS = tuple(value for value, _label in CaptchaChallenge.KIND_CHOICES)

# 每 IP 每分钟的调用上限：正常用户一次表单交互只会调 1~3 次，这里留足余量
GENERATE_LIMIT = 60
VERIFY_LIMIT = 120

# 连续失败冷却：同一 IP 在 5 分钟内累计失败 20 次，冷却 10 分钟
FAIL_LIMIT = 20
FAIL_WINDOW = 300
BLOCK_SECONDS = 600

# 滑块 / 汉字点选：图片合成成本更高，生成限流收紧；猜位置空间有限，冷却阈值也收紧
SLIDER_GENERATE_LIMIT = 30
SLIDER_VERIFY_LIMIT = 60
SLIDER_FAIL_LIMIT = 10
SLIDER_FAIL_WINDOW = 300
SLIDER_BLOCK_SECONDS = 600

CLICK_GENERATE_LIMIT = 30
CLICK_VERIFY_LIMIT = 60
CLICK_FAIL_LIMIT = 10
CLICK_FAIL_WINDOW = 300
CLICK_BLOCK_SECONDS = 600

# 行为验证（影子模式）：每个页面提交上报一次，限流放宽；同一 IP 10 分钟内第 6 次起标记 ip_burst
BEHAVIOR_LIMIT = 120
BEHAVIOR_IP_WINDOW = 600
BEHAVIOR_IP_LIMIT = 5
BEHAVIOR_PAYLOAD_MAX = 8192


@require_http_methods(['POST'])
@guard.no_store
def behavior_view(request):
    """行为验证影子采集：只打分记录，不参与放行 / 拦截

    请求体二选一：
        application/json   {"scene": "login", "features": {...}}
        x-www-form-urlencoded  scene=login&features={...}

    返回 data = {score, band, hits, shadow: true}，前端可用于调试；
    任何情况下都不影响业务提交（影子模式，fail-open）。
    """
    if guard.rate_limited(request, 'behavior', BEHAVIOR_LIMIT):
        return _json_response(StatusCode.RATE_LIMITED, msg='请求过于频繁，请稍后重试')

    try:
        if (request.content_type or '').startswith('application/json'):
            payload = json.loads((request.body or b'{}').decode('utf-8'))
        else:
            form = request.POST.dict()
            payload = {
                'scene': form.get('scene'),
                'features': json.loads(form.get('features') or '{}'),
            }
    except (ValueError, UnicodeDecodeError):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: 请求体必须为 JSON')

    if not isinstance(payload, dict):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: 请求体必须为 JSON 对象')

    features = payload.get('features') or {}
    if not isinstance(features, dict):
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, msg='参数格式错误: features 必须为对象')
    if len(json.dumps(features, ensure_ascii=False)) > BEHAVIOR_PAYLOAD_MAX:
        return _json_response(StatusCode.PARAM_VALUE_INVALID,
                              msg=f'参数值非法: features 超过 {BEHAVIOR_PAYLOAD_MAX} 字节')

    scene = (payload.get('scene') or BehaviorSample.SCENE_OTHER).strip()
    valid_scenes = tuple(value for value, _label in BehaviorSample.SCENE_CHOICES)
    if scene not in valid_scenes:
        scene = BehaviorSample.SCENE_OTHER

    extra_hits = []
    try:
        ip_count = _rl.hit(f'captcha_self:behavior:ip:{client_ip(request)}', BEHAVIOR_IP_WINDOW)
        if ip_count > BEHAVIOR_IP_LIMIT:
            extra_hits.append('ip_burst')
    except Exception:
        # 缓存故障不影响采集（fail-open）
        pass

    score, band, hits = behavior.record(scene, features, extra_hits=extra_hits)
    return _json_response(
        StatusCode.SUCCESS,
        data={'score': score, 'band': band, 'hits': hits, 'shadow': True},
        msg='记录成功（影子模式，不影响放行）')


@require_http_methods(['GET'])
@guard.no_store
def generate_view(request):
    """生成验证码

    query 参数：
        kind   (选填): 类型，char=字符图片（默认）/ arithmetic=算术
        length (选填): 字符个数，仅 kind=char 生效，取值 4-6（默认 4）

    返回 data = {captcha_id, kind, image, expire_in}：
        captcha_id 校验时必须回传；image 为 base64 data URI，可直接用于 <img src>；
        expire_in 为有效期（秒）。
    """
    if guard.rate_limited(request, 'generate', GENERATE_LIMIT):
        kind = (request.GET.get('kind') or CaptchaChallenge.KIND_CHAR).strip()
        stats.record_blocked(kind if kind in VALID_KINDS else CaptchaChallenge.KIND_CHAR)
        return _json_response(StatusCode.RATE_LIMITED, msg='请求过于频繁，请稍后重试')

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
@guard.no_store
def verify_view(request):
    """校验验证码（一次性，校验后立即失效）

    表单参数：
        captcha_id (必填): 生成接口返回的验证码 ID
        answer     (必填): 用户填写的答案（字符不区分大小写）

    结果语义：校验通过返回 code=10000 且 data.passed=true；未通过（答案错误 / 已过期 /
    已使用 / 不存在）返回 code=20003 且 data.passed=false，原因见 msg。
    """
    if guard.rate_limited(request, 'verify', VERIFY_LIMIT):
        stats.record_blocked(CaptchaChallenge.KIND_CHAR)
        return _json_response(StatusCode.RATE_LIMITED, data={'passed': False},
                              msg='请求过于频繁，请稍后重试')

    fail_key, block_key = guard.fail_keys(request, 'verify')
    if guard.blocked(block_key):
        stats.record_blocked(CaptchaChallenge.KIND_CHAR)
        return guard.too_many_failures(BLOCK_SECONDS)

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
        if guard.record_failure(fail_key, block_key, FAIL_LIMIT, FAIL_WINDOW, BLOCK_SECONDS):
            stats.record_blocked(CaptchaChallenge.KIND_CHAR)
            return guard.too_many_failures(BLOCK_SECONDS)
        return _json_response(StatusCode.PARAM_VALUE_INVALID, data={'passed': False}, msg=result)

    guard.reset_failure(fail_key)
    return _json_response(StatusCode.SUCCESS, data={'passed': True}, msg='校验通过')


@require_http_methods(['GET'])
@guard.no_store
def slider_generate_view(request):
    """生成滑块验证码

    返回 data = {slider_id, background, piece, piece_y, piece_size, width, height, expire_in}：
        background 为 JPEG 背景图（data URI），piece 为带透明通道的拼图块（PNG data URI）；
        **缺口横坐标不在响应里**，必须由用户拖动拼图块去对齐。
    """
    if guard.rate_limited(request, 'slider_generate', SLIDER_GENERATE_LIMIT):
        stats.record_blocked('slider')
        return _json_response(StatusCode.RATE_LIMITED, msg='请求过于频繁，请稍后重试')

    data, _answer_x = slider_service.create_challenge()
    return _json_response(StatusCode.SUCCESS, data=data, msg='生成成功')


@require_http_methods(['POST'])
@guard.no_store
def slider_verify_view(request):
    """校验滑块位置与拖动轨迹（一次性消费）

    表单参数：
        slider_id (必填): 生成接口返回的滑块 ID
        x         (必填): 拼图块左边缘的画布横坐标
        track     (必填): 拖动轨迹 JSON，如 [{"x":0,"t":0},{"x":30,"t":120}, …]

    通过返回 code=10000 且 data.passed=true；未通过返回 code=20003，原因见 msg。
    """
    if guard.rate_limited(request, 'slider_verify', SLIDER_VERIFY_LIMIT):
        stats.record_blocked('slider')
        return _json_response(StatusCode.RATE_LIMITED, data={'passed': False},
                              msg='请求过于频繁，请稍后重试')

    fail_key, block_key = guard.fail_keys(request, 'slider')
    if guard.blocked(block_key):
        stats.record_blocked('slider')
        return guard.too_many_failures(SLIDER_BLOCK_SECONDS)

    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})

    slider_id = (params.get('slider_id') or '').strip()
    raw_x = (params.get('x') or '').strip()
    track = params.get('track') or ''
    missing = [name for name, value in
               (('slider_id', slider_id), ('x', raw_x), ('track', track)) if not value]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, data={'passed': False},
                              msg=f'参数缺失: {", ".join(missing)}')

    try:
        float(raw_x)
    except ValueError:
        return _json_response(StatusCode.PARAM_FORMAT_ERROR, data={'passed': False},
                              msg='参数格式错误: x 必须为数字')

    ok, result = slider_service.verify_challenge(slider_id, raw_x, track)
    if not ok:
        if guard.record_failure(fail_key, block_key,
                                SLIDER_FAIL_LIMIT, SLIDER_FAIL_WINDOW, SLIDER_BLOCK_SECONDS):
            stats.record_blocked('slider')
            return guard.too_many_failures(SLIDER_BLOCK_SECONDS)
        return _json_response(StatusCode.PARAM_VALUE_INVALID, data={'passed': False}, msg=result)

    guard.reset_failure(fail_key)
    return _json_response(StatusCode.SUCCESS, data={'passed': True}, msg='校验通过')


@require_http_methods(['GET'])
@guard.no_store
def click_generate_view(request):
    """生成汉字点选验证码

    返回 data = {challenge_id, image, chars, count, width, height, expire_in}：
        image 为 PNG data URI；chars 是**按顺序**需要点击的目标字；
        目标字的坐标不在响应里，服务端只落库用于命中判断。
    """
    if guard.rate_limited(request, 'click_generate', CLICK_GENERATE_LIMIT):
        stats.record_blocked('click')
        return _json_response(StatusCode.RATE_LIMITED, msg='请求过于频繁，请稍后重试')

    data, _targets = click_word_service.create_challenge()
    return _json_response(StatusCode.SUCCESS, data=data, msg='生成成功')


@require_http_methods(['POST'])
@guard.no_store
def click_verify_view(request):
    """校验汉字点选顺序与位置（一次性消费）

    表单参数：
        challenge_id (必填): 生成接口返回的挑战 ID
        points       (必填): 点击点 JSON，如
                             [{"x":120,"y":66,"t":0},{"x":210,"y":80,"t":520}]

    通过返回 code=10000 且 data.passed=true；未通过返回 code=20003，原因见 msg。
    """
    if guard.rate_limited(request, 'click_verify', CLICK_VERIFY_LIMIT):
        stats.record_blocked('click')
        return _json_response(StatusCode.RATE_LIMITED, data={'passed': False},
                              msg='请求过于频繁，请稍后重试')

    fail_key, block_key = guard.fail_keys(request, 'click')
    if guard.blocked(block_key):
        stats.record_blocked('click')
        return guard.too_many_failures(CLICK_BLOCK_SECONDS)

    params = request.POST.dict()
    params.update({k: v for k, v in request.GET.items() if k not in params})

    challenge_id = (params.get('challenge_id') or '').strip()
    points = params.get('points') or ''
    missing = [name for name, value in
               (('challenge_id', challenge_id), ('points', points)) if not value]
    if missing:
        return _json_response(StatusCode.PARAM_MISSING, data={'passed': False},
                              msg=f'参数缺失: {", ".join(missing)}')

    ok, result = click_word_service.verify_challenge(challenge_id, points)
    if not ok:
        if guard.record_failure(fail_key, block_key,
                                CLICK_FAIL_LIMIT, CLICK_FAIL_WINDOW, CLICK_BLOCK_SECONDS):
            stats.record_blocked('click')
            return guard.too_many_failures(CLICK_BLOCK_SECONDS)
        return _json_response(StatusCode.PARAM_VALUE_INVALID, data={'passed': False}, msg=result)

    guard.reset_failure(fail_key)
    return _json_response(StatusCode.SUCCESS, data={'passed': True}, msg='校验通过')
