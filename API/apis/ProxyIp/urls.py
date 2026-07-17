# API路由
from django.urls import path, include

# 域名前缀: /api/ProxyIp/
urlpatterns = [
    path('66daili/', include('API.apis.ProxyIp.ProxyIP_66daili.urls')),  # 66免费代理IP
]