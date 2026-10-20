"""第三方支付 · 对外 API 视图（/api/pay/*）

三个端点都走项目签名认证（`ApiAuthMiddleware`），因此 `request.auth_app` 一定是
「正在调用我们的接入项目」——所有订单查询/退款都按它做归属隔离，**看不到别人的单**。

    POST /api/pay/create   统一下单（返回二维码 / 收银台地址）
    POST /api/pay/query    订单查询（同时把状态同步回本地订单，已支付会补发货）
    POST /api/pay/refund   订单退款

**发货口径**：下单时必须传 `user_id`（本站的注册用户 ID），支付成功后**按订单金额给他
的账户余额加钱**（单位：元）。接入项目本身不再有任何额度概念，本接口只是把「代收的钱」
落到你自己用户的账上。
"""
import ipaddress

from django.views.decorators.http import require_http_methods

from API.apis.pay import service
from API.apis.pay.providers.base import PayError
from API.apis.pay.utils import client_ip as detect_client_ip
from API.apis.pay.utils import format_money
from API.common import StatusCode
from API.common.responses import json_response as _json_response
from API.models import PayRefundRequest


def _order_brief(order) -> dict:
    """订单对外视图（不暴露内部主键与归属用户）

    `pay_type` 是**你下单时选的支付方式**（alipay / wxpay …），
    `pay_form` 是**平台决定的支付形态**（qrcode 二维码 / jump 收银台地址 / html 网页表单）——
    前端按 `pay_form` 决定怎么渲染，不要在 `pay_type` 上做判断。
    """
    return {
        'out_trade_no': order.out_trade_no,
        'trade_no': order.trade_no,
        'provider': order.provider_code,
        'pay_type': order.pay_type,
        'pay_form': order.pay_form,
        'amount': format_money(order.amount),
        'subject': order.subject,
        'status': order.status,
        'pay_info': order.pay_info,
        'param': order.param,
    }


def _public_ip(text):
    """把外部传入的 client_ip 归一成公网 IP 字符串；非法 / 内网 / 本机 / 保留地址返回 None

    易支付等上游会把「127.0.0.1 / 内网 / 公共 DNS」当成风险 IP，直接返回
    「系统异常无法完成付款」。故调用方显式传 client_ip 时先在这里拦住。
    """
    try:
        addr = ipaddress.ip_address((text or '').strip())
    except ValueError:
        return None
    if (addr.is_loopback or addr.is_private or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
        return None
    return str(addr)


def _find_own_order(request, out_trade_no):
    """按商户订单号取本调用方的订单（别人的单一律视为不存在）"""
    from API.models import PayOrder

    return PayOrder.objects.filter(out_trade_no=out_trade_no,
                                   app_id=getattr(request.auth_app, 'pk', None)).first()


@require_http_methods(['POST'])
def create_view(request):
    """统一下单

    表单参数：
        user_id   收款用户（必填，本站注册用户 ID：UUID；支付成功后给他的账户余额加本次金额）
        pay_type  支付方式（必填，alipay / wxpay …）
        amount    金额（必填，元，两位小数）
        provider  渠道标识（可选，默认第一个启用的渠道，如 ezfp）
        subject   商品名称（可选）
        return_url 支付完成后浏览器跳回地址（可选，仅影响用户看到的结果页）
        param     业务扩展参数（可选，回调/查单原样返回）
        method    调用方式（可选，默认 web；**移动端 App 建议 jump**）
        device    设备类型（可选，默认 pc；**移动端建议 mobile / wechat / alipay**）
        client_ip 付款人公网 IP（可选）。**服务端代调用时建议显式传真实付款人 IP**：
                  上游支付平台会做风险控制，传入本机 / 内网 / 代理 IP 会被拒成
                  「系统异常无法完成付款」；不传则取请求来源 IP。
    返回：{out_trade_no, trade_no, provider, pay_type, amount, subject, status, pay_info, param}

    拿到返回后**按 `pay_type` 渲染**：`qrcode` 直接出二维码；`jump` / `html` 打开 `pay_info`
    地址（移动端 WebView / 系统浏览器打开即可拉起支付）。
    """
    pay_type = (request.POST.get('pay_type') or '').strip()
    amount = (request.POST.get('amount') or '').strip()
    user_id = (request.POST.get('user_id') or '').strip()
    if not pay_type or not amount or not user_id:
        return _json_response(StatusCode.PARAM_MISSING, msg='user_id、pay_type 与 amount 为必填')

    from django.core.exceptions import ValidationError

    from API.models import User

    try:
        # 用户主键是 UUID，非法取值（不是 UUID 形状）会抛 ValidationError，统一按「不存在」处理
        payer = User.objects.filter(pk=user_id).first()
    except (ValidationError, ValueError):
        payer = None
    if payer is None:
        return _json_response(StatusCode.PARAM_VALUE_INVALID, msg='user_id 对应的用户不存在')

    payer_ip = (request.POST.get('client_ip') or '').strip()
    if payer_ip:
        payer_ip = _public_ip(payer_ip)
        if not payer_ip:
            return _json_response(
                StatusCode.PARAM_VALUE_INVALID,
                msg='client_ip 必须是公网 IP（不能是本机 / 内网 / 保留地址）')
    else:
        payer_ip = detect_client_ip(request)

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
            user=payer, app=request.auth_app, client_ip=payer_ip, request=request,
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

    表单参数：
        out_trade_no  商户订单号（必填）
        amount        退款金额（可选，留空 = 退剩余可退金额）
        contact       联系方式（可选，人工受理时供平台核实）
        remark        申请说明（可选）
    返回：`refund_status` 告诉你是哪种结果 ——
        done            已自助退款完成（`refund_amount` 为本次金额，`refunded_total` 为累计）
        manual_pending  该渠道不支持自助退款，**已受理**，由人工在 N 个工作日内原路退回；
                        `msg` 就是要转达给用户的那句话，`refund_request_id` 是受理单号

    ⚠️ `manual_pending` 属于**成功受理**（HTTP 200 / code 10000），不是失败，别重试 ——
    重复提交不会重复受理（可退金额会被待处理的申请扣减，超出会直接拒绝）。
    """
    out_trade_no = (request.POST.get('out_trade_no') or '').strip()
    if not out_trade_no:
        return _json_response(StatusCode.PARAM_MISSING, msg='out_trade_no 为必填')

    order = _find_own_order(request, out_trade_no)
    if order is None:
        return _json_response(StatusCode.NOT_FOUND, msg='订单不存在')

    amount = (request.POST.get('amount') or '').strip() or service.refundable_amount(order)
    try:
        mode, obj = service.refund_order(
            order, amount, source=PayRefundRequest.SOURCE_API, app=request.auth_app,
            operator=f'app:{request.auth_app.app_id}',
            contact=(request.POST.get('contact') or '').strip(),
            remark=(request.POST.get('remark') or '').strip())
    except PayError as exc:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=str(exc))

    if mode == 'manual':
        return _json_response(StatusCode.SUCCESS, msg=service.refund_notice(), data={
            'out_trade_no': obj.out_trade_no,
            'refund_status': 'manual_pending',
            'refund_amount': format_money(obj.amount),
            'refunded_total': format_money(order.refund_amount),
            'refund_request_id': str(obj.pk),
        })
    data = _order_brief(obj)
    data['refund_status'] = 'done'
    data['refund_amount'] = format_money(obj.refund_amount)
    data['refunded_total'] = format_money(obj.refund_amount)
    return _json_response(StatusCode.SUCCESS, data=data, msg='退款已提交')
