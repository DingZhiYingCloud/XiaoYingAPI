"""用户余额流水

用户账户余额（`User.balance`，单位「元」）的每一次变动都在这里留一条，用途：
    · 对账：支付充值到账 / 管理员调整 / 兑换成项目点数 / 退款扣回，逐笔可查
    · 追溯：每条都记「变动后余额」，任何时点都能还原余额是怎么来的

类型（type）：
    pay       - 支付充值（关联 PayOrder）
    transfer  - 兑换成接入项目点数（关联 UserApp，points 记换到的点数）
    admin     - 管理员手动调整（金额可正可负）
    refund    - 订单退款扣回

与 `AppCreditLedger`（项目额度流水，单位「点」）的区别：那张表记的是**项目额度**，
本表记的是**用户账户余额**，两者之间通过 transfer 打通（余额 -X 元 → 项目点数 +X×汇率）。
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Payment.order import PayOrder
from API.models.Projects.app import UserApp
from API.models.Users.user import User


class UserBalanceLedger(BaseModel):
    """用户余额流水（只增不改，逐笔可查）"""

    TYPE_PAY = 'pay'
    TYPE_TRANSFER = 'transfer'
    TYPE_ADMIN = 'admin'
    TYPE_REFUND = 'refund'
    TYPE_CHOICES = (
        (TYPE_PAY, '支付充值'),
        (TYPE_TRANSFER, '兑换项目点数'),
        (TYPE_ADMIN, '管理员调整'),
        (TYPE_REFUND, '退款扣回'),
    )

    id = models.UUIDField('流水ID', primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='balance_ledgers',
                             verbose_name='用户')
    type = models.CharField('类型', max_length=20, choices=TYPE_CHOICES, db_index=True)
    amount = models.DecimalField('变动金额（元）', max_digits=14, decimal_places=2,
                                 help_text='正数=余额增加，负数=余额减少')
    balance_after = models.DecimalField('变动后余额（元）', max_digits=14, decimal_places=2)

    order = models.ForeignKey(PayOrder, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='balance_ledgers', verbose_name='关联支付订单')
    app = models.ForeignKey(UserApp, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name='balance_ledgers', verbose_name='关联项目',
                            help_text='兑换项目点数时的目标项目')
    points = models.DecimalField('兑换点数', max_digits=20, decimal_places=4, default=0,
                                 help_text='仅兑换类型有意义：本次换到项目上的点数')
    operator = models.CharField('操作人', max_length=64, blank=True, default='',
                                help_text='管理员调整时记超管用户名；系统动作为空')
    remark = models.CharField('备注', max_length=255, blank=True, default='')

    class Meta:
        db_table = 'user_balance_ledger'
        verbose_name = '用户余额流水'
        verbose_name_plural = '用户余额流水'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['user', '-create_time'], name='idx_user_bal_user_time'),
            models.Index(fields=['type', '-create_time'], name='idx_user_bal_type_time'),
        ]

    def __str__(self):
        return f'{self.user} {self.get_type_display()} {self.amount} → {self.balance_after}'
