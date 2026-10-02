"""第三方支付服务 - 接口文档与在线调试数据

数据与 API/apis/pay/ 实际实现对齐（服务策略 /api/pay/ 未配置显式策略，
按全局兜底 fail-closed 处理 = 需要项目签名）：

- 下单：`service.create_order()` → 渠道实现 `EzfpProvider.create_order()`
- 查单：`service.query_order()`（顺带把平台状态同步回本站订单，已支付补发货）
- 退款：`service.refund_order()`

**支付形态由平台返回的 `pay_type` 决定**（不是我们指定的）：
`qrcode` = 二维码内容，`jump` = 收银台跳转地址。文档里如实说明，避免调用方硬编码。
"""
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec,
                     ServiceSpec)


def _options(pairs, blank='不传（默认）'):
    """下拉选项：[('值', '标签'), ...] → [{value, label}]，首项为「不传」"""
    return [{'value': '', 'label': blank}] + [{'value': v, 'label': l} for v, l in pairs]


#: 支付方式（与 EzfpProvider.pay_types 一致；实际可用以商户用户组启用的为准）
_PAY_TYPES = _options([
    ('alipay', '支付宝'),
    ('wxpay', '微信支付'),
    ('qqpay', 'QQ钱包'),
    ('bank', '网银支付'),
    ('jdpay', '京东支付'),
    ('paypal', 'PayPal'),
    ('usdt', '泰达币（USDT-TRC20）'),
    ('stripepay', '银行卡/钱包（Stripe）'),
    ('stripealipay', 'Stripe 支付宝'),
    ('stripewxpay', 'Stripe 微信支付'),
], blank='请选择')

#: 调用方式（与 EzfpProvider.methods 一致）
_METHODS = _options([
    ('web', 'web=通用网页支付'),
    ('jump', 'jump=跳转支付'),
    ('jsapi', 'jsapi=小程序内支付'),
    ('app', 'app=APP 支付'),
    ('scan', 'scan=付款码支付'),
    ('applet', 'applet=小程序支付'),
], blank='不传（默认 web）')

#: 设备类型（与 EzfpProvider.devices 一致）
_DEVICES = _options([
    ('pc', 'pc=电脑浏览器'),
    ('mobile', 'mobile=手机浏览器'),
    ('qq', 'qq=手机 QQ 内'),
    ('wechat', 'wechat=微信内浏览器'),
    ('alipay', 'alipay=支付宝客户端'),
], blank='不传（默认 pc）')

#: 三个端点共用的响应字段（data 内部）
_ORDER_FIELDS = [
    ResponseFieldSpec('out_trade_no', 'string', '商户订单号（本站生成，查询 / 退款都用它）'),
    ResponseFieldSpec('trade_no', 'string', '平台订单号（部分渠道下单时为空，付款后才有）'),
    ResponseFieldSpec('provider', 'string', '渠道标识，当前为 ezfp'),
    ResponseFieldSpec('pay_type', 'string', '支付形态：qrcode=二维码内容 / jump=收银台地址'),
    ResponseFieldSpec('amount', 'string', '金额（元，两位小数）'),
    ResponseFieldSpec('subject', 'string', '商品名称'),
    ResponseFieldSpec('status', 'string',
                      '订单状态：pending 待支付 / paid 已支付 / partial_refunded 部分退款 / '
                      'refunded 已退款 / failed 下单失败 / closed 已关闭'),
    ResponseFieldSpec('pay_info', 'string', '支付参数：pay_type=qrcode 时是二维码内容，jump 时是收银台地址'),
    ResponseFieldSpec('param', 'string', '业务扩展参数，原样返回'),
]

_ORDER_EXAMPLE = '''{
  "out_trade_no": "XY20261002120000123456",
  "trade_no": "2026100222001412345678",
  "provider": "ezfp",
  "pay_type": "qrcode",
  "amount": "1.00",
  "subject": "账户充值",
  "status": "pending",
  "pay_info": "weixin://wxpay/bizpayurl?pr=AbCdEfG",
  "param": ""
}'''

_QUERY_EXAMPLE = '''{
  "out_trade_no": "XY20261002120000123456",
  "trade_no": "2026100222001412345678",
  "provider": "ezfp",
  "pay_type": "qrcode",
  "amount": "1.00",
  "subject": "账户充值",
  "status": "paid",
  "pay_info": "weixin://wxpay/bizpayurl?pr=AbCdEfG",
  "param": "",
  "paid": true
}'''

_REFUND_EXAMPLE = '''{
  "out_trade_no": "XY20261002120000123456",
  "trade_no": "2026100222001412345678",
  "provider": "ezfp",
  "pay_type": "qrcode",
  "amount": "1.00",
  "subject": "账户充值",
  "status": "refunded",
  "pay_info": "weixin://wxpay/bizpayurl?pr=AbCdEfG",
  "param": "",
  "refund_amount": "1.00"
}'''


SERVICE = ServiceSpec(
    slug='pay',
    name='第三方支付',
    prefix='/api/pay/',
    summary='统一下单 / 订单查询 / 订单退款三件套。支持支付宝、微信、QQ 钱包等支付方式，'
            'PC 与移动端通用：按返回的 pay_type 渲染二维码或打开收银台地址即可。',
    keywords='支付接口,聚合支付API,扫码支付接口,支付宝微信支付,第三方支付接口',
    intro=[
        '支付服务把「下单 → 用户付款 → 到账 / 发货」这条链路收敛成三个接口：'
        '`/api/pay/create` 下单拿到支付参数，`/api/pay/query` 查询并同步订单状态，'
        '`/api/pay/refund` 退款。调用方不需要对接各支付平台的协议与签名。',
        '**支付结果只认异步回调与主动查单，页面跳转不算**：用户付款完成后，平台会异步通知本站，'
        '本站校验签名与金额后推进订单（给调用项目的点数余额充值）；通知偶有丢失，'
        '因此调用方可在支付后轮询 `query` 接口兜底，两边都能触发且**只会发货一次**。',
        '**PC 与移动端同一条路**：支付形态由平台按 `method` / `device` 返回 ——'
        '`pay_info` 直接在页面渲染即可（`qrcode` 出二维码，`jump` 打开收银台地址）。'
        '移动端 H5 / 内嵌 WebView 用 `method=jump` + `device=mobile`，'
        '原生 App 内唤起用 `method=app`，微信内用 `device=wechat`。',
    ],
    channels=[
        ChannelSpec(
            slug='ezfp',
            name='易支付',
            provider='ezfp.cn（聚合支付网关，RSA 签名）',
            auth_note='auth',
            note='聚合支付网关，网关地址与商户凭据（商户 ID + 商户私钥 + 平台公钥）由本站后台'
                 '「支付设置」维护，调用方无需也不应持有。下单的 `notify_url` 由本站固定为'
                 '`/pay/notify/ezfp/`，调用方不需要传。'
                 '实际可用的支付方式取决于商户用户组开通了哪些，未开通的方式下单时平台会直接报错。',
            endpoints=[
                EndpointSpec(
                    'create', '统一下单', 'POST', '/api/pay/create',
                    summary='创建一笔支付订单，返回支付参数（二维码内容或收银台跳转地址）与商户订单号。',
                    params=[
                        ParamSpec('pay_type', '支付方式', kind='select', required=True,
                                  options=_PAY_TYPES,
                                  desc='必填。与商户用户组开通的方式一致，否则平台报错'),
                        ParamSpec('amount', '金额（元）', kind='text', required=True,
                                  placeholder='如 1.00',
                                  desc='必填。大于 0 的数字，两位小数；不得低于后台设置的单笔最低金额'),
                        ParamSpec('provider', '支付渠道', kind='text',
                                  desc='选填。不传则用第一个启用的渠道（当前仅 ezfp）'),
                        ParamSpec('subject', '商品名称', kind='text', placeholder='如 会员充值',
                                  desc='选填。用户在收银台看到的商品名，不传则用「订单支付」'),
                        ParamSpec('return_url', '支付完成跳回地址', kind='text',
                                  placeholder='https://your-site.com/pay/result',
                                  desc='选填。只影响用户付款后浏览器跳回哪里，**不参与到账判定**'),
                        ParamSpec('param', '业务扩展参数', kind='text',
                                  desc='选填。原样回传，便于对账时把订单与自己系统的业务单关联起来'),
                        ParamSpec('method', '调用方式', kind='select', options=_METHODS,
                                  desc='选填。移动端 H5 / WebView 建议 jump；原生 App 用 app'),
                        ParamSpec('device', '设备类型', kind='select', options=_DEVICES,
                                  desc='选填。移动端建议 mobile，微信内 wechat'),
                    ],
                    notes=[
                        '拿到返回后**按 `pay_type` 渲染**：`qrcode` 直接把 `pay_info` 做成二维码；'
                        '`jump` 用浏览器 / WebView 打开 `pay_info`（收银台页自带二维码与付款入口）。'
                        '实测同一笔微信支付在 `method=web` 下返回 `qrcode`，'
                        '在 `method=jump` 下返回 https 收银台地址，故**不要硬编码某一种形态**。',
                        '**到账只认异步回调与主动查单**：`return_url` 的页面跳转只代表用户看到了结果页，'
                        '不能作为发货依据；请以 `query` 接口的 `paid` 或本站异步通知后的余额变化为准。',
                        '**只扣一次**：同一订单重复回调 / 回调与查单同时命中时，'
                        '本站用行锁 + 状态判断保证发货只发生一次。',
                        '**移动端无需自备二维码库**：用 `method=jump` 时返回的是普通网页地址，'
                        'PC 浏览器、手机浏览器、WebView 都能直接打开。',
                        '**下单本身不消耗项目点数**（本服务单价为 0 点/次），'
                        '因此余额为 0 的项目也能调用本接口给自己的项目充值。',
                    ],
                    response_fields=_ORDER_FIELDS,
                    response_example=_ORDER_EXAMPLE,
                ),
                EndpointSpec(
                    'query', '订单查询', 'POST', '/api/pay/query',
                    summary='按商户订单号查询订单，并把平台最新状态同步回本站（已支付会补发货）。',
                    params=[
                        ParamSpec('out_trade_no', '商户订单号', kind='text', required=True,
                                  desc='必填。下单接口返回的 out_trade_no'),
                    ],
                    notes=[
                        '只能查**本调用方自己**下的单：订单按 APPID 归属隔离，别人的单一律返回「订单不存在」。',
                        '查到平台已支付且本站订单还没推进时，本接口会**当场补发货**'
                        '（按后台汇率给调用项目加点数），因此「回调没收到」也能靠轮询查单兜底。',
                        '已下单后建议每 3～5 秒查一次，直到 `paid=true` 或超时；'
                        '不必高频轮询，平台侧订单状态不会瞬间多次跳变。',
                    ],
                    response_fields=_ORDER_FIELDS + [
                        ResponseFieldSpec('paid', 'bool', '是否已支付（true 时订单已推进并发货）'),
                    ],
                    response_example=_QUERY_EXAMPLE,
                ),
                EndpointSpec(
                    'refund', '订单退款', 'POST', '/api/pay/refund',
                    summary='对已支付的订单发起退款；`amount` 留空表示退回剩余可退金额。',
                    params=[
                        ParamSpec('out_trade_no', '商户订单号', kind='text', required=True,
                                  desc='必填。要退款的订单号'),
                        ParamSpec('amount', '退款金额（元）', kind='text',
                                  placeholder='留空=全额退剩余',
                                  desc='选填。不得大于可退金额（订单金额 − 已退金额）'),
                    ],
                    notes=[
                        '只能退**本调用方自己**的订单。退款是否支持分笔、到账时长由支付平台与渠道决定，'
                        '本接口只负责提交并把结果回写订单。',
                        '退款成功后本站订单状态变为 `refunded`（部分退款为 `partial_refunded`），'
                        '累计退款额记在 `refund_amount`。',
                        '⚠️ **已充进调用项目点数的订单退款，点数不会自动扣回** ——'
                        '需要人工核账时请联系本站管理员。',
                    ],
                    response_fields=_ORDER_FIELDS + [
                        ResponseFieldSpec('refund_amount', 'string', '累计已退款金额（元）'),
                    ],
                    response_example=_REFUND_EXAMPLE,
                ),
            ],
        ),
    ],
)
