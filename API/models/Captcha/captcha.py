"""自研图形验证码数据模型

    CaptchaChallenge - 验证码挑战记录（一图一条，一次性消费）

字段说明:
    id          - 验证码ID（UUID 主键，作为 captcha_id 下发给客户端）
    answer      - 标准答案（明文，短有效期 + 一次性，校验依据）
    kind        - 类型（char=字符图片 / arithmetic=算术）
    expire_time - 过期时间（超过即作废）
    used        - 是否已使用（一次性：校验一次即置为已用，防同一张图被反复尝试）

图片本身不落库：生成时即时返回 base64，服务端只保存答案与有效期；
过期记录由生成接口惰性清理，无需定时任务。
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class CaptchaChallenge(BaseModel):
    """验证码挑战记录"""

    KIND_CHAR = 'char'
    KIND_ARITHMETIC = 'arithmetic'
    KIND_CHOICES = [
        (KIND_CHAR, '字符图片'),
        (KIND_ARITHMETIC, '算术'),
    ]

    id = models.UUIDField('验证码ID', primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.CharField('标准答案', max_length=16,
                              help_text='校验依据；短有效期 + 一次性消费')
    kind = models.CharField('类型', max_length=12, choices=KIND_CHOICES, default=KIND_CHAR,
                            help_text='char=字符图片 / arithmetic=算术')
    expire_time = models.DateTimeField('过期时间', db_index=True,
                                       help_text='超过该时间即作废，需重新获取')
    used = models.BooleanField('已使用', default=False,
                               help_text='一次性：校验一次即置为已用，防同一张图被反复尝试')

    class Meta:
        db_table = 'captcha_challenge'
        verbose_name = '图形验证码'
        verbose_name_plural = '图形验证码'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.get_kind_display()} {self.id}（{self.expire_time:%Y-%m-%d %H:%M:%S} 过期）'
