# 代练丸子 DaiLianWanZi API路由
from django.urls import path

from API.common.views import service_building_view

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

    # 财务 (finance)
    path('user/balance', request.balance_view, name='dlwz_balance'),

    # 商家版 · 我的订单 (business)
    path('business/order-tabs', request.order_tabs_view, name='dlwz_business_order_tabs'),
    path('business/orders', request.business_orders_view, name='dlwz_business_orders'),
    path('business/orders/cancel', request.cancel_order_view, name='dlwz_business_cancel_order'),

    # 商家版 · 发单 (business publish)
    path('business/games', request.games_view, name='dlwz_business_games'),
    path('business/order-options', request.order_options_view, name='dlwz_business_order_options'),
    path('business/orders/publish', request.publish_order_view, name='dlwz_business_publish_order'),

    # 商家版 · 接单大厅 (business hall)
    path('business/hall/search', request.business_search_orders_view, name='dlwz_business_hall_search'),
    path('business/hall/words', request.business_search_words_view, name='dlwz_business_hall_words'),
    path('business/hall/detail', request.business_hall_detail_view, name='dlwz_business_hall_detail'),

    # 商家版 · 接单 (business take)
    path('business/orders/take-password-check', request.business_take_password_check_view,
         name='dlwz_business_take_password_check'),
    path('business/orders/take', request.business_take_order_view, name='dlwz_business_take_order'),

    # 商家版 · 撤销 / 仲裁 (business revoke / arbitrate)
    path('business/orders/revoke', request.business_apply_revocation_view,
         name='dlwz_business_apply_revocation'),
    path('business/orders/revoke/agree', request.business_agree_revocation_view,
         name='dlwz_business_agree_revocation'),
    path('business/orders/revoke/cancel', request.business_cancel_revocation_view,
         name='dlwz_business_cancel_revocation'),
    path('business/orders/arbitrate', request.business_apply_arbitration_view,
         name='dlwz_business_apply_arbitration'),

    # 打手版 (player)：尚未接入，保留前缀并返回「服务建设中」，调用方不会拿到 404
    path('player', service_building_view, name='dlwz_player'),
    path('player/<path:rest>', service_building_view, name='dlwz_player_rest'),
]
