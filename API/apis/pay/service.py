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
from django.db.models import F
from django.utils import timezone

from API.apis.pay.providers import build_provider
from API.apis.pay.providers.base import PayError
from API.apis.pay.utils import absolute_url, format_money, gen_out_trade_no, parse_money
from API.models import (
    PayNotifyLog,
    PayOrder,
    PayProvider,
    PaySetting,
    User,
    UserApp,
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

    :param user: 本站充值时的下单用户（有值 → 支付成功自动给用户余额加钱）
    :param app:  对外调用时签名认证出的接入项目（有值 → 不改任何余额，仅作归属留痕）
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
    order.pay_type = result.get('pay_type') or pay_type
    order.pay_info = result.get('pay_info') or ''
    order.save(update_fields=['trade_no', 'pay_type', 'pay_info'])
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
    """处理异步通知：留痕 → 验签 → 找单 → 核金额 → 发货

    :return: (ok, message) —— ok=True 时视图必须返回 `success`，否则平台会一直重推
    """
    raw = '&'.join(f'{k}={v}' for k, v in params.items() if k != 'sign')
    log = PayNotifyLog.objects.create(
        provider_code=provider_code,
        out_trade_no=(params.get('out_trade_no') or '')[:64],
        trade_no=(params.get('trade_no') or '')[:64],
        raw=raw[:20000],
        ip=(request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', '')) if request else '',
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:255]) if request else '',
    )

    def _fail(message):
        log.message = message[:255]
        log.save(update_fields=['message'])
        return False, message

    try:
        provider = build_provider_for(provider_code)
    except PayError as exc:
        return _fail(str(exc))

    try:
        if not provider.verify_notify(params):
            return _fail('验签失败')
    except PayError as exc:
        return _fail(str(exc))
    log.verified = True

    parsed = provider.parse_notify(params)
    if not parsed['out_trade_no']:
        return _fail('通知缺少商户订单号')

    order = PayOrder.objects.filter(out_trade_no=parsed['out_trade_no'],
                                    provider_code=provider_code).first()
    if order is None:
        log.verified = True
        return _fail(f'订单不存在：{parsed["out_trade_no"]}')

    # 金额必须与本地订单一致（防止改价 / 错单）
    notify_money = parse_money(parsed['money'])
    if notify_money is None or notify_money != order.amount:
        return _fail(f'金额不符：通知 {parsed["money"]} / 订单 {order.amount}')

    if parsed['state'] != 'paid':
        log.message = f'非成功状态：{parsed.get("trade_status")}'[:255]
        log.save(update_fields=['verified', 'message'])
        return True, '非成功状态，已忽略'

    changed = _mark_paid(order, trade_no=parsed['trade_no'] or order.trade_no,
                         money=parsed['money'], buyer=parsed.get('buyer', ''), source='notify')
    log.handled = True
    log.message = ('订单已支付并处理' if changed else '订单此前已处理（幂等跳过）')[:255]
    log.save(update_fields=['verified', 'handled', 'message'])
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
        # 发货：本站充值给「用户账户余额」加钱；对外调用给「调用项目的点数额度」加点
        if locked.user_id:
            _credit_user_balance(locked)
        elif locked.app_id:
            _credit_app_points(locked)
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


def _credit_app_points(order: PayOrder) -> None:
    """给「调用项目的点数额度」充值（对外下单，支付成功后按汇率换算成点数）

    金额是钱、点数是额度，两者按 PaySetting.points_per_yuan 换算；
    流水走项目额度流水（AppCreditLedger），备注标注来源订单，便于对账。
    """
    from API.common.credit_guard import recharge as recharge_app
    from API.models import UserApp

    setting = PaySetting.get_solo()
    points = (order.amount * Decimal(str(setting.points_per_yuan))).quantize(Decimal('0.0001'))
    if points <= 0:
        return
    app = UserApp.objects.filter(pk=order.app_id).first()
    if app is None:
        return
    recharge_app(app, points, operator='pay',
                 remark=f'在线支付充值（{order.provider_code} {order.out_trade_no}）')


# ==================== 退款 ====================

def refund_order(order: PayOrder, amount, *, operator: str = '') -> PayOrder:
    """发起退款并回写订单（金额单位为元；不支持部分金额退款的渠道由平台报错）"""
    if not order.is_paid:
        raise PayError('只有已支付的订单才能退款')

    money = parse_money(amount)
    if money is None or money <= 0:
        raise PayError('退款金额非法')
    refundable = order.amount - order.refund_amount
    if money > refundable:
        raise PayError(f'退款金额超过可退金额（可退 {format_money(refundable)} 元）')

    provider = build_provider_for(order.provider_code)
    result = provider.refund(amount=money, out_trade_no=order.out_trade_no,
                             trade_no=order.trade_no or None)

    with transaction.atomic():
        locked = PayOrder.objects.select_for_update().get(pk=order.pk)
        locked.refund_amount = locked.refund_amount + money
        locked.status = (PayOrder.STATUS_REFUNDED
                         if locked.refund_amount >= locked.amount
                         else PayOrder.STATUS_PARTIAL_REFUNDED)
        locked.save(update_fields=['refund_amount', 'status', 'updated_time'])
        if locked.user_id:
            _debit_user_balance_on_refund(locked, money, result.get('refund_no', ''), operator)
    return locked


def _debit_user_balance_on_refund(order: PayOrder, money, refund_no: str, operator: str) -> None:
    """退款扣回用户余额（允许扣成负数：钱可能已被兑换成项目点数，扣不回来就记欠款）"""
    User.objects.filter(pk=order.user_id).update(balance=F('balance') - money)
    balance_after = User.objects.values_list('balance', flat=True).get(pk=order.user_id)
    UserBalanceLedger.objects.create(
        user_id=order.user_id, type=UserBalanceLedger.TYPE_REFUND,
        amount=-money, balance_after=balance_after, order=order, operator=operator or '',
        remark=f'订单退款扣回（{refund_no or order.out_trade_no}）',
    )


# ==================== 用户余额 → 项目点数 ====================

def transfer_to_app_points(user: User, app: UserApp, amount, *, operator: str = '') -> tuple:
    """把用户账户余额（元）按汇率兑换成某个接入项目的点数（额度）

    :return: (ok, message, data) —— 成功时 data 含 points / user_balance / app_balance
    """
    setting = PaySetting.get_solo()
    money = parse_money(amount)
    if money is None or money <= 0:
        return False, '兑换金额非法', None

    points = (money * Decimal(str(setting.points_per_yuan))).quantize(Decimal('0.0001'))
    if points <= 0:
        return False, '兑换点数不足，请提高金额', None

    from API.common.credit_guard import recharge as recharge_app

    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        if locked_user.balance < money:
            return False, f'账户余额不足（当前 {format_money(locked_user.balance)} 元）', None
        User.objects.filter(pk=user.pk).update(balance=F('balance') - money)
        balance_after = User.objects.values_list('balance', flat=True).get(pk=user.pk)
        UserBalanceLedger.objects.create(
            user_id=user.pk, type=UserBalanceLedger.TYPE_TRANSFER,
            amount=-money, balance_after=balance_after, app=app, points=points,
            operator=operator or '',
            remark=f'兑换项目点数 {points} 点 → {app.name}',
        )
        recharge_app(app, points, operator=operator or 'user',
                     remark=f'账户余额兑换（{money} 元 × {setting.points_per_yuan}）')

    return True, '兑换成功', {
        'points': points, 'user_balance': balance_after, 'app_balance': app.balance,
    }
