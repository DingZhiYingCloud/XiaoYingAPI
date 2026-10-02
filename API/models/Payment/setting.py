"""支付设置（单例）

全库只有一行，存「在线支付」的全局开关与门槛：
    enabled            - 是否开启在线支付（关闭后前台充值页不再下单、/api/pay/create 直接拒绝）
    min_amount         - 单笔最低充值金额（元）
    refund_notice_days - 人工受理退款的告知天数（回复「N 个工作日内退款」，见 provider.refund_mode）

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
    min_amount = models.DecimalField(
        '单笔最低金额（元）', max_digits=14, decimal_places=2, default=1,
        help_text='单笔充值 / 下单的最低金额，低于该值直接拒绝',
    )
    refund_notice_days = models.PositiveIntegerField(
        '人工退款告知天数（工作日）', default=7,
        help_text='渠道不支持自助退款时，回复申请人「人工审核后 N 个工作日内退款」；'
                  '只影响文案，不参与任何计算',
    )

    class Meta:
        db_table = 'pay_setting'
        verbose_name = '支付设置'
        verbose_name_plural = '支付设置'

    def __str__(self):
        return f'支付设置（{"开启" if self.enabled else "关闭"}）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'PaySetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
