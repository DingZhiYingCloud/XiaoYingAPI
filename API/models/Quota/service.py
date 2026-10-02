"""服务余量（各上游服务账号的余额 / 剩余数量）

用于盯着平台自用的第三方服务账号还剩多少：51代理 的账户余额（元）、超级鹰的题分，
低于各自设定的阈值时由后台线程发邮件提醒。

**本表只存「按服务可配置的项 + 每次检查的结果」**：「显示名 / 单位 / 怎么取数」属于代码侧的
服务注册表（见 `API/apis/quota/services.py`），不重复存库，避免同一份信息两处维护、互相漂移。

为什么每行就是一个服务而不是键值对：与项目「每个功能单独建表、字段即配置项」的惯例一致，
一行读出来就是该服务完整的配置与状态。
"""
from django.db import models

from API.common.base import BaseModel


class QuotaService(BaseModel):
    """单个被监控服务的余量与通知配置"""

    NOTIFY_METHOD_EMAIL = 'email'
    NOTIFY_METHOD_CHOICES = (
        (NOTIFY_METHOD_EMAIL, '邮件'),
    )

    code = models.CharField(
        '服务标识', max_length=50, unique=True,
        help_text='与 API/apis/quota/services.py 的服务注册表一一对应',
    )
    balance = models.DecimalField(
        '当前余量', max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='最近一次成功检查取回的数值；从未成功过则为空',
    )
    threshold = models.DecimalField(
        '最低数量阈值', max_digits=14, decimal_places=4, null=True, blank=True,
        help_text='余量低于该值时发通知；留空表示不通知',
    )
    notify_enabled = models.BooleanField('启用通知', default=True)
    notify_method = models.CharField(
        '通知方式', max_length=20, choices=NOTIFY_METHOD_CHOICES,
        default=NOTIFY_METHOD_EMAIL,
        help_text='目前只有邮件一种方式',
    )
    alert_active = models.BooleanField(
        '告警中', default=False,
        help_text='告警只发一次：跌破阈值时置位，恢复后自动复位（重新武装）',
    )
    last_checked_at = models.DateTimeField('最近检查时间', null=True, blank=True)
    last_error = models.CharField('最近一次检查错误', max_length=255, blank=True, default='')
    last_notified_at = models.DateTimeField('最近告警时间', null=True, blank=True)

    class Meta:
        db_table = 'quota_service'
        verbose_name = '服务余量'
        verbose_name_plural = '服务余量'

    def __str__(self):
        return f'{self.code}（余量 {self.balance}）'
