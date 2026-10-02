"""上游故障告警态（每行一个服务）

只存「跨轮次必须记住」的东西：某个服务当前是否处于告警中。窗口内的调用量、上游错误数
与失败率都是**实时从调用统计表算出来的**，是本轮检查的产物、不是需要持久化的状态，
故不在此冗余存放（避免同一份信息两处维护、互相漂移）。

为什么每行一个服务而不是键值对：与项目「每个功能单独建表、字段即配置项」的惯例一致，
也便于用行级条件更新做多 worker 抢占（见 `API/apis/monitor/utils.py` 的 `_evaluate`）。
"""
from django.db import models

from API.common.base import BaseModel


class UpstreamAlertState(BaseModel):
    """单个服务的上游故障告警态"""

    service = models.CharField(
        '服务前缀', max_length=64, unique=True,
        help_text='与调用统计表的 service 字段口径一致，如 /api/haijiao/',
    )
    alert_active = models.BooleanField(
        '告警中', default=False,
        help_text='告警只发一次：判定为故障时置位，恢复正常后自动复位（重新武装）',
    )
    last_alert_at = models.DateTimeField('最近告警时间', null=True, blank=True)

    class Meta:
        db_table = 'upstream_alert_state'
        verbose_name = '上游故障告警态'
        verbose_name_plural = '上游故障告警态'
        ordering = ('service',)

    def __str__(self):
        return f'{self.service}（{"告警中" if self.alert_active else "正常"}）'
