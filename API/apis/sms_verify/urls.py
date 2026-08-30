# 验证码认证服务路由（根目录，未来其他验证码服务在此并列扩展）
from django.urls import path, include

# 域名前缀: /api/sms_verify/
urlpatterns = [
    path('aliyun/', include('API.apis.sms_verify.aliyun.urls')),  # 阿里云验证码认证
]
