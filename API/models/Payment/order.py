"""支付订单与回调留痕

    PayOrder      - 一笔支付订单（本系统生成的 out_trade_no 为唯一业务键）
    PayNotifyLog  - 异步通知原文留痕（排查「用户已付款但订单没更新」用）

订单来源两类，用 user / app 两个外键区分（都可为空）：
    · 本站充值：`user` 有值（下单的登录用户）；支付成功自动给「用户账户余额」加钱
    · 对外调用：`app` 有值（签名认证出的接入项目）；支付成功不改任何余额，
      由调用方通过回调 / 主动查单自行处理（`param` 原样回传，供对账）

订单状态与平台口径的映射（易支付 `status`：0 未支付 / 1 已支付 / 2 已退款 / 3 已冻结 / 4 预授权）：
    pending           待支付
    paid              已支付
    partial_refunded  部分退款
    refunded          已全额退款
    failed            支付失败
    closed            已关闭（超时未支付 / 手工关闭）
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import UserApp
from API.models.Users.user import User


class PayOrder(BaseModel):
    """支付订单"""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_PARTIAL_REFUNDED = 'partial_refunded'
    STATUS_REFUNDED = 'refunded'
    STATUS_FAILED = 'failed'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = (
        (STATUS_PENDING, '待支付'),
        (STATUS_PAID, '已支付'),
        (STATUS_PARTIAL_REFUNDED, '部分退款'),
        (STATUS_REFUNDED, '已全额退款'),
        (STATUS_FAILED, '支付失败'),
        (STATUS_CLOSED, '已关闭'),
    )
    #: 已收到钱的终态（用于幂等判断：这些状态不允许被后来的回调改写）
    PAID_STATUSES = (STATUS_PAID, STATUS_PARTIAL_REFUNDED, STATUS_REFUNDED)

    id = models.UUIDField('订单ID', primary_key=True, default=uuid.uuid4, editable=False)
    out_trade_no = models.CharField('商户订单号', max_length=64, unique=True,
                                    help_text='本系统生成，全局唯一；传给支付平台作为 out_trade_no')
    trade_no = models.CharField('平台订单号', max_length=64, blank=True, default='', db_index=True,
                                help_text='支付平台返回的订单号（下单时可能还没有，回调/查单补齐）')

    provider_code = models.CharField('支付渠道', max_length=32, db_index=True,
                                     help_text='PayProvider.code，如 ezfp')
    pay_type = models.CharField('支付方式', max_length=20, blank=True, default='',
                                help_text='alipay / wxpay …')
    method = models.CharField('发起方式', max_length=20, blank=True, default='web',
                              help_text='易支付的 method，本站固定 web（只取二维码）')
    subject = models.CharField('商品名称', max_length=128, help_text='传给平台的 name')
    amount = models.DecimalField('订单金额（元）', max_digits=14, decimal_places=2,
                                 help_text='两位小数；回调时必须与本字段核对')
    pay_info = models.TextField('支付参数', blank=True, default='',
                                help_text='平台返回的 pay_info（本系统只用二维码内容），供前端展示')

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    refund_amount = models.DecimalField('已退款金额（元）', max_digits=14, decimal_places=2, default=0)
    buyer = models.CharField('支付用户标识', max_length=128, blank=True, default='')

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='pay_orders', verbose_name='下单用户',
                             help_text='本站充值订单的下单用户；对外调用创建的订单为空')
    app = models.ForeignKey(UserApp, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name='pay_orders', verbose_name='下单项目',
                            help_text='对外调用时签名认证出的接入项目；本站充值订单为空')
    client_ip = models.CharField('用户IP', max_length=45, blank=True, default='')
    param = models.CharField('业务扩展参数', max_length=255, blank=True, default='',
                             help_text='调用方传入，回调/查单原样返回，便于对账')

    paid_at = models.DateTimeField('支付时间', null=True, blank=True)
    closed_at = models.DateTimeField('关闭时间', null=True, blank=True)
    last_query_at = models.DateTimeField('最近查单时间', null=True, blank=True)

    class Meta:
        db_table = 'pay_order'
        verbose_name = '支付订单'
        verbose_name_plural = '支付订单'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['provider_code', 'status'], name='idx_pay_order_prov_status'),
            models.Index(fields=['user', '-create_time'], name='idx_pay_order_user_time'),
            models.Index(fields=['app', '-create_time'], name='idx_pay_order_app_time'),
        ]

    def __str__(self):
        return f'{self.out_trade_no} {self.amount}元 ({self.get_status_display()})'

    @property
    def is_paid(self) -> bool:
        return self.status in self.PAID_STATUSES


class PayNotifyLog(BaseModel):
    """异步通知原文留痕

    每次收到平台的 notify 都写一条（无论验签是否通过），用于事后排查
    「平台说通知了、我们没更新」这类问题。**不存完整密钥**，只存原始参数串。
    """

    provider_code = models.CharField('支付渠道', max_length=32, db_index=True)
    out_trade_no = models.CharField('商户订单号', max_length=64, blank=True, default='', db_index=True)
    trade_no = models.CharField('平台订单号', max_length=64, blank=True, default='')
    raw = models.TextField('通知原文', blank=True, default='', help_text='平台发来的原始参数串（含 sign）')
    verified = models.BooleanField('验签通过', default=False)
    handled = models.BooleanField('业务已处理', default=False,
                                  help_text='True = 本次通知成功推进了订单状态（含「已处理过、幂等跳过」）')
    message = models.CharField('处理结果', max_length=255, blank=True, default='')
    ip = models.CharField('来源IP', max_length=45, blank=True, default='')
    user_agent = models.CharField('User-Agent', max_length=255, blank=True, default='')

    class Meta:
        db_table = 'pay_notify_log'
        verbose_name = '支付回调留痕'
        verbose_name_plural = '支付回调留痕'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['out_trade_no', '-create_time'], name='idx_pay_notify_order_time'),
        ]

    def __str__(self):
        return f'{self.provider_code} {self.out_trade_no} 验签={self.verified}'
