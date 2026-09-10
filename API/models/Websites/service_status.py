"""服务状态配置（前台手动管理 API 服务的对外状态）

单一模型：记录某个服务前缀被“手动指定”的状态；未被指定的服务按默认规则展示
（已接入文档 = 开放，未接入文档 = 建设中）。
状态码/文案/样式见 API/website/service_status.py（唯一口径），此处仅存储数据。
"""
from django.db import models

from API.common.base import BaseModel

# 合法状态值（与 service_status.py STATUS_DEFS 的键保持一致）
STATUS_CHOICES = (
    ('open', '开放'),
    ('testing', '测试中'),
    ('maintenance', '维护中'),
    ('building', '建设中'),
    ('offline', '已下线'),
)


class ServiceStatus(BaseModel):
    """某 API 服务的手动状态覆盖（一服务一条，无记录 = 使用默认派生状态）"""

    url_prefix = models.CharField(
        '服务路由前缀', max_length=64, primary_key=True,
        help_text='对应官网服务清单的 url_prefix，如 /api/music/')
    status = models.CharField('服务状态', max_length=16, choices=STATUS_CHOICES)

    class Meta:
        db_table = 'api_service_status'
        verbose_name = '服务状态配置'
        verbose_name_plural = '服务状态配置'

    def __str__(self):
        return f'{self.url_prefix} -> {self.get_status_display()}'
