"""IP 封禁（人工封禁 / 解禁，默认 7 天，到期自动失效）

**为什么单开一张表**：封禁对象是「IP」而不是「账号」—— 请求还没到认证那一步就已经能命中
（此时可能根本没有账号），所以要有一张不依赖 `User` 的封禁表；并且要带**原因**、**到期时间**
与操作留痕，既给被封的访客看，也给管理员复核用。

**「生效中」的判定**：`is_active=True` 且（`expire_time` 为空 = 永久，或 `expire_time > now`）。
同一个 IP 允许存在多条记录（解禁之后再封会新增一条，保留完整历史），因此判定口径是
「是否存在任一生效记录」，而不是「最后一条」。

与 `User.status`（账号封禁）是两回事：那是账号维度的布尔开关，这里是 IP 维度、带期限与原因。
"""
import uuid

from django.db import models
from django.utils import timezone

from API.common.base import BaseModel


class BannedIP(BaseModel):
    """被封禁的 IP（一条记录 = 一次封禁）"""

    id = models.UUIDField('记录ID', primary_key=True, default=uuid.uuid4, editable=False)
    ip = models.CharField('IP 地址', max_length=45, db_index=True,
                          help_text='被封禁的客户端 IP（兼容 IPv4 / IPv6）')
    reason = models.CharField('封禁原因', max_length=255,
                              help_text='必填；会展示给被封禁的访客与管理员，便于申诉与复核')
    expire_time = models.DateTimeField('封禁到期', null=True, blank=True, db_index=True,
                                       help_text='到期后自动失效；留空表示永久封禁')
    is_active = models.BooleanField('封禁中', default=True, db_index=True,
                                    help_text='手动解禁会置为 False；与「是否到期」无关')
    operator = models.CharField('操作人', max_length=64, blank=True, default='',
                                help_text='发起封禁的控制台账号')
    unbanned_at = models.DateTimeField('解禁时间', null=True, blank=True)
    unban_note = models.CharField('解禁备注', max_length=255, blank=True, default='')

    class Meta:
        db_table = 'banned_ip'
        verbose_name = 'IP 封禁'
        verbose_name_plural = 'IP 封禁'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['ip', 'is_active'], name='idx_banned_ip_active'),
            models.Index(fields=['expire_time'], name='idx_banned_ip_expire'),
        ]

    def __str__(self):
        return f'{self.ip}（{self.status_key}）'

    @property
    def is_expired(self) -> bool:
        """是否已到期（未设到期时间 = 永久，永远不算到期）"""
        return self.expire_time is not None and self.expire_time <= timezone.now()

    @property
    def is_effective(self) -> bool:
        """当前是否真的在拦截：未手动解禁 且 未到期"""
        return self.is_active and not self.is_expired

    @property
    def status_key(self) -> str:
        """状态键（模板据此上色 / 译名）：active 封禁中 / expired 已过期 / unbanned 已解禁"""
        if not self.is_active:
            return 'unbanned'
        return 'expired' if self.is_expired else 'active'

    @property
    def is_permanent(self) -> bool:
        return self.expire_time is None
