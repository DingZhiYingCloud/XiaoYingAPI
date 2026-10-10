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
    path('user/balance', request.balance_view, name='dlt_balance'),

    # 游戏 (games)
    path('games', request.games_view, name='dlt_games'),
    path('games/orders', request.games_orders_view, name='dlt_games_orders'),

    # 搜索 (search)
    path('search/orders', request.search_orders_view, name='dlt_search_orders'),
    path('search/hot-words', request.hot_search_words_view, name='dlt_hot_search_words'),

    # 订单 (orders)
    path('orders/receive', request.receive_order_view, name='dlt_receive_order'),
    path('orders/receive-default', request.receive_order_default_view,
         name='dlt_receive_order_default'),
    path('orders/publish', request.publish_order_view, name='dlt_publish_order'),
    path('orders/apply-cancel', request.apply_cancel_view, name='dlt_apply_cancel_order'),
    path('orders/handle-cancel', request.handle_cancel_view, name='dlt_handle_cancel_order'),
    path('orders/delete', request.delete_order_view, name='dlt_delete_order'),
    path('orders/my', request.my_orders_view, name='dlt_my_orders'),
    path('orders/detail', request.order_detail_view, name='dlt_order_detail'),
    path('orders/owner-info', request.owner_info_view, name='dlt_owner_info'),
    path('orders/upload-image', request.upload_image_view, name='dlt_upload_image'),
    path('orders/upload-first-image', request.upload_first_image_view, name='dlt_upload_first_image'),
    path('orders/upload-end-image', request.upload_end_image_view, name='dlt_upload_end_image'),

    # 头像 (avatar)
    path('avatar/upload', request.upload_avatar_view, name='dlt_upload_avatar'),
]
