"""支付服务层（下单 / 查单 / 退款 / 发货）

对外 `/api/pay/*` 与本站充值页**都调这一层**（本站内部直连，不走 /api/ 签名）。
视图只做参数校验与统一 JSON，业务规则都收在这里。

三条安全红线（写死在实现里，不要在别处复制判断）：
    1. **只认异步通知 + 主动查单**：页面跳转（return_url）不算支付成功；
    2. **回调必须验签 + 核对商户订单号 + 核对金额**，三者缺一不可；
    3. **发货只发生一次**：订单状态推进用「行锁 + 状态判断」保证幂等，
       重复通知不会重复加钱。
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from API.apis.pay.providers import build_provider
from API.apis.pay.providers.base import PayError
from API.apis.pay.utils import (absolute_url, client_ip, format_money,
                                gen_out_trade_no, parse_money)
from API.models import (
    PayNotifyLog,
    PayOrder,
    PayProvider,
    PayRefundRequest,
    PaySetting,
    User,
    UserBalanceLedger,
)

logger = logging.getLogger('api.pay')

#: 平台订单号入库长度上限（PayOrder.trade_no = 64）
_TRADE_NO_MAX = 64


# ==================== 渠道配置 ====================

def get_config(provider_code: str) -> PayProvider:
    """取渠道配置行（不存在直接报错，避免静默走空配置）"""
    config = PayProvider.objects.filter(code=(provider_code or '').strip()).first()
    if config is None:
        raise PayError(f'支付渠道不存在：{provider_code}')
    return config


def build_provider_for(provider_code: str):
    """按渠道标识构造可用实例（校验渠道已启用）"""
    config = get_config(provider_code)
    if not config.enabled:
        raise PayError(f'{config.name} 当前未启用')
    provider = build_provider(config)
    if provider is None:
        raise PayError(f'支付渠道 {provider_code} 没有对应的实现，请检查 providers 注册表')
    return provider


def available_channels() -> list:
    """前台可选渠道（已启用 + 已登记实现）"""
    rows = []
    for config in PayProvider.objects.filter(enabled=True):
        provider = build_provider(config)
        if provider is not None:
            rows.append(config)
    return rows


# ==================== 下单 ====================

def create_order(*, provider_code, amount, pay_type, subject,
                 user=None, app=None, client_ip='', request=None,
                 return_url='', param='', method='web', device='pc') -> PayOrder:
    """统一下单并落库

    :param user: 钱加到哪个用户账上（支付成功自动给其账户余额加本次金额）；
        本站充值传下单用户，对外调用传调用方指定的 user_id
    :param app:  对外调用时签名认证出的接入项目（仅作归属隔离与留痕，不影响发货）
    :param return_url: 支付完成后浏览器跳回地址；留空用站点根地址
    :param method: 调用方式（网页端 web；**移动端 App 建议 jump**）
    :param device: 设备类型（网页端 pc；**移动端 mobile / wechat / alipay**）
    :return: 已落库的 PayOrder（status=pending，pay_info 为二维码内容或跳转地址）
    """
    setting = PaySetting.get_solo()
    if not setting.enabled:
        raise PayError('在线支付当前未开启，请联系管理员')

    money = parse_money(amount)
    if money is None or money <= 0:
        raise PayError('金额非法：必须为大于 0 的数字（元）')
    if money < Decimal(str(setting.min_amount)):
        raise PayError(f'金额低于最低充值金额 {format_money(setting.min_amount)} 元')

    provider = build_provider_for(provider_code)
    if not provider.config.method_allowed(pay_type):
        raise PayError(f'{provider.name} 不支持支付方式：{pay_type}')

    notify_url = absolute_url(request, f'/pay/notify/{provider_code}/')
    back_url = return_url or absolute_url(request, '/')

    order = PayOrder.objects.create(
        out_trade_no=gen_out_trade_no(),
        provider_code=provider_code,
        pay_type=pay_type,
        method=method,
        subject=(subject or '账户充值')[:128],
        amount=money,
        user=user,
        app=app,
        client_ip=client_ip or '',
        param=(param or '')[:255],
        status=PayOrder.STATUS_PENDING,
    )

    try:
        result = provider.create_order(
            out_trade_no=order.out_trade_no, amount=money, subject=order.subject,
            pay_type=pay_type, client_ip=client_ip, notify_url=notify_url,
            return_url=back_url, param=order.param, method=method, device=device,
        )
    except PayError:
        # 下单失败：订单留痕为「失败」，便于后台看到「有单没拿到二维码」的真实原因
        order.status = PayOrder.STATUS_FAILED
        order.save(update_fields=['status'])
        raise

    order.trade_no = (result.get('trade_no') or '')[:_TRADE_NO_MAX]
    # 平台返回的 pay_type 是**支付形态**（qrcode / jump / html），不是调用方选的支付方式；
    # 两者分开存：pay_type 保留调用方的选择（alipay / wxpay …），pay_form 存形态供前端渲染。
    order.pay_form = result.get('pay_type') or ''
    order.pay_info = result.get('pay_info') or ''
    order.save(update_fields=['trade_no', 'pay_form', 'pay_info'])
    return order


# ==================== 查单（兜底 + 对账） ====================

def query_order(order: PayOrder, *, save_state: bool = True) -> PayOrder:
    """主动查单：通知可能丢，查单是兜底；查到已支付就补发货（幂等）"""
    provider = build_provider_for(order.provider_code)
    result = provider.query_order(out_trade_no=order.out_trade_no)

    if result.get('trade_no') and not order.trade_no:
        order.trade_no = result['trade_no'][:_TRADE_NO_MAX]

    if result['state'] == 'paid' and not order.is_paid:
        _mark_paid(order, trade_no=result.get('trade_no') or order.trade_no,
                   money=result.get('money'), buyer='', source='query')

    if save_state:
        order.last_query_at = timezone.now()
        order.save(update_fields=['last_query_at', 'trade_no'])
    return order


# ==================== 回调 ====================

def handle_notify(provider_code: str, params: dict, request=None) -> tuple:
    """处理异步通知：验签 → 留痕 → 找单 → 核金额 → 发货

    :return: (ok, message) —— ok=True 时视图必须返回 `success`，否则平台会一直重推
    """
    raw = '&'.join(f'{k}={v}' for k, v in params.items() if k != 'sign')

    # 先验签、后留痕：该回调接口对外免签名，若不分真假都写 PayNotifyLog，
    # 任何匿名请求都能往留痕表里插行（刷表 / 撑体积）。故**只有通过验签的通知才落库**，
    # 验签失败 / 未知渠道的只记文件日志（error.log 里带原文，仍可排查伪造与配置错误）。
    try:
        provider = build_provider_for(provider_code)
    except PayError as exc:
        logger.warning('支付回调：渠道不可用 provider=%s raw=%s', provider_code, raw[:2000])
        return False, str(exc)

    try:
        verified = provider.verify_notify(params)
    except PayError as exc:
        logger.warning('支付回调：验签异常 provider=%s raw=%s', provider_code, raw[:2000])
        return False, str(exc)
    if not verified:
        logger.warning('支付回调：验签失败 provider=%s ip=%s raw=%s',
                       provider_code, (client_ip(request) if request else ''), raw[:2000])
        return False, '验签失败'

    log = PayNotifyLog.objects.create(
        provider_code=provider_code,
        out_trade_no=(params.get('out_trade_no') or '')[:64],
        trade_no=(params.get('trade_no') or '')[:64],
        raw=raw[:20000],
        verified=True,
        ip=(client_ip(request) if request else ''),
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:255]) if request else '',
    )

    def _fail(message):
        log.message = message[:255]
        log.save(update_fields=['message'])
        return False, message

    parsed = provider.parse_notify(params)
    if not parsed['out_trade_no']:
        return _fail('通知缺少商户订单号')

    order = PayOrder.objects.filter(out_trade_no=parsed['out_trade_no'],
                                    provider_code=provider_code).first()
    if order is None:
        return _fail(f'订单不存在：{parsed["out_trade_no"]}')

    # 金额必须与本地订单一致（防止改价 / 错单）
    notify_money = parse_money(parsed['money'])
    if notify_money is None or notify_money != order.amount:
        return _fail(f'金额不符：通知 {parsed["money"]} / 订单 {order.amount}')

    if parsed['state'] != 'paid':
        log.message = f'非成功状态：{parsed.get("trade_status")}'[:255]
        log.save(update_fields=['message'])
        return True, '非成功状态，已忽略'

    changed = _mark_paid(order, trade_no=parsed['trade_no'] or order.trade_no,
                         money=parsed['money'], buyer=parsed.get('buyer', ''), source='notify')
    log.handled = True
    log.message = ('订单已支付并处理' if changed else '订单此前已处理（幂等跳过）')[:255]
    log.save(update_fields=['handled', 'message'])
    return True, log.message


def _mark_paid(order: PayOrder, *, trade_no: str, money, buyer: str, source: str) -> bool:
    """把订单推进为「已支付」并完成发货（幂等）

    :return: True = 本次真的推进了；False = 之前已处理过（重复通知）
    """
    with transaction.atomic():
        locked = PayOrder.objects.select_for_update().get(pk=order.pk)
        if locked.is_paid:
            return False
        locked.status = PayOrder.STATUS_PAID
        if trade_no:
            locked.trade_no = trade_no[:_TRADE_NO_MAX]
        if buyer:
            locked.buyer = buyer[:128]
        locked.paid_at = timezone.now()
        locked.save(update_fields=['status', 'trade_no', 'buyer', 'paid_at', 'updated_time'])
        # 发货：两种来源口径一致 —— 都把订单金额加到「下单用户」的账户余额上
        if locked.user_id:
            _credit_user_balance(locked)
    logger.info('支付成功 order=%s user=%s app=%s amount=%s source=%s',
                locked.out_trade_no, locked.user_id, locked.app_id, locked.amount, source)
    return True


def _credit_user_balance(order: PayOrder) -> None:
    """给下单用户加余额并写一条流水（调用方已在事务内）"""
    User.objects.filter(pk=order.user_id).update(balance=F('balance') + order.amount)
    balance_after = User.objects.values_list('balance', flat=True).get(pk=order.user_id)
    UserBalanceLedger.objects.create(
        user_id=order.user_id, type=UserBalanceLedger.TYPE_PAY,
        amount=order.amount, balance_after=balance_after, order=order,
        remark=f'在线支付充值（{order.provider_code} {order.out_trade_no}）',
    )


# ==================== 退款 ====================
#
# 两条路径，按**渠道能力**分流（`PayProvider.refund_mode`）：
#   auto   自助退款 —— 调平台退款接口，成功即回写
#   manual 人工受理 —— 平台没给商户开自助退款（易支付当前就是），落一条待办申请，
#                      回复「人工审核后 N 个工作日内退款」，管理员在平台后台退完再回本站标记
# 两个路径**共用同一段回写**（`_apply_refund`），避免订单状态与余额扣回的口径漂移。

def resolve_refund_mode(provider_code: str) -> str:
    """渠道的退款方式（auto 自助 / manual 人工受理）

    渠道配置行缺失时按「人工受理」处理：宁可多走一次人工审核，也不要直接调平台
    换来一句「未开通自助退款」—— 那会让申请人以为这笔钱退不了。
    """
    config = PayProvider.objects.filter(code=(provider_code or '').strip()).first()
    return config.refund_mode if config is not None else PayProvider.REFUND_MANUAL


def refund_notice(days=None) -> str:
    """人工受理的统一告知文案（天数取「支付设置」的配置，随时可在后台调整）"""
    if days is None:
        days = PaySetting.get_solo().refund_notice_days
    return _('退款通道出现问题，人工审核后会在 %(days)s 个工作日内完成退款') % {'days': days}


def refundable_amount(order: PayOrder):
    """订单当前可退金额（单笔口径，公式见 refundable_amounts）"""
    return refundable_amounts([order]).get(order.pk, Decimal('0'))


def refundable_amounts(orders) -> dict:
    """批量算可退金额，返回 `{order_id: Decimal}`

    公式（唯一实现）：可退金额 = 订单金额 − 已退金额 − **其它待人工处理**的申请金额
    最后一项不可少：人工受理的申请在被处理前不会动 `refund_amount`，
    若不算进来，同一笔订单能被反复申请、退超。

    列表页一次要算多笔，故这里一次性聚合（逐笔调 `refundable_amount` 会产生 N+1）。
    """
    orders = list(orders)
    if not orders:
        return {}
    pending = dict(
        PayRefundRequest.objects
        .filter(order__in=[o.pk for o in orders], status=PayRefundRequest.STATUS_PENDING)
        .values_list('order')
        .annotate(total=Sum('amount')))
    return {o.pk: o.amount - o.refund_amount - (pending.get(o.pk) or Decimal('0'))
            for o in orders}


def refund_order(order: PayOrder, amount, *, operator: str = '', source: str = '',
                 user=None, app=None, contact: str = '', remark: str = '') -> tuple:
    """退款统一入口（对外接口 / 前台 / 控制台都走这里）

    :param source: 申请来源（PayRefundRequest.SOURCE_*），人工受理时留痕用
    :return: (mode, obj)
        mode='auto'   → obj 是已回写退款结果的 `PayOrder`
        mode='manual' → obj 是新建的 `PayRefundRequest`（待人工处理）
    """
    if not order.is_paid:
        raise PayError('只有已支付的订单才能退款')

    money = parse_money(amount)
    if money is None or money <= 0:
        raise PayError('退款金额非法')

    # 并发保护：可退金额的校验与「落待办申请」必须在同一把订单行锁内完成。
    # 可退额 = 订单金额 − 已退金额 − 其它**待人工处理**的申请金额（见 refundable_amounts）。
    # 若在锁外先判、再落库，两笔并发申请会各自按同一份「还没有 pending 记录」的旧可退额
    # 通过校验，双双落库导致同一订单被超额受理。放进锁内且先落 pending 申请后，
    # 后一笔会读到前一笔的 pending 金额从而被正确拒绝。
    with transaction.atomic():
        locked = PayOrder.objects.select_for_update().get(pk=order.pk)
        if not locked.is_paid:
            raise PayError('只有已支付的订单才能退款')
        refundable = refundable_amount(locked)
        if money > refundable:
            raise PayError(f'退款金额超过可退金额（可退 {format_money(refundable)} 元）')
        if resolve_refund_mode(locked.provider_code) == PayProvider.REFUND_MANUAL:
            return 'manual', _create_refund_request(
                locked, money, source=source, user=user, app=app,
                contact=contact, remark=remark)

    provider = build_provider_for(order.provider_code)
    result = provider.refund(amount=money, out_trade_no=order.out_trade_no,
                             trade_no=order.trade_no or None)
    return 'auto', _apply_refund(order, money, refund_no=result.get('refund_no', ''),
                                 operator=operator)


def _create_refund_request(order: PayOrder, money, *, source, user, app,
                           contact, remark) -> PayRefundRequest:
    """落一条「待人工处理」的退款申请（不调平台、不动订单与余额）"""
    return PayRefundRequest.objects.create(
        order=order, out_trade_no=order.out_trade_no, provider_code=order.provider_code,
        amount=money, source=source or PayRefundRequest.SOURCE_USER,
        applicant_user=user, applicant_app=app,
        contact=(contact or '')[:128], remark=(remark or '')[:255],
    )


def _apply_refund(order: PayOrder, money, *, refund_no: str, operator: str) -> PayOrder:
    """回写退款结果（自助退款 / 人工标记已退款 共用）

    :param refund_no: 平台退款单号（人工处理时可不填，或填平台后台的退款单号作留痕）
    """
    with transaction.atomic():
        locked = PayOrder.objects.select_for_update().get(pk=order.pk)
        # 兜底：累计退款不得超过订单金额。这是退款回写的**唯一写点**，
        # 自助退款在锁外调平台、并发时可能两笔都进来，这里做最后一道防线。
        if locked.refund_amount + money > locked.amount:
            raise PayError('退款金额超过订单金额，已拒绝（可能为并发退款）')
        locked.refund_amount = locked.refund_amount + money
        locked.status = (PayOrder.STATUS_REFUNDED
                         if locked.refund_amount >= locked.amount
                         else PayOrder.STATUS_PARTIAL_REFUNDED)
        locked.save(update_fields=['refund_amount', 'status', 'updated_time'])
        if locked.user_id:
            _debit_user_balance_on_refund(locked, money, refund_no, operator)
    return locked


def settle_refund_request(refund_request: PayRefundRequest, *, operator: str = '',
                          note: str = '') -> PayOrder:
    """把一条待处理的退款申请标记为「已退款」（管理员已在渠道后台退完钱）

    本站只做记账：推进订单状态、扣回用户余额、写流水 —— 与自助退款走同一段回写。
    """
    with transaction.atomic():
        locked = PayRefundRequest.objects.select_for_update().get(pk=refund_request.pk)
        if not locked.is_pending:
            raise PayError('该退款申请已处理过，不能重复操作')
        order = _apply_refund(PayOrder.objects.get(pk=locked.order_id), locked.amount,
                              refund_no=note, operator=operator)
        locked.status = PayRefundRequest.STATUS_REFUNDED
        locked.operator = operator or ''
        locked.handled_at = timezone.now()
        locked.handle_note = (note or '')[:255]
        locked.save(update_fields=['status', 'operator', 'handled_at', 'handle_note',
                                   'updated_time'])
    logger.info('退款申请已标记退款 request=%s order=%s amount=%s operator=%s',
                locked.pk, locked.out_trade_no, locked.amount, operator)
    return order


def reject_refund_request(refund_request: PayRefundRequest, *, operator: str = '',
                          note: str = '') -> PayRefundRequest:
    """驳回一条待处理的退款申请（订单保持已支付，不动余额）"""
    with transaction.atomic():
        locked = PayRefundRequest.objects.select_for_update().get(pk=refund_request.pk)
        if not locked.is_pending:
            raise PayError('该退款申请已处理过，不能重复操作')
        locked.status = PayRefundRequest.STATUS_REJECTED
        locked.operator = operator or ''
        locked.handled_at = timezone.now()
        locked.handle_note = (note or '')[:255]
        locked.save(update_fields=['status', 'operator', 'handled_at', 'handle_note',
                                   'updated_time'])
    return locked


def _debit_user_balance_on_refund(order: PayOrder, money, refund_no: str, operator: str) -> None:
    """退款扣回用户余额（允许扣成负数：钱可能已被用户花掉，扣不回来就记欠款）"""
    User.objects.filter(pk=order.user_id).update(balance=F('balance') - money)
    balance_after = User.objects.values_list('balance', flat=True).get(pk=order.user_id)
    UserBalanceLedger.objects.create(
        user_id=order.user_id, type=UserBalanceLedger.TYPE_REFUND,
        amount=-money, balance_after=balance_after, order=order, operator=operator or '',
        remark=f'订单退款扣回（{refund_no or order.out_trade_no}）',
    )
