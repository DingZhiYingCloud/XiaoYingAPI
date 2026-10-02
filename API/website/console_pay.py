"""超管控制台 · 支付设置

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/pay/    全局设置（开关 / 最低金额 / 人工退款告知天数）
                          + 渠道配置（pid / 密钥 / 网关 / 支付方式 / 退款方式）
                          + 订单列表（可手动查单 / 退款）+ 退款申请（人工受理队列）+ 最近余额流水
    POST /console/pay/    action =
                            save_setting    保存全局设置
                            save_provider   保存某个渠道的商户配置
                            sync_order      对某笔订单手动查单（顺带补发货）
                            refund_order    对某笔订单发起退款
                            settle_refund   把一条待处理的退款申请标记为「已退款」
                            reject_refund   驳回一条待处理的退款申请

**退款的两条路径**：渠道配成「自助退款」时，点退款就调平台接口；配成「人工受理」
（易支付当前就是这样，平台没给商户开自助退款）时，点退款不会报错，而是**登记一条
待退款申请**，你在平台后台把钱退掉后回来点「标记已退款」—— 那一步会把订单状态与
用户余额一起对齐（与自助退款走同一段回写逻辑）。

渠道清单来自 `API/apis/pay/providers/registry.py`（代码侧唯一来源）：这里按它
`get_or_create` 配置行，新增渠道无需改本页。

**密钥一律密文落库、页面不回显**：输入框留空 = 不修改；填了就整体替换（并即时校验能否解析）。
"""
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.apis.pay import service
from API.apis.pay.providers import PROVIDER_CLASSES
from API.apis.pay.providers.base import PayError
from API.apis.pay.providers.registry import pay_type_icon
from API.apis.pay.providers.sign import load_private_key, load_public_key
from API.apis.pay.utils import format_money, parse_money
from API.models import (PayOrder, PayProvider, PayRefundRequest, PaySetting,
                        UserBalanceLedger)

from .admin_auth import notify_success, superadmin_required
from .console_users import _page_prefix

logger = logging.getLogger('api.pay')

REDIRECT_URL = 'website:console_pay'
PAGE_SIZE = 20
LEDGER_ROWS = 20
#: 「退款申请」区块已处理部分的展示条数（待处理的全部列出，通常很少）
REFUND_ROWS = 10


@superadmin_required
def pay_view(request):
    """支付设置页：展示 + 保存 + 订单操作"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save_setting':
            return _save_setting(request)
        if action == 'save_provider':
            return _save_provider(request)
        if action == 'sync_order':
            return _sync_order(request)
        if action == 'refund_order':
            return _refund_order(request)
        if action == 'settle_refund':
            return _settle_refund(request)
        if action == 'reject_refund':
            return _reject_refund(request)
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)
    return _render(request)


def _render(request):
    """渲染：全局设置 + 渠道 + 订单（筛选分页）+ 最近余额流水"""
    setting = PaySetting.get_solo()

    providers = []
    for code, provider_cls in PROVIDER_CLASSES.items():
        config, _created = PayProvider.objects.get_or_create(
            code=code, defaults={'name': provider_cls.name})
        if config.name != provider_cls.name:      # 展示名以代码为准，避免历史配置漂移
            config.name = provider_cls.name
            config.save(update_fields=['name'])
        providers.append({
            'code': code,
            'name': provider_cls.name,
            'gateway_default': provider_cls.default_gateway,
            'config': config,
            'has_private_key': bool(config.private_key_enc),
            'has_platform_key': bool(config.platform_public_key_enc),
            'pay_types': [(value, label, pay_type_icon(value))
                          for value, label in provider_cls.pay_types.items()],
            'selected_methods': config.method_list,
            'supports_auto_refund': config.supports_auto_refund,
        })

    status = (request.GET.get('status') or '').strip()
    provider_code = (request.GET.get('provider') or '').strip()
    keyword = (request.GET.get('q') or '').strip()

    orders = PayOrder.objects.select_related('user', 'app')
    if status:
        orders = orders.filter(status=status)
    if provider_code:
        orders = orders.filter(provider_code=provider_code)
    if keyword:
        orders = orders.filter(Q(out_trade_no__icontains=keyword)
                               | Q(trade_no__icontains=keyword)
                               | Q(subject__icontains=keyword))
    paginator = Paginator(orders, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))

    # 退款申请：待处理的排前面（要人去办），已处理的只留最近几条；拼成一个列表交给模板，
    # 两种状态共用同一套表格行（操作列按 status 决定显示按钮还是处理结果）
    refunds = PayRefundRequest.objects.select_related('order', 'applicant_user', 'applicant_app')
    refund_pending = list(refunds.filter(status=PayRefundRequest.STATUS_PENDING))
    refund_handled = list(refunds.exclude(status=PayRefundRequest.STATUS_PENDING)
                          .order_by('-handled_at')[:REFUND_ROWS])
    return render(request, 'console/pay.html', {
        'setting': setting,
        'providers': providers,
        'page_obj': page,
        'paginator': paginator,
        'total': paginator.count,
        'status_options': PayOrder.STATUS_CHOICES,
        'status_filter': status,
        'provider_filter': provider_code,
        'keyword': keyword,
        'page_prefix': _page_prefix(request),
        'ledgers': (UserBalanceLedger.objects.select_related('user', 'order')
                    .order_by('-create_time')[:LEDGER_ROWS]),
        'ledger_total': UserBalanceLedger.objects.count(),
        'pending_total': PayOrder.objects.filter(status=PayOrder.STATUS_PENDING).count(),
        'refunds': refund_pending + refund_handled,
        'refund_pending_total': len(refund_pending),
    })


# ==================== 保存：全局设置 ====================

def _save_setting(request):
    """保存「开启在线支付 / 最低金额 / 人工退款告知天数」"""
    raw_min = (request.POST.get('min_amount') or '').strip()

    min_amount = parse_money(raw_min or '0')
    if min_amount is None or min_amount < 0:
        messages.error(request, _('最低金额必须是不小于 0 的数字（元，最多两位小数）'))
        return redirect(REDIRECT_URL)

    raw_days = (request.POST.get('refund_notice_days') or '').strip()
    try:
        notice_days = int(raw_days)
    except (TypeError, ValueError):
        notice_days = -1
    if notice_days < 0:
        messages.error(request, _('人工退款告知天数必须是不小于 0 的整数'))
        return redirect(REDIRECT_URL)

    setting = PaySetting.get_solo()
    setting.enabled = request.POST.get('enabled') == 'on'
    setting.min_amount = min_amount
    setting.refund_notice_days = notice_days
    setting.save(update_fields=['enabled', 'min_amount', 'refund_notice_days', 'updated_time'])
    notify_success(request, _('支付设置已保存'))
    return redirect(REDIRECT_URL)


# ==================== 保存：渠道配置 ====================

def _save_provider(request):
    """保存某个渠道的商户配置（启用 / pid / 网关 / 支付方式 / 密钥）"""
    code = (request.POST.get('code') or '').strip()
    provider_cls = PROVIDER_CLASSES.get(code)
    if provider_cls is None:
        messages.error(request, _('渠道不存在：%(code)s') % {'code': code})
        return redirect(REDIRECT_URL)

    config, _created = PayProvider.objects.get_or_create(
        code=code, defaults={'name': provider_cls.name})

    enabled = request.POST.get('enabled') == 'on'
    merchant_id = (request.POST.get('merchant_id') or '').strip()
    gateway = (request.POST.get('gateway') or '').strip()
    remark = (request.POST.get('remark') or '').strip()

    # 密钥：留空 = 不修改；填了就校验能否解析（避免把粘贴错的密钥存进去，到线上才发现签名失败）
    private_key = (request.POST.get('private_key') or '').strip()
    platform_key = (request.POST.get('platform_public_key') or '').strip()
    if private_key:
        try:
            load_private_key(private_key)
        except Exception:
            messages.error(request, _('商户私钥无法解析：请确认复制的是完整私钥（PKCS#8，可带 -----BEGIN----- 头尾）'))
            return redirect(REDIRECT_URL)
    if platform_key:
        try:
            load_public_key(platform_key)
        except Exception:
            messages.error(request, _('平台公钥无法解析：请确认复制的是完整公钥'))
            return redirect(REDIRECT_URL)

    effective_private = private_key or config.private_key
    effective_platform = platform_key or config.platform_public_key
    if enabled and not (merchant_id and effective_private and effective_platform):
        messages.error(request, _('启用渠道前必须填齐：商户ID、商户私钥、平台公钥'))
        return redirect(REDIRECT_URL)

    methods = [key for key in provider_cls.pay_types if request.POST.get(f'method_{code}_{key}') == 'on']

    refund_mode = (request.POST.get('refund_mode') or '').strip()
    valid_modes = {mode for mode, _label in PayProvider.REFUND_MODE_CHOICES}
    if refund_mode not in valid_modes:
        refund_mode = PayProvider.REFUND_AUTO

    config.name = provider_cls.name
    config.enabled = enabled
    config.merchant_id = merchant_id
    config.gateway = gateway
    config.remark = remark
    config.enabled_methods = ','.join(methods)
    config.refund_mode = refund_mode
    if private_key:
        config.set_private_key(private_key)
    if platform_key:
        config.set_platform_public_key(platform_key)
    config.save()

    tail = '' if methods else _('（未勾选支付方式 = 不限制，该渠道全部可用）')
    notify_success(request, _('%(name)s 配置已保存%(tail)s') % {'name': provider_cls.name, 'tail': tail})
    return redirect(REDIRECT_URL)


# ==================== 订单操作 ====================

def _get_order(request):
    """取表单提交的订单（id 缺失 / 非法 UUID / 不存在都返回 None，不抛 500）"""
    order_id = (request.POST.get('order_id') or '').strip()
    if not order_id:
        return None
    try:
        return PayOrder.objects.filter(pk=order_id).first()
    except (ValidationError, ValueError):
        return None


def _sync_order(request):
    """手动查单（通知丢了时的兜底；查到已支付会自动补发货）"""
    order = _get_order(request)
    if order is None:
        messages.error(request, _('订单不存在'))
        return redirect(REDIRECT_URL)
    try:
        service.query_order(order)
    except PayError as exc:
        messages.error(request, _('查单失败：%(msg)s') % {'msg': str(exc)})
        return redirect(REDIRECT_URL)
    order.refresh_from_db()
    notify_success(request, _('查单完成：%(no)s 当前状态为「%(status)s」')
                   % {'no': order.out_trade_no, 'status': order.get_status_display()})
    return redirect(REDIRECT_URL)


def _refund_order(request):
    """手动退款（金额留空 = 退剩余可退金额）

    渠道支持自助退款就当场退掉；不支持则登记一条待退款申请（见模块 docstring）。
    """
    order = _get_order(request)
    if order is None:
        messages.error(request, _('订单不存在'))
        return redirect(REDIRECT_URL)
    amount = (request.POST.get('amount') or '').strip() or service.refundable_amount(order)
    operator = request.user.get_username()
    try:
        mode, obj = service.refund_order(
            order, amount, operator=operator, source=PayRefundRequest.SOURCE_CONSOLE,
            remark=(request.POST.get('remark') or '').strip())
    except PayError as exc:
        messages.error(request, _('退款失败：%(msg)s') % {'msg': str(exc)})
        return redirect(REDIRECT_URL)

    if mode == 'manual':
        notify_success(request, _('已登记退款申请：%(no)s %(money)s 元。该渠道未开通自助退款，'
                                 '请在渠道后台退款后回到本页「退款申请」点「标记已退款」')
                       % {'no': obj.out_trade_no, 'money': format_money(obj.amount)})
        return redirect(REDIRECT_URL)

    obj.refresh_from_db()
    notify_success(request, _('退款已提交：%(no)s 已退 %(money)s 元（累计 %(total)s 元）')
                   % {'no': obj.out_trade_no, 'money': format_money(amount),
                      'total': format_money(obj.refund_amount)})
    return redirect(REDIRECT_URL)


def _get_refund(request):
    """取表单提交的退款申请（id 缺失 / 非法 UUID / 不存在都返回 None，不抛 500）"""
    refund_id = (request.POST.get('refund_id') or '').strip()
    if not refund_id:
        return None
    try:
        return PayRefundRequest.objects.filter(pk=refund_id).first()
    except (ValidationError, ValueError):
        return None


def _settle_refund(request):
    """把一条待处理的退款申请标记为「已退款」（钱已在渠道后台退给用户）

    这一步同时推进订单状态、扣回用户余额并写流水，与自助退款口径一致。
    """
    refund_request = _get_refund(request)
    if refund_request is None:
        messages.error(request, _('退款申请不存在'))
        return redirect(REDIRECT_URL)
    try:
        order = service.settle_refund_request(
            refund_request, operator=request.user.get_username(),
            note=(request.POST.get('note') or '').strip())
    except PayError as exc:
        messages.error(request, _('标记退款失败：%(msg)s') % {'msg': str(exc)})
        return redirect(REDIRECT_URL)
    notify_success(request, _('退款申请已标记退款：%(no)s %(money)s 元（订单累计已退 %(total)s 元）')
                   % {'no': refund_request.out_trade_no,
                      'money': format_money(refund_request.amount),
                      'total': format_money(order.refund_amount)})
    return redirect(REDIRECT_URL)


def _reject_refund(request):
    """驳回一条待处理的退款申请（订单保持已支付，不动余额）"""
    refund_request = _get_refund(request)
    if refund_request is None:
        messages.error(request, _('退款申请不存在'))
        return redirect(REDIRECT_URL)
    try:
        service.reject_refund_request(
            refund_request, operator=request.user.get_username(),
            note=(request.POST.get('note') or '').strip())
    except PayError as exc:
        messages.error(request, _('驳回失败：%(msg)s') % {'msg': str(exc)})
        return redirect(REDIRECT_URL)
    notify_success(request, _('已驳回退款申请：%(no)s %(money)s 元')
                   % {'no': refund_request.out_trade_no,
                      'money': format_money(refund_request.amount)})
    return redirect(REDIRECT_URL)
