"""API 调用统计数据模型

按天预聚合：不保存每次调用的明细，只按「日期 + 端点 + 项目 + 状态码」累加计数与耗时，
既能把表控制在可预期规模，又能支撑服务/端点/项目/状态码/耗时各维度查询。

字段说明:
    stat_date    - 统计日期（按 TIME_ZONE=Asia/Shanghai 的本地日期切分）
    service      - 服务前缀（取路径第 1 段，如 /api/email/），便于按服务汇总
    path         - 端点路径（已去掉查询串）
    app_id       - 接入项目 APPID；开放接口与未认证请求记为 NO_APP
    status_code  - 业务状态码（响应 JSON 里的 code）；响应非 JSON 时记 HTTP 状态码
    call_count   - 调用次数（累加）
    cost_sum_ms  - 总耗时（毫秒，累加，用于算平均）
    cost_max_ms  - 最大耗时（毫秒，取最大值）

写入口径见 API/common/api_stats.py（进程内缓冲 + 批量 UPSERT 累加）。
"""
import uuid

from django.db import models

from API.common.base import BaseModel

# 无接入项目（开放接口 / 签名校验未通过）时占位用的项目标识
NO_APP = '-'


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
