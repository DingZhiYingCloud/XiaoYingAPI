"""第三方支付 · 对外 API 视图（/api/pay/*）

三个端点都走项目签名认证（`ApiAuthMiddleware`），因此 `request.auth_app` 一定是
「正在调用我们的接入项目」——所有订单查询/退款都按它做归属隔离，**看不到别人的单**。

    POST /api/pay/create   统一下单（返回二维码）
    POST /api/pay/query    订单查询（同时把状态同步回本地订单，已支付会补发货）
    POST /api/pay/refund   订单退款
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.apis.pay import service
from API.apis.pay.providers.base import PayError
from API.apis.pay.utils import client_ip, format_money
from API.common import StatusCode


def _json_response(code, data=None, msg=None):
    """统一响应格式: {"code", "msg", "data"}"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _order_brief(order) -> dict:
    """订单对外视图（不暴露内部主键与归属用户）"""
    return {
        'out_trade_no': order.out_trade_no,
        'trade_no': order.trade_no,
        'provider': order.provider_code,
        'pay_type': order.pay_type,
        'amount': format_money(order.amount),
        'subject': order.subject,
        'status': order.status,
        'pay_info': order.pay_info,
        'param': order.param,
    }


def _find_own_order(request, out_trade_no):
    """按商户订单号取本调用方的订单（别人的单一律视为不存在）"""
    from API.models import PayOrder

    return PayOrder.objects.filter(out_trade_no=out_trade_no,
                                   app_id=getattr(request.auth_app, 'pk', None)).first()


@require_http_methods(['POST'])
def create_view(request):
    """统一下单

    表单参数：
        provider  渠道标识（可选，默认第一个启用的渠道，如 ezfp）
        pay_type  支付方式（必填，alipay / wxpay …）
        amount    金额（必填，元，两位小数）
        subject   商品名称（可选）
        return_url 支付完成后浏览器跳回地址（可选，仅影响用户看到的结果页）
        param     业务扩展参数（可选，回调/查单原样返回）
        method    调用方式（可选，默认 web；**移动端 App 建议 jump**）
        device    设备类型（可选，默认 pc；**移动端建议 mobile / wechat / alipay**）
    返回：{out_trade_no, trade_no, provider, pay_type, amount, subject, status, pay_info, param}

    拿到返回后**按 `pay_type` 渲染**：`qrcode` 直接出二维码；`jump` / `html` 打开 `pay_info`
    地址（移动端 WebView / 系统浏览器打开即可拉起支付）。
    """
    pay_type = (request.POST.get('pay_type') or '').strip()
    amount = (request.POST.get('amount') or '').strip()
    if not pay_type or not amount:
        return _json_response(StatusCode.PARAM_MISSING, msg='pay_type 与 amount 为必填')

    provider_code = (request.POST.get('provider') or '').strip()
    if not provider_code:
        channels = service.available_channels()
        if not channels:
            return _json_response(StatusCode.BUSINESS_RULE_RESTRICTED, msg='当前没有可用的支付渠道')
        provider_code = channels[0].code

    try:
        order = service.create_order(
            provider_code=provider_code, amount=amount, pay_type=pay_type,
            subject=(request.POST.get('subject') or '订单支付').strip(),
            app=request.auth_app, client_ip=client_ip(request), request=request,
            return_url=(request.POST.get('return_url') or '').strip(),
            param=(request.POST.get('param') or '').strip(),
            method=(request.POST.get('method') or 'web').strip(),
            device=(request.POST.get('device') or 'pc').strip(),
        )
    except PayError as exc:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=str(exc))
    return _json_response(StatusCode.SUCCESS, data=_order_brief(order), msg='下单成功')


@require_http_methods(['POST'])
def query_view(request):
    """订单查询（会顺带把平台状态同步回本地订单）

    表单参数：out_trade_no(必填)
    返回：订单信息 + `paid`(是否已支付)
    """
    out_trade_no = (request.POST.get('out_trade_no') or '').strip()
    if not out_trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg='out_trade_no 为必填')

    order = _find_own_order(request, out_trade_no)
    if order is None:
        return _json_response(StatusCode.NOT_FOUND, msg='订单不存在')

    try:
        order = service.query_order(order)
    except PayError as exc:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=str(exc))
    data = _order_brief(order)
    data['paid'] = order.is_paid
    return _json_response(StatusCode.SUCCESS, data=data, msg='查询成功')


@require_http_methods(['POST'])
def refund_view(request):
    """订单退款

    表单参数：out_trade_no(必填)、amount(可选，留空 = 退剩余可退金额)
    返回：订单信息（含 refund_amount）
    """
    out_trade_no = (request.POST.get('out_trade_no') or '').strip()
    if not out_trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg='out_trade_no 为必填')

    order = _find_own_order(request, out_trade_no)
    if order is None:
        return _json_response(StatusCode.NOT_FOUND, msg='订单不存在')

    amount = (request.POST.get('amount') or '').strip() or (order.amount - order.refund_amount)
    try:
        order = service.refund_order(order, amount,
                                     operator=f'app:{request.auth_app.app_id}')
    except PayError as exc:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=str(exc))
    data = _order_brief(order)
    data['refund_amount'] = format_money(order.refund_amount)
    return _json_response(StatusCode.SUCCESS, data=data, msg='退款已提交')
