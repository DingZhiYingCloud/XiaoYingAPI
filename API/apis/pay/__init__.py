"""第三方支付服务（对外 API + 本站充值共用的底层）

目录结构（**新增一个支付渠道只要动两处**，见 `providers/registry.py`）：

    urls.py          对外路由：/api/pay/create|query|refund（走项目签名 + 额度）
    request.py       上述三个视图（薄薄一层：参数校验 → 调 service → 统一 JSON）
    notify.py        异步通知入口（免签名，挂 /pay/notify/<code>/，靠平台公钥验签）
    service.py       服务层：下单 / 查单 / 退款 / 发货（本站充值页与对外接口都走它）
    providers/       渠道实现（与 /api/ 解耦，只依赖模型与 requests）

设计要点：
    · 所有金额都是「元、两位小数字符串」，绝不用 float 计算；
    · 订单状态只由「异步通知 + 主动查单」推进，页面跳转（return_url）不算数；
    · 发货（给用户余额加钱）只在订单首次变为「已支付」时执行一次，靠数据库
      条件更新保证幂等。
"""
