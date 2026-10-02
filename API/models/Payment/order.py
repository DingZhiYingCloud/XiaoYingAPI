"""支付订单、回调留痕与退款申请

    PayOrder         - 一笔支付订单（本系统生成的 out_trade_no 为唯一业务键）
    PayNotifyLog     - 异步通知原文留痕（排查「用户已付款但订单没更新」用）
    PayRefundRequest - 退款申请（渠道不支持自助退款时的人工受理队列）

订单来源两类，两条路径的**发货口径一致**（都给「下单用户」的账户余额加钱）：
    · 本站充值：`user` 有值（下单的登录用户），`app` 为空
    · 对外调用：`app` 有值（签名认证出的接入项目，用于查单 / 退款的归属隔离），
      `user` 由调用方在下单时用 `user_id` 指定（钱加到这个用户账上）

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
                                help_text='调用方选择的支付方式：alipay / wxpay …')
    pay_form = models.CharField('支付形态', max_length=20, blank=True, default='',
                                help_text='平台返回的形态：qrcode 二维码 / jump 收银台地址 / html 网页表单；'
                                          '前端按它决定渲染方式')
    method = models.CharField('发起方式', max_length=20, blank=True, default='web',
                              help_text='下单时传给平台的 method：web / jump / jsapi / app / scan / applet')
    subject = models.CharField('商品名称', max_length=128, help_text='传给平台的 name')
    amount = models.DecimalField('订单金额（元）', max_digits=14, decimal_places=2,
                                 help_text='两位小数；回调时必须与本字段核对')
    pay_info = models.TextField('支付参数', blank=True, default='',
                                help_text='平台返回的 pay_info：pay_form=qrcode 时是二维码内容，'
                                          'jump 时是收银台地址，供前端展示')

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    refund_amount = models.DecimalField('已退款金额（元）', max_digits=14, decimal_places=2, default=0)
    buyer = models.CharField('支付用户标识', max_length=128, blank=True, default='')

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='pay_orders', verbose_name='下单用户',
                             help_text='钱最终加到这个用户的账户余额上；本站充值即下单人，'
                                       '对外调用由调用方用 user_id 指定')
    app = models.ForeignKey(UserApp, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name='pay_orders', verbose_name='下单项目',
                            help_text='对外调用时签名认证出的接入项目（用于归属隔离）；本站充值订单为空')
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

    # ---------- 展示用中文（后台/前台列表把 ezfp jump 这类技术值翻成人话） ----------

    @property
    def provider_name(self) -> str:
        """渠道展示名（如 ezfp → 易支付）"""
        from API.apis.pay.providers.registry import provider_name

        return provider_name(self.provider_code)

    @property
    def pay_type_label(self) -> str:
        """支付方式的中文名（如 alipay → 支付宝）"""
        from API.apis.pay.providers.registry import pay_type_label

        return pay_type_label(self.provider_code, self.pay_type)

    @property
    def pay_form_label(self) -> str:
        """支付形态的中文说明（如 jump → 跳转收银台）"""
        from API.apis.pay.providers.registry import pay_form_label

        return pay_form_label(self.pay_form)


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


class PayRefundRequest(BaseModel):
    """退款申请（人工受理队列）

    **为什么要这张表**：有些支付渠道没有对商户开通「自助退款」（易支付当前就是这样：
    调 `/api/pay/refund` 会被平台回「管理员未开启商户后台自助退款」）。这种情况不能让
    退款请求就这么失败掉 —— 用户/接入项目会以为钱退不了了。改为**先受理、后人工处理**：
    落一条待处理的申请，回复「人工审核后 N 个工作日内退款」，由超管在平台后台把钱退掉、
    再回本站把这条申请标记为「已退款」（顺带把订单状态与用户余额一起对齐）。

    渠道支不支持自助退款由 `PayProvider.refund_mode` 决定（auto / manual），
    因此以后新增的渠道同样适用，不必改代码。

    状态流转（**只有待处理可以流转**，已处理的不可再改，避免重复退款）：
        pending    待人工处理
        refunded   已退款（人工在平台后台退完，回本站标记）
        rejected   已驳回（说明原因；订单保持已支付）
    """

    STATUS_PENDING = 'pending'
    STATUS_REFUNDED = 'refunded'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, '待人工处理'),
        (STATUS_REFUNDED, '已退款'),
        (STATUS_REJECTED, '已驳回'),
    )

    SOURCE_API = 'api'
    SOURCE_USER = 'user'
    SOURCE_CONSOLE = 'console'
    SOURCE_CHOICES = (
        (SOURCE_API, '接入项目发起'),
        (SOURCE_USER, '用户申请'),
        (SOURCE_CONSOLE, '管理员登记'),
    )

    id = models.UUIDField('申请ID', primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(PayOrder, on_delete=models.CASCADE, related_name='refund_requests',
                              verbose_name='支付订单')
    #: 订单号的冗余副本：列表与工单核对时不必再关联查询，订单被删也不影响可读性
    out_trade_no = models.CharField('商户订单号', max_length=64, db_index=True)
    provider_code = models.CharField('支付渠道', max_length=32, blank=True, default='', db_index=True)
    amount = models.DecimalField('申请退款金额（元）', max_digits=14, decimal_places=2,
                                 help_text='不得大于「订单金额 − 已退金额 − 其它待处理申请金额」')

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    source = models.CharField('申请来源', max_length=10, choices=SOURCE_CHOICES, default=SOURCE_USER,
                              help_text='谁提的这条申请，便于人工核实时回访')

    applicant_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='pay_refund_requests', verbose_name='申请用户',
                                       help_text='本站充值订单的申请用户；接入项目发起时为空')
    applicant_app = models.ForeignKey(UserApp, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='pay_refund_requests', verbose_name='申请项目',
                                      help_text='对外调用时签名认证出的接入项目；用户申请时为空')
    contact = models.CharField('联系方式', max_length=128, blank=True, default='',
                               help_text='申请人留的联系方式（可选），供人工核实')
    remark = models.CharField('申请说明', max_length=255, blank=True, default='')

    operator = models.CharField('处理人', max_length=64, blank=True, default='')
    handled_at = models.DateTimeField('处理时间', null=True, blank=True)
    handle_note = models.CharField('处理备注', max_length=255, blank=True, default='',
                                   help_text='驳回原因，或人工退款时填平台退款单号')

    class Meta:
        db_table = 'pay_refund_request'
        verbose_name = '退款申请'
        verbose_name_plural = '退款申请'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['order', '-create_time'], name='idx_pay_refund_order_time'),
            models.Index(fields=['status', '-create_time'], name='idx_pay_refund_status_time'),
        ]

    def __str__(self):
        return f'{self.out_trade_no} {self.amount}元 ({self.get_status_display()})'

    @property
    def is_pending(self) -> bool:
        return self.status == self.STATUS_PENDING

    @property
    def provider_name(self) -> str:
        """渠道展示名（如 ezfp → 易支付）"""
        from API.apis.pay.providers.registry import provider_name

        return provider_name(self.provider_code)
