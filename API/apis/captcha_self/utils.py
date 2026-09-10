"""自研图形验证码 - 业务封装

职责：
- create_challenge(): 调用 SpiderServices/Captcha 生成图片，落库一条一次性挑战记录
- verify_challenge(): 按 captcha_id 取记录并比对答案，无论对错都消费掉（一次性）
- 生成时惰性清理过期记录（项目无定时任务，靠调用顺带清理）

有效期可通过 .env 的 CAPTCHA_SELF_EXPIRE_SECONDS 调整（默认 300 秒）。
"""
import base64
import os
from datetime import timedelta

from django.utils import timezone
from dotenv import load_dotenv

from API.models.Captcha.captcha import CaptchaChallenge
from SpiderServices.Captcha import generator

load_dotenv()

# 验证码有效期（秒）
EXPIRE_SECONDS = int(os.getenv('CAPTCHA_SELF_EXPIRE_SECONDS', '300'))


def _to_data_uri(png_bytes):
    """PNG 字节 -> base64 data URI（前端可直接用于 <img src>）"""
    return 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')


def create_challenge(kind=CaptchaChallenge.KIND_CHAR, length=None):
    """生成一张验证码并落库

    :param kind: 验证码类型（char=字符图片 / arithmetic=算术）
    :param length: 字符验证码长度（4-6，越界自动收敛）；算术类型忽略该参数
    :return: dict  captcha_id / kind / image(base64 data URI) / expire_in(秒)
    """
    if kind == CaptchaChallenge.KIND_ARITHMETIC:
        png_bytes, answer = generator.new_arithmetic_captcha()
    else:
        png_bytes, answer = generator.new_char_captcha(length or generator.DEFAULT_LENGTH)

    # 惰性清理过期记录，避免表无限增长
    CaptchaChallenge.objects.filter(expire_time__lt=timezone.now()).delete()

    challenge = CaptchaChallenge.objects.create(
        answer=answer,
        kind=kind,
        expire_time=timezone.now() + timedelta(seconds=EXPIRE_SECONDS),
    )
    return {
        'captcha_id': str(challenge.id),
        'kind': kind,
        'image': _to_data_uri(png_bytes),
        'expire_in': EXPIRE_SECONDS,
    }


def verify_challenge(captcha_id, answer):
    """校验验证码答案（一次性消费）

    :param captcha_id: 验证码 ID（UUID 字符串，格式已由视图层校验）
    :param answer: 用户提交的答案
    :return: (success, data_or_msg) 二元组
        (True, '')           校验通过
        (False, err_msg)     未通过 / 不可用（不存在、已过期、已使用、答案错误）

    安全性：采用条件更新做原子消费——同一验证码的并发重复提交只有一次能成功，
    且无论对错都作废，防止同一张图被反复暴力尝试。
    """
    challenge = CaptchaChallenge.objects.filter(id=captcha_id).first()
    if challenge is None:
        return False, '验证码不存在或已失效，请重新获取'
    if challenge.expire_time < timezone.now():
        return False, '验证码已过期，请重新获取'

    consumed = CaptchaChallenge.objects.filter(id=challenge.id, used=False).update(used=True)
    if not consumed:
        return False, '验证码已被使用，请重新获取'

    if (answer or '').strip().upper() != challenge.answer.strip().upper():
        return False, '答案错误'
    return True, ''
