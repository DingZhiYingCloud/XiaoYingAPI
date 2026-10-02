"""支付设置（单例）

全库只有一行，存「在线支付」的全局开关与换算口径：
    enabled          - 是否开启在线支付（关闭后前台充值页不再下单、/api/pay/create 直接拒绝）
    points_per_yuan  - 兑换汇率：1 元 = 多少点（用户余额 → 接入项目点数时使用）
    min_amount       - 单笔最低充值金额（元）

为什么是单例：与 `SecuritySetting` / `QuotaSetting` / `SiteAppearance` 同一理由 ——
项目惯例是「每个功能单独建表、字段即配置项」，这些项彼此相关、一起读写，单行表比零散键值更直观。

各支付渠道自身的商户配置（pid / 密钥 / 开关）不在这里，见 `Payment/provider.py`。
"""
from django.db import models

from API.common.base import BaseModel


class PaySetting(BaseModel):
    """支付设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    enabled = models.BooleanField(
        '开启在线支付', default=True,
        help_text='关闭后前台充值页不再展示下单入口，/api/pay/create 直接返回「支付未开启」',
    )
    points_per_yuan = models.DecimalField(
        '兑换汇率（点/元）', max_digits=12, decimal_places=4, default=1,
        help_text='1 元等于多少点数，用于「用户余额（元）→ 接入项目点数」的兑换；默认 1',
    )
    min_amount = models.DecimalField(
        '单笔最低金额（元）', max_digits=14, decimal_places=2, default=1,
        help_text='单笔充值 / 下单的最低金额，低于该值直接拒绝',
    )

    class Meta:
        db_table = 'pay_setting'
        verbose_name = '支付设置'
        verbose_name_plural = '支付设置'

    def __str__(self):
        return f'支付设置（{"开启" if self.enabled else "关闭"}，1 元 = {self.points_per_yuan} 点）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'PaySetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
