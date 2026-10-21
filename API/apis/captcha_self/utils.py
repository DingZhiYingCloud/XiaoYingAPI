"""自研图形验证码 - 业务封装

职责：
- create_challenge(): 调用 SpiderServices/Captcha 生成图片，落库一条一次性挑战记录
- verify_challenge(): 按 captcha_id 取记录并比对答案，无论对错都消费掉（一次性）
- 生成时惰性清理过期记录（项目无定时任务，靠调用顺带清理）

安全说明：
    数据库只存答案的 HMAC-SHA256 摘要（密钥由 SECRET_KEY 派生），**不落明文**；
    即使库文件 / 备份被读走，也拿不到尚未使用的验证码答案。摘要绑定 captcha_id，
    同一答案在不同挑战里的摘要不同。SECRET_KEY 变更会让所有未使用验证码失效（短有效期，可接受）。

有效期可通过 .env 的 CAPTCHA_SELF_EXPIRE_SECONDS 调整（默认 300 秒）。
"""
import base64
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from dotenv import load_dotenv

from API.models.Captcha.captcha import CaptchaChallenge
from SpiderServices.Captcha import generator

from . import guard
from . import stats
from .config import env_int

load_dotenv()

# 生成答案摘要用的盐；改了它等价于让所有旧验证码立即失效
_ANSWER_SALT = 'captcha_self.answer.v1'

EXPIRE_SECONDS = env_int('CAPTCHA_SELF_EXPIRE_SECONDS', 300)


def _to_data_uri(png_bytes):
    """PNG 字节 -> base64 data URI（前端可直接用于 <img src>）"""
    return 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')


def _normalize_answer(answer):
    """答案归一：去首尾空白 + 统一大写（字符验证码不区分大小写）"""
    return (answer or '').strip().upper()


def _answer_digest(challenge_id, answer):
    """答案摘要：HMAC-SHA256(SECRET_KEY, '挑战ID:归一化答案')

    绑定挑战 ID，避免同一答案在不同验证码里产生相同摘要；输出为 64 位十六进制文本。
    """
    payload = f'{challenge_id}:{_normalize_answer(answer)}'
    return salted_hmac(_ANSWER_SALT, payload, algorithm='sha256').hexdigest()


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
    guard.cleanup_expired(CaptchaChallenge)

    # 先实例化拿到 UUID 主键，再用它给答案做摘要（主键在模型实例化时已生成）
    challenge = CaptchaChallenge(
        kind=kind,
        expire_time=timezone.now() + timedelta(seconds=EXPIRE_SECONDS),
    )
    challenge.answer = _answer_digest(challenge.id, answer)
    challenge.save(force_insert=True)
    stats.record_generated(kind)
    return {
        'captcha_id': str(challenge.id),
        'kind': kind,
        'image': _to_data_uri(png_bytes),
        'expire_in': EXPIRE_SECONDS,
    }


def verify_challenge(captcha_id, answer, kind=None):
    """校验验证码答案（一次性消费）

    :param captcha_id: 验证码 ID；**格式非法按「不存在」处理**——本函数有多个调用方
                       （开放接口 / 官网表单），不能因为客户端传入非 UUID 字符串就让
                       ORM 抛 ValidationError（那会变成 500）
    :param answer: 用户提交的答案
    :param kind: 调用方声明的类型（char / arithmetic），仅用于统计；记录存在时以库中类型为准
    :return: (success, data_or_msg) 二元组
        (True, '')           校验通过
        (False, err_msg)     未通过 / 不可用（不存在、已过期、已使用、答案错误）

    安全性：采用条件更新做原子消费——同一验证码的并发重复提交只有一次能成功，
    且无论对错都作废，防止同一张图被反复暴力尝试；答案用恒定时间比较。
    """
    fallback_kind = kind if kind in stats.KINDS else CaptchaChallenge.KIND_CHAR
    try:
        uuid.UUID(str(captcha_id))
    except (ValueError, TypeError, AttributeError):
        stats.record_failed(fallback_kind, 'invalid')
        return False, '验证码不存在或已失效，请重新获取'

    challenge = CaptchaChallenge.objects.filter(id=captcha_id).first()
    if challenge is None:
        stats.record_failed(fallback_kind, 'invalid')
        return False, '验证码不存在或已失效，请重新获取'
    if challenge.expire_time < timezone.now():
        stats.record_failed(challenge.kind, 'expired')
        return False, '验证码已过期，请重新获取'

    consumed = CaptchaChallenge.objects.filter(id=challenge.id, used=False).update(used=True)
    if not consumed:
        stats.record_failed(challenge.kind, 'used')
        return False, '验证码已被使用，请重新获取'

    if not constant_time_compare(_answer_digest(challenge.id, answer), challenge.answer):
        stats.record_failed(challenge.kind, 'wrong')
        return False, '答案错误'
    stats.record_passed(challenge.kind)
    return True, ''
