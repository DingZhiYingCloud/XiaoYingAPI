"""API 调用统计数据模型

两级预聚合，都不保存调用明细：

1. **按天**（`ApiCallStat`，全历史保留）：按「日期 + 端点 + 项目 + 状态码」累加计数与耗时，
   是调用量的**唯一真值**（文档中心累计次数、公开统计接口、按天看板都读它）。
2. **按小时**（`ApiCallStatHour`，只保留近 HOUR_RETENTION_DAYS 天）：在上述维度上再细分小时，
   用于时段分布 / 星期×小时热力图 / 日内峰值这类**必须有小时维度**的分析。
   超过保留期由 `manage.py prune_api_call_hour` 删除——按天的真值表不受影响，
   因此不需要额外归档任务。

字段说明（两张表一致）:
    stat_date    - 统计日期（按 TIME_ZONE=Asia/Shanghai 的本地日期切分）
    stat_hour    - 统计小时 0-23（本地时间；仅按小时表有）
    service      - 服务前缀（取路径第 1 段，如 /api/email/），便于按服务汇总
    path         - 端点路径（已去掉查询串）
    app_id       - 接入项目 APPID；开放接口与未认证请求记为 NO_APP
    status_code  - 业务状态码（响应 JSON 里的 code）；响应非 JSON 时记 HTTP 状态码
    call_count   - 调用次数（累加）
    cost_sum_ms  - 总耗时（毫秒，累加，用于算平均）
    cost_max_ms  - 最大耗时（毫秒，取最大值）
    cost_points  - 消耗点数（累加；只对成功调用按当时生效单价结算，失败调用记 0）

写入口径见 API/common/api_stats.py（进程内缓冲 + 批量 UPSERT 累加，两张表同一批落库）。

`cost_points` 是「按当时单价结算」的**历史真值**：批量落库那一刻用当次生效单价算出并累加，
之后改价不会回填历史行，因此「累计消耗」永远可对账。
"""
import uuid

from django.db import models

from API.common.base import BaseModel

# 无接入项目（开放接口 / 签名校验未通过）时占位用的项目标识
NO_APP = '-'

# 小时粒度数据的保留天数（超过由 prune_api_call_hour 删除；按天数据不受影响）
HOUR_RETENTION_DAYS = 90


class ApiCallStat(BaseModel):
    """API 调用统计（按天预聚合）"""

    id = models.UUIDField('统计ID', primary_key=True, default=uuid.uuid4, editable=False)
    stat_date = models.DateField('统计日期', help_text='按本地时区（Asia/Shanghai）日期切分')
    service = models.CharField('服务前缀', max_length=100, help_text='路径第 1 段，如 /api/email/')
    path = models.CharField('端点路径', max_length=255, help_text='不含查询串的请求路径')
    app_id = models.CharField('接入项目', max_length=32, default=NO_APP,
                              help_text=f'接入项目 APPID；开放接口与未认证请求记为 {NO_APP}')
    status_code = models.PositiveIntegerField('状态码', help_text='业务 code；响应非 JSON 时为 HTTP 状态码')
    call_count = models.PositiveIntegerField('调用次数', default=0)
    cost_sum_ms = models.PositiveBigIntegerField('总耗时(毫秒)', default=0)
    cost_max_ms = models.PositiveIntegerField('最大耗时(毫秒)', default=0)
    cost_points = models.DecimalField('消耗点数', max_digits=20, decimal_places=4, default=0,
                                      help_text='成功调用按当时生效单价结算的点数（失败调用记 0）')

    class Meta:
        db_table = 'api_call_stat'
        verbose_name = 'API调用统计'
        verbose_name_plural = 'API调用统计'
        ordering = ['-stat_date']
        constraints = [
            # 聚合维度唯一：写入时按该组合 UPSERT 累加
            models.UniqueConstraint(
                fields=['stat_date', 'path', 'app_id', 'status_code'],
                name='uniq_api_call_stat',
            ),
        ]
        indexes = [
            models.Index(fields=['service', 'stat_date'], name='idx_apistat_service_date'),
            models.Index(fields=['app_id', 'stat_date'], name='idx_apistat_app_date'),
        ]

    def __str__(self):
        return f'{self.stat_date} {self.path} [{self.app_id}] code={self.status_code} x{self.call_count}'


class ApiCallStatHour(BaseModel):
    """API 调用统计（按小时预聚合，只保留近 HOUR_RETENTION_DAYS 天）

    与按天表的差别只有多一个 stat_hour；两张表的 service/path/app_id/status_code 口径完全一致，
    因此「同一区间的按小时汇总」与「按天表的合计」在保留期内应当相等（回归脚本会校验这一点）。
    """

    id = models.UUIDField('统计ID', primary_key=True, default=uuid.uuid4, editable=False)
    stat_date = models.DateField('统计日期', help_text='按本地时区（Asia/Shanghai）日期切分')
    stat_hour = models.PositiveSmallIntegerField('统计小时', help_text='本地时间小时 0-23')
    service = models.CharField('服务前缀', max_length=100, help_text='路径第 1 段，如 /api/email/')
    path = models.CharField('端点路径', max_length=255, help_text='不含查询串的请求路径')
    app_id = models.CharField('接入项目', max_length=32, default=NO_APP,
                              help_text=f'接入项目 APPID；开放接口与未认证请求记为 {NO_APP}')
    status_code = models.PositiveIntegerField('状态码', help_text='业务 code；响应非 JSON 时为 HTTP 状态码')
    call_count = models.PositiveIntegerField('调用次数', default=0)
    cost_sum_ms = models.PositiveBigIntegerField('总耗时(毫秒)', default=0)
    cost_max_ms = models.PositiveIntegerField('最大耗时(毫秒)', default=0)
    cost_points = models.DecimalField('消耗点数', max_digits=20, decimal_places=4, default=0,
                                      help_text='成功调用按当时生效单价结算的点数（失败调用记 0）')

    class Meta:
        db_table = 'api_call_stat_hour'
        verbose_name = 'API调用统计(按小时)'
        verbose_name_plural = 'API调用统计(按小时)'
        ordering = ['-stat_date', '-stat_hour']
        constraints = [
            models.UniqueConstraint(
                fields=['stat_date', 'stat_hour', 'path', 'app_id', 'status_code'],
                name='uniq_api_call_stat_hour',
            ),
        ]
        indexes = [
            models.Index(fields=['stat_date', 'stat_hour'], name='idx_apistat_hour_date'),
            models.Index(fields=['service', 'stat_date', 'stat_hour'], name='idx_apistat_hour_service'),
            models.Index(fields=['app_id', 'stat_date', 'stat_hour'], name='idx_apistat_hour_app'),
        ]

    def __str__(self):
        return (f'{self.stat_date} {self.stat_hour:02d}:00 {self.path} [{self.app_id}] '
                f'code={self.status_code} x{self.call_count}')

