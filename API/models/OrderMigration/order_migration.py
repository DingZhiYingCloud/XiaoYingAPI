"""代练搬单记录模型

记录一笔「代练通订单 → 代练丸子发单」的搬运全生命周期，供监控轮询与对账：
    已抓取(candidate) → 已发丸子(published) → 代练通已接单(taken)
    另含 失败(failed) / 已撤单(cancelled)

设计意图：
    - 监控轮询需要「代练通单号 ↔ 丸子 trade_no」的稳定映射与状态机；
    - 号主游戏账号属敏感信息，落库 AES 加密（复用 EncryptedSecretField）。
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import EncryptedSecretField


class MigrationStatus(models.TextChoices):
    """搬单记录状态"""

    CANDIDATE = 'candidate', '已抓取（未发布）'
    PUBLISHING = 'publishing', '发单中（未确认）'
    PUBLISHED = 'published', '已发丸子（待接单）'
    TAKEN = 'taken', '代练通已接单'
    FAILED = 'failed', '失败'
    CANCELLED = 'cancelled', '已撤单'


class OrderMigration(BaseModel):
    """一笔代练通订单搬运到代练丸子的记录"""

    id = models.UUIDField('记录ID', primary_key=True, default=uuid.uuid4, editable=False)

    # 代练通侧（来源订单）
    dlt_serial_no = models.CharField('代练通订单号', max_length=64, unique=True)
    dlt_title = models.CharField('代练通标题', max_length=255)
    dlt_price = models.FloatField('代练通金额(元)')
    dlt_zone = models.CharField('代练通大区', max_length=32)
    dlt_time_limit = models.IntegerField('代练通时限(小时)')
    dlt_ensure = models.FloatField(
        '代练通双金(元)', default=0,
        help_text='该代练通原单接单需冻结的总保证金（Ensure），用于跨轮占用代练通余额、防止超发')

    # 代练丸子侧（镜像订单）
    dlwz_trade_no = models.CharField('丸子订单号', max_length=64, blank=True, db_index=True)
    amount = models.FloatField('丸子发布价(元)', default=0)
    security_deposit = models.FloatField('安全保证金(元)', default=0)
    efficiency_deposit = models.FloatField('效率保证金(元)', default=0)

    # 状态机与观测
    status = models.CharField('状态', max_length=16, choices=MigrationStatus.choices,
                              default=MigrationStatus.CANDIDATE, db_index=True)
    dlwz_status = models.IntegerField('丸子订单状态快照', null=True, blank=True)
    account_info = EncryptedSecretField(
        '号主账号信息', max_length=2000, blank=True,
        help_text='代练通接单后取到的账号/密码/角色名等，落库 AES 加密')
    message = models.CharField('备注/错误', max_length=500, blank=True)

    class Meta:
        db_table = 'order_migration'
        verbose_name = '代练搬单记录'
        verbose_name_plural = '代练搬单记录'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.dlt_serial_no} → {self.dlwz_trade_no or "(未发布)"} [{self.get_status_display()}]'
