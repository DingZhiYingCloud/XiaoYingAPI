"""图床上传 token 池

统一管理各图床线路的账号上传 token 及其容量配额。
服务器只记录每个 token 的已用容量（不参与图片存储）：
- 上传成功时按图床返回的图片大小累加 used_bytes；
- 当 used_bytes >= capacity_bytes（容量用尽）时，上传层会自动删除该 token，
  后续上传自动切换到下一个仍有余量的 token。

每个 token 默认容量 50MB（可在导入 token 时自定义）。
"""
from django.db import models

from API.common.base import BaseModel


class ImageHostingToken(BaseModel):
    """图床上传 token（一条 = 一个账号 token + 其容量配额）"""

    token = models.CharField('Token', max_length=255, unique=True)
    capacity_bytes = models.BigIntegerField('容量（字节）', default=50 * 1024 * 1024)
    used_bytes = models.BigIntegerField('已用（字节）', default=0)

    class Meta:
        db_table = 'image_hosting_token'
        verbose_name = '图床Token'
        verbose_name_plural = '图床Token'
        ordering = ['create_time', 'id']

    def __str__(self):
        return f'图床Token#{self.pk}'

    @property
    def remaining_bytes(self) -> int:
        """剩余容量（字节），最小为 0"""
        return max(self.capacity_bytes - self.used_bytes, 0)
