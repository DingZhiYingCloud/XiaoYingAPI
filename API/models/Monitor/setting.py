"""上游故障告警设置（单例）

各服务调用上游失败时统一返回 4xxxx 错误码（第三方/外部服务错误，见
`API/common/status_code.py`），据此按「服务维度 + 最近窗口」统计上游故障率并邮件告警。

全库只有一行，存「所有服务共用」的判定参数。**接收邮箱不在这里存**，直接复用
「服务余量」页（`QuotaSetting.notify_email`）那一个 —— 两处告警都发给同一个后台管理员，
不重复配置。

为什么是单例：与 `QuotaSetting` / `SecuritySetting` 同一理由 —— 项目惯例是
「每个功能单独建表、字段即配置项」，这些项彼此相关、一起读写，单行表比零散键值更直观。
"""
from django.db import models

from API.common.base import BaseModel


class UpstreamAlertSetting(BaseModel):
    """上游故障告警设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    enabled = models.BooleanField(
        '启用告警', default=True,
        help_text='关闭后不再判定与发送上游故障告警；已置位的告警态会在下一轮检查时复位',
    )
    failed_rate_threshold = models.DecimalField(
        '失败率阈值', max_digits=5, decimal_places=2, default=50,
        help_text='窗口内上游错误占比不低于该百分比（%）时告警',
    )
    min_calls = models.PositiveIntegerField(
        '最小样本数', default=20,
        help_text='窗口内总调用量低于该值时不判定，避免小样本误报',
    )

    class Meta:
        db_table = 'upstream_alert_setting'
        verbose_name = '上游故障告警设置'
        verbose_name_plural = '上游故障告警设置'

    def __str__(self):
        return (f'上游故障告警设置（阈值 {self.failed_rate_threshold}%、'
                f'最小样本 {self.min_calls} 次、{"启用" if self.enabled else "停用"}）')

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'UpstreamAlertSetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
