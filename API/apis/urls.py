# API路由
from django.urls import path, include

# 域名前缀: /api/
urlpatterns = [
    path('email/', include('API.apis.emails.urls')), # 邮箱服务路由
]

