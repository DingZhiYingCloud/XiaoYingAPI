"""QQBot 好友私聊消息（事件上报落库 + 后台回复记录）

好友发给机器人的**私聊**消息（OneBot `message` 事件，`message_type=private`）由 NapCat 的
HTTP 客户端 POST 到 `/hook/qqbot/<密钥>/`，落到本表（`direction=in`）；管理员在控制台
「QQBot」页的「好友消息」里回复时，发出的内容也记一条（`direction=out`），
于是这一张表就是完整的双向对话记录，面板按主键增量拉取（`id > cursor`）实现实时展示。

为什么收到的消息必须靠事件上报：OneBot **没有**「拉取新消息 / 查历史消息」的接口，消息只能由
NapCat 主动推。所以只统计「启用上报之后」收到的消息。

只落私聊（含好友/临时会话），**不落群消息**：群消息量大、且本功能只关心「谁私聊了机器人」。
"""
from django.db import models

from API.common.base import BaseModel


class QQPrivateMessage(BaseModel):
    """一条好友私聊消息（收到 / 后台回复发出）"""

    class Direction(models.TextChoices):
        IN = 'in', '收到'
        OUT = 'out', '发出'

    message_id = models.CharField(
        '上游消息ID', max_length=64, blank=True, default='', db_index=True,
        help_text='OneBot 的 message_id，用于幂等（上游重推同一条时不再入库）')
    user_id = models.CharField('好友 QQ 号', max_length=20, db_index=True)
    nickname = models.CharField('好友昵称', max_length=100, blank=True, default='')
    content = models.TextField('消息内容', blank=True, default='',
                               help_text='消息段拍平后的可读文本（非文本段以 [图片]/[语音] 等占位）')
    sub_type = models.CharField('会话类型', max_length=16, blank=True, default='',
                                help_text='OneBot 的 sub_type，如 friend / group / other')
    direction = models.CharField('方向', max_length=8, default=Direction.IN, db_index=True,
                                 choices=Direction.choices,
                                 help_text='in=好友发来；out=管理员在后台回复发出')
    is_read = models.BooleanField('已读', default=False,
                                  help_text='仅「收到」有意义：打开该会话即置为已读（用于未读红点）')
    is_starred = models.BooleanField('星标', default=False, db_index=True,
                                     help_text='手动标记，便于事后回看（不随已读变化）')
    is_greeting = models.BooleanField(
        '业务开场白', default=False,
        help_text='代练搬单给「刚加我们好友的打手」发的主动开场白（direction=out）；'
                  '据此把该 QQ 认作来交接的打手，后续私聊按客服口径引导')
    received_at = models.DateTimeField('消息时间', null=True, blank=True,
                                       help_text='事件里的时间戳；缺失则以入库时间为准')

    class Meta:
        db_table = 'qq_private_message'
        verbose_name = 'QQ私聊消息'
        verbose_name_plural = 'QQ私聊消息'
        ordering = ['id']                      # 自增即时间序；面板按 id 增量拉取
        indexes = [
            models.Index(fields=['user_id', 'id'], name='qq_priv_msg_user_idx'),
            models.Index(fields=['-id'], name='qq_priv_msg_id_idx'),
        ]

    def __str__(self):
        return f'[{self.get_direction_display()}] QQ {self.user_id}: {self.content[:30]}'
