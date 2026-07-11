# 代练丸子 DaiLianWanZi API路由
from django.urls import path

from . import request

# 域名前缀: /api/dlwz/
urlpatterns = [
    # 认证 (auth)
    path('auth/send-code', request.send_code_view, name='dlwz_send_code'),
    path('auth/login', request.login_view, name='dlwz_login'),

    # 用户 (user)
    path('user/info', request.user_info_view, name='dlwz_user_info'),
    path('user/upload-avatar', request.upload_avatar_view, name='dlwz_upload_avatar'),
    path('user/set-profile', request.set_profile_view, name='dlwz_set_profile'),
    path('user/real-name', request.real_name_view, name='dlwz_real_name'),
    path('user/sign-in', request.sign_in_view, name='dlwz_sign_in'),

    # 订单 (orders)
    path('orders/public', request.orders_public_view, name='dlwz_orders_public'),
    path('orders/search', request.orders_search_view, name='dlwz_orders_search'),
    path('orders/detail', request.order_detail_view, name='dlwz_order_detail'),
    path('orders/publish', request.publish_order_view, name='dlwz_publish_order'),
    path('orders/cancel', request.cancel_order_view, name='dlwz_cancel_order'),

    # 财务 (finance)
    path('user/balance', request.balance_view, name='dlwz_balance'),
]
