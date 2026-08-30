# 图形认证集成服务路由（根目录，未来其他图形认证服务在此并列扩展）
from django.urls import path, include

# 域名前缀: /api/captcha_auth/
urlpatterns = [
    path('aliyun/', include('API.apis.captcha_auth.aliyun.urls')),  # 阿里云图形认证集成
]
