"""前台「充值中心」—— 登录用户给自己充值 + 兑换项目点数

页面：
    GET  /my/wallet/     余额 / 充值表单 / 待支付订单（含支付入口）/ 充值记录 / 兑换入口
    POST /my/wallet/     action = create_order  下单（成功后跳转平台收银台）
                                 check_order   手动查单（轮询 / 「我已支付」按钮，回 JSON）
                                 transfer      账户余额兑换成某个项目的点数

鉴权：官网会话（复用 `my_projects.login_required`），未登录跳 `/login/?next=`。

口径（与 `API/apis/pay/service.py` 一致，这里只做展示与编排）：
    · 下单固定 **method=jump + device=pc**：平台返回收银台跳转地址，**收银台页自带二维码**，
      PC 与手机浏览器都能直接打开（实测支付宝 / 微信均返回 jump）；因此本站不需要自备二维码库。
    · **到账只认异步回调 + 主动查单**，页面跳转不算：支付完平台跳回本页后，页面加载时会对
      「最近一笔待支付订单」做一次主动查单（带 10 秒节流），避免回调稍晚导致用户以为没到账。
    · 兑换只允许换成**自己名下**项目的点数，汇率取控制台「支付设置」里的值。
"""
import logging

from django.contrib import messages
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from API.apis.pay import service
from API.apis.pay.providers.base import PayError
from API.apis.pay.utils import absolute_url, client_ip, format_money, parse_money
from API.models import PayOrder, PayProvider, PaySetting, UserApp, UserBalanceLedger

from .my_projects import login_required

logger = logging.getLogger('api.pay')

#: 页面加载时对「待支付订单」自动查单的时间窗与节流
AUTO_QUERY_WINDOW_MINUTES = 60
AUTO_QUERY_THROTTLE_SECONDS = 10

#: 记录显示条数
LEDGER_ROWS = 20
ORDER_ROWS = 10

#: 充值金额快捷档位（元）
AMOUNT_PRESETS = ('10', '50', '100', '200', '500', '1000')


def _recharge_methods() -> list:
    """可用的支付方式（取第一个启用渠道的「已启用支付方式」，未限制则给主流的两个）

    返回 [(value, label)]，供充值表单的单选；渠道不可用时返回空列表（页面提示去后台开启）。
    """
    from API.apis.pay.providers import PROVIDER_CLASSES

    for config in service.available_channels():
        provider_cls = PROVIDER_CLASSES.get(config.code)
        if provider_cls is None:
            continue
        allowed = config.method_list or list(provider_cls.pay_types)
        rows = [(value, label) for value, label in provider_cls.pay_types.items() if value in allowed]
        if rows:
            # 常用两种排前面，其余按渠道声明顺序
            rows.sort(key=lambda kv: 0 if kv[0] in ('alipay', 'wxpay') else 1)
            return rows
    return []


def _summary(user) -> dict:
    """余额与累计数据（累计充值 = 支付充值流水之和；已兑换 = 兑换流水绝对值之和）"""
    balance = user.balance
    paid = (UserBalanceLedger.objects.filter(user=user, type=UserBalanceLedger.TYPE_PAY)
            .aggregate(total=Sum('amount'))['total']) or 0
    transferred = (UserBalanceLedger.objects.filter(user=user, type=UserBalanceLedger.TYPE_TRANSFER)
                   .aggregate(total=Sum('amount'))['total']) or 0
    return {
        'balance': balance,
        'total_recharged': paid,
        'total_transferred': abs(transferred),
    }


def _sync_pending_order(user):
    """页面加载时对最近一笔待支付订单做一次主动查单（回调晚到时也能及时到账）

    任何异常都不影响页面渲染：平台不可用时静默跳过，用户仍可点「我已支付，刷新状态」。
    """
    from datetime import timedelta

    from django.utils import timezone

    order = (PayOrder.objects.filter(user=user, status=PayOrder.STATUS_PENDING)
             .order_by('-create_time').first())
    if order is None:
        return
    if order.create_time < timezone.now() - timedelta(minutes=AUTO_QUERY_WINDOW_MINUTES):
        return
    if (order.last_query_at
            and (timezone.now() - order.last_query_at).total_seconds() < AUTO_QUERY_THROTTLE_SECONDS):
        return
    try:
        service.query_order(order)
    except Exception:
        logger.warning('充值页自动查单失败（不影响页面）: %s', order.out_trade_no, exc_info=True)


@login_required
def wallet_view(request, user):
    """充值中心：展示 + 下单 / 查单 / 兑换"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'create_order':
            return _create_order(request, user)
        if action == 'check_order':
            return _check_order(request, user)
        if action == 'transfer':
            return _transfer(request, user)
        messages.error(request, _('不支持的操作'))
        return redirect('website:my_wallet')

    _sync_pending_order(user)
    user.refresh_from_db(fields=['balance'])

    setting = PaySetting.get_solo()
    pending = (PayOrder.objects.filter(user=user, status=PayOrder.STATUS_PENDING)
               .order_by('-create_time').first())
    return render(request, 'my_wallet/index.html', {
        'summary': _summary(user),
        'setting': setting,
        'methods': _recharge_methods(),
        'amount_presets': AMOUNT_PRESETS,
        'pending_order': pending,
        'orders': PayOrder.objects.filter(user=user).order_by('-create_time')[:ORDER_ROWS],
        'ledgers': (UserBalanceLedger.objects.filter(user=user)
                    .order_by('-create_time')[:LEDGER_ROWS]),
        'apps': UserApp.objects.filter(owner=user),
    })


def _create_order(request, user):
    """下单并**直接跳转平台收银台**（方案 A：收银台页自带二维码，PC / 手机都能打开）"""
    amount = (request.POST.get('amount') or '').strip()
    pay_type = (request.POST.get('pay_type') or '').strip()

    methods = dict(_recharge_methods())
    if not methods:
        messages.error(request, _('当前没有可用的支付渠道，请稍后再试或联系管理员'))
        return redirect('website:my_wallet')
    if pay_type not in methods:
        messages.error(request, _('请选择支付方式'))
        return redirect('website:my_wallet')

    try:
        order = service.create_order(
            provider_code=service.available_channels()[0].code,
            amount=amount, pay_type=pay_type,
            subject=_('账户充值'), user=user,
            client_ip=client_ip(request), request=request,
            return_url=absolute_url(request, reverse('website:my_wallet')),
            method='jump', device='pc',
        )
    except PayError as exc:
        messages.error(request, _('下单失败：%(msg)s') % {'msg': str(exc)})
        return redirect('website:my_wallet')

    if not order.pay_info:
        messages.error(request, _('下单成功但平台没有返回支付地址，请稍后在下方订单里重试'))
        return redirect('website:my_wallet')
    # 直接跳收银台（支付完成后平台按 return_url 跳回本页，再由自动查单确认到账）。
    # 只对 http(s) 地址跳转：部分渠道可能回 weixin:// 这类非网页地址（浏览器跳不了，
    # Django 也会以 400 拒绝），此时留在本页让用户从订单卡片继续。
    if order.pay_info.startswith(('http://', 'https://')):
        return redirect(order.pay_info)
    messages.info(request, _('已生成支付参数，请在下方订单里继续支付'))
    return redirect('website:my_wallet')


def _check_order(request, user):
    """手动查单（「我已支付，刷新状态」按钮 / 轮询用），返回 JSON"""
    out_trade_no = (request.POST.get('out_trade_no') or '').strip()
    order = PayOrder.objects.filter(out_trade_no=out_trade_no, user=user).first()
    if order is None:
        return JsonResponse({'code': 404, 'msg': _('订单不存在'), 'data': None})

    try:
        service.query_order(order)
    except PayError as exc:
        return JsonResponse({'code': 40001, 'msg': str(exc), 'data': None})

    order.refresh_from_db()
    user.refresh_from_db(fields=['balance'])
    return JsonResponse({
        'code': 10000,
        'msg': _('查询完成'),
        'data': {
            'out_trade_no': order.out_trade_no,
            'status': order.status,
            'status_display': str(order.get_status_display()),
            'paid': order.is_paid,
            'balance': format_money(user.balance),
        },
    })


def _transfer(request, user):
    """账户余额（元）按汇率兑换成自己名下某个项目的点数"""
    app = UserApp.objects.filter(pk=(request.POST.get('app_id') or '').strip(), owner=user).first()
    if app is None:
        messages.error(request, _('请选择要兑换的项目'))
        return redirect('website:my_wallet')

    amount = parse_money((request.POST.get('amount') or '').strip())
    if amount is None or amount <= 0:
        messages.error(request, _('兑换金额非法'))
        return redirect('website:my_wallet')

    ok, message, data = service.transfer_to_app_points(user, app, amount)
    if not ok:
        messages.error(request, message)
        return redirect('website:my_wallet')
    messages.success(request, _('已兑换：%(money)s 元 → 「%(app)s」%(points)s 点（当前项目余额 %(balance)s 点）')
                     % {'money': format_money(amount), 'app': app.name,
                        'points': data['points'], 'balance': data['app_balance']})
    return redirect('website:my_wallet')
