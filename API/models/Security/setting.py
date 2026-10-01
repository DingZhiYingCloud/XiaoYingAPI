"""安全设置（单例）

超管在 `/console/security/` 维护控制台自身的安全开关。

为什么是单例：与 `SiteAppearance` / `FeedbackSetting` 同一理由 —— 项目惯例是
「每个功能单独建表、字段即配置项」，安全配置项彼此相关、一起读写，单行表比零散键值更直观。
"""
from django.db import models

from API.common.base import BaseModel


class SecuritySetting(BaseModel):
    """控制台安全设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    hide_console = models.BooleanField(
        '后台入口隐身', default=True,
        help_text='开启后，未登录（或非超管）访问 /console/** 一律返回 404，'
                  '与访问一个根本不存在的地址看起来完全一样，探测者无法据此判断后台是否存在；'
                  '关闭则退回「跳转登录页」的行为，会把后台入口暴露出去',
    )

    class Meta:
        db_table = 'security_setting'
        verbose_name = '安全设置'
        verbose_name_plural = '安全设置'

    def __str__(self):
        return f'安全设置（后台入口隐身：{"开" if self.hide_console else "关"}）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'SecuritySetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
