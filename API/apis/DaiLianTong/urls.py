# 代练通 DaiLianTong API路由
from django.urls import path

from . import request

# 域名前缀: /api/dlt/
urlpatterns = [
    # 认证 (auth)
    path('auth/send-code', request.send_code_view, name='dlt_send_code'),
    path('auth/register', request.register_view, name='dlt_register'),
    path('auth/login', request.login_view, name='dlt_login'),

    # 用户 (user)
    path('user/info', request.user_info_view, name='dlt_user_info'),
    path('user/set-contact', request.set_contact_view, name='dlt_set_contact'),
    path('user/set-mysign', request.set_mysign_view, name='dlt_set_mysign'),
    path('user/change-password', request.change_password_view, name='dlt_change_password'),
    path('user/sign-in', request.sign_in_view, name='dlt_sign_in'),
    path('user/real-name-info', request.real_name_info_view, name='dlt_real_name_info'),

    # 订单 (orders)
    path('orders/public', request.orders_public_view, name='dlt_orders_public'),
    path('orders/detail', request.order_detail_view, name='dlt_order_detail'),
    path('orders/receive', request.receive_order_view, name='dlt_receive_order'),
    path('orders/publish', request.publish_order_view, name='dlt_publish_order'),
    path('orders/delete', request.delete_order_view, name='dlt_delete_order'),
    path('orders/my', request.my_orders_view, name='dlt_my_orders'),
    path('orders/upload-image', request.upload_image_view, name='dlt_upload_image'),

    # 头像 (avatar)
    path('avatar/upload', request.upload_avatar_view, name='dlt_upload_avatar'),
]
