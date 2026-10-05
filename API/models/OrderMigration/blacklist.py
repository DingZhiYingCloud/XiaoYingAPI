"""代练搬单标题黑名单

每条一个词，抓单时代练通标题包含任意一条就不搬运 —— 这类标题（联系 / 看要求 / 勿扰 …）
像「公告」，发到代练丸子有被平台判定成公告的嫌疑。

做成独立表而不是配置里的一串文本，是为了后续能逐条增删（后台页面提供添加 / 删除）。
"""
from django.db import models

from API.common.base import BaseModel

# 初始黑名单（数据迁移时写入；与需求给的数组一致）
DEFAULT_BLACKLIST_WORDS = [
    'r', '此单', '联系', '看要求', '出w', 'w', '出', '需要', '老板',
    '接', '人不够', '俱乐部', '限', '陪练', '陪', '勿扰', '一个',
]


class OrderMigrationBlacklist(BaseModel):
    """标题黑名单条目（一条一个词）"""

    word = models.CharField('黑名单词', max_length=64, unique=True)

    class Meta:
        db_table = 'order_migration_blacklist'
        verbose_name = '搬单标题黑名单'
        verbose_name_plural = '搬单标题黑名单'
        ordering = ['-create_time']

    def __str__(self):
        return self.word
