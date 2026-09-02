# 用户中心 - 用户 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/user_center/users/
urlpatterns = [
    path('register', request.register_view, name='user_center_register'),  # 注册（两步注册第一步/纯用户名）
    path('login/send', request.send_login_code_view, name='user_center_send_login_code'),  # 发送登录验证码
    path('login', request.login_view, name='user_center_login'),           # 登录（验证码/账号+密码）
    path('logout', request.logout_view, name='user_center_logout'),        # 退出
    path('info', request.info_view, name='user_center_info'),              # 用户信息
    path('verify', request.verify_view, name='user_center_verify'),        # 验证 Token
    path('methods', request.methods_view, name='user_center_methods'),     # 可用注册/登录方式（公开）
    path('verify/email', request.verify_email_view, name='user_center_verify_email'),             # 邮箱验证（链接/验证码，两步注册第二步）
    path('verify/email/resend', request.resend_verify_email_view, name='user_center_verify_email_resend'),  # 重新发送验证邮件
    path('verify/phone', request.verify_phone_view, name='user_center_verify_phone'),             # 手机号验证码（两步注册第二步）
    path('verify/phone/send', request.send_phone_code_view, name='user_center_send_phone_code'),  # 发送手机号短信验证码
]
