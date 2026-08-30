# 用户中心 - 用户 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/user_center/users/
urlpatterns = [
    path('register', request.register_view, name='user_center_register'),  # 注册
    path('login', request.login_view, name='user_center_login'),           # 登录
    path('logout', request.logout_view, name='user_center_logout'),        # 退出
    path('info', request.info_view, name='user_center_info'),              # 用户信息
    path('verify', request.verify_view, name='user_center_verify'),        # 验证 Token
]
