"""自研汉字点选验证码数据模型

    ClickWordChallenge - 汉字点选挑战（一次一条，一次性消费）

字段说明:
    id          - 挑战ID（UUID 主键，作为 challenge_id 下发给客户端）
    targets     - 目标字及其中心坐标 / 命中半径（JSON，仅服务端使用，**不下发**）
    expire_time - 过期时间（超过即作废）
    used        - 是否已使用（一次性：校验一次即置为已用）

图片不落库：生成时即时返回 base64，服务端只保存目标坐标与有效期；
过期记录由生成接口惰性清理，无需定时任务。
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class ClickWordChallenge(BaseModel):
    """汉字点选挑战记录"""

    id = models.UUIDField('挑战ID', primary_key=True, default=uuid.uuid4, editable=False)
    targets = models.JSONField('目标字', default=list,
                               help_text='[{"char": "山", "x": 120, "y": 66, "r": 26}, …]，'
                                         '顺序即点击顺序；仅服务端校验用，不下发')
    expire_time = models.DateTimeField('过期时间', db_index=True,
                                       help_text='超过该时间即作废，需重新获取')
    used = models.BooleanField('已使用', default=False,
                               help_text='一次性：校验一次即置为已用')

    class Meta:
        db_table = 'captcha_click_word_challenge'
        verbose_name = '汉字点选验证码'
        verbose_name_plural = '汉字点选验证码'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.id}（{self.expire_time:%Y-%m-%d %H:%M:%S} 过期）'
