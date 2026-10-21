"""自研滑块验证码数据模型

    SliderChallenge - 滑块挑战记录（一次一条，一次性消费）

字段说明:
    id          - 挑战ID（UUID 主键，作为 slider_id 下发给客户端）
    answer      - 缺口横坐标的 HMAC-SHA256 摘要（不存明文；校验时在容差范围内枚举比对）
    piece_y     - 拼图块纵向位置（下发前端用于定位拼图块；横坐标才是答案）
    expire_time - 过期时间（超过即作废）
    used        - 是否已使用（一次性：校验一次即置为已用）

背景图与拼图块都不落库：生成时即时返回 base64，服务端只保存答案摘要与有效期；
过期记录由生成接口惰性清理，无需定时任务。
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class SliderChallenge(BaseModel):
    """滑块挑战记录"""

    id = models.UUIDField('滑块ID', primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.CharField('答案摘要', max_length=64,
                              help_text='缺口横坐标的 HMAC-SHA256 摘要（不落明文）')
    piece_y = models.PositiveSmallIntegerField('拼图块纵坐标',
                                               help_text='缺口顶边的 y 像素；横坐标才是答案')
    expire_time = models.DateTimeField('过期时间', db_index=True,
                                       help_text='超过该时间即作废，需重新获取')
    used = models.BooleanField('已使用', default=False,
                               help_text='一次性：校验一次即置为已用')

    class Meta:
        db_table = 'captcha_slider_challenge'
        verbose_name = '滑块验证码'
        verbose_name_plural = '滑块验证码'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.id}（{self.expire_time:%Y-%m-%d %H:%M:%S} 过期）'
