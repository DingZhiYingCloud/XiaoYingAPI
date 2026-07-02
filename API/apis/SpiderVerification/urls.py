# API路由
from django.urls import path, include

# 域名前缀: /api/spider_verification/
urlpatterns = [
    path('sv4759/', include('API.apis.SpiderVerification.SV4759.urls')), # 4759爬虫验证服务路由
]

