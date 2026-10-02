# 第三方支付服务路由
from django.urls import path

from . import request

# 域名前缀: /api/pay/
# 三个端点均为「需签名」的对外接口（服务策略由 /console/services/ 维护）；
# 异步通知不走这里（它必须免签名），挂在 /pay/notify/<渠道>/ 见 API/website/urls.py。
urlpatterns = [
    path('create', request.create_view, name='pay_create'),   # 统一下单（返回二维码）
    path('query', request.query_view, name='pay_query'),      # 订单查询（顺带同步状态）
    path('refund', request.refund_view, name='pay_refund'),   # 订单退款
]
