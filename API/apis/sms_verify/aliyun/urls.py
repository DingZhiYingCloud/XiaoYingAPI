# 阿里云验证码认证服务路由
from django.urls import path

from . import request

# 域名前缀: /api/sms_verify/aliyun/
urlpatterns = [
    path('send', request.send_view, name='sms_verify_aliyun_send'),    # 发送短信验证码
    path('check', request.check_view, name='sms_verify_aliyun_check'),  # 核验短信验证码
]
