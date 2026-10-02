"""服务余量通知设置（单例）

全库只有一行，存「所有服务共用」的通知项 —— 目前就一个接收通知邮箱。

为什么是单例：与 `SecuritySetting` / `SiteAppearance` 同一理由 —— 项目惯例是
「每个功能单独建表、字段即配置项」，这些项彼此相关、一起读写，单行表比零散键值更直观。
"""
from django.db import models

from API.common.base import BaseModel


class QuotaSetting(BaseModel):
    """余量通知设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    notify_email = models.EmailField(
        '接收通知邮箱', blank=True, default='',
        help_text='所有服务的余量告警统一发到该邮箱；留空则不发信，只在控制台提示告警',
    )

    class Meta:
        db_table = 'quota_setting'
        verbose_name = '余量通知设置'
        verbose_name_plural = '余量通知设置'

    def __str__(self):
        return f'余量通知设置（接收邮箱：{self.notify_email or "未配置"}）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'QuotaSetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
