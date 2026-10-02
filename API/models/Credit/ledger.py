"""接入项目额度 · 充值流水

每次超管在控制台给某个项目充值（或扣回 / 纠错调整）都在这里留一行，用于对账与追溯。

**只记「人工调整」，不记扣费**：调用扣费是按次发生的（可能每秒几十次），逐笔落表会把
SQLite 的单写锁打爆；扣费的事实已经由调用统计（`ApiCallStat`，按 app 可查成功调用次数）
完整记录，余额 = Σ流水 - 按单价折算的累计消耗，两边能对上。

金额允许为负：负数是「扣回 / 纠错」，正数是「充值」。
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class AppCreditLedger(BaseModel):
    """一条额度调整记录（充值 / 扣回）"""

    id = models.UUIDField('流水ID', primary_key=True, default=uuid.uuid4, editable=False)
    app = models.ForeignKey(
        'API.UserApp', on_delete=models.CASCADE, related_name='credit_ledger',
        db_index=True, verbose_name='接入项目',
    )
    amount = models.DecimalField(
        '调整金额', max_digits=16, decimal_places=2,
        help_text='正数=充值，负数=扣回 / 纠错（单位：点）',
    )
    balance_after = models.DecimalField(
        '调整后余额', max_digits=16, decimal_places=2,
        help_text='本次调整完成后该项目的余额快照，便于对账',
    )
    operator = models.CharField('操作人', max_length=150, blank=True, default='',
                                help_text='执行本次调整的超管用户名')
    remark = models.CharField('备注', max_length=255, blank=True, default='')

    class Meta:
        db_table = 'app_credit_ledger'
        verbose_name = '额度流水'
        verbose_name_plural = '额度流水'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['app', '-create_time'], name='idx_credit_app_time'),
        ]

    def __str__(self):
        return f'{self.app_id} {self.amount:+} -> {self.balance_after}'
