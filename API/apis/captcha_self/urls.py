# 自研图形验证码 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/captcha_self/
urlpatterns = [
    path('generate', request.generate_view, name='captcha_self_generate'),  # 生成验证码
    path('verify', request.verify_view, name='captcha_self_verify'),        # 校验验证码
]
