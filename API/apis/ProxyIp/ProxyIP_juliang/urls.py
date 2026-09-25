# ProxyIP_juliang API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/juliang/
urlpatterns = [
    path('proxies', request.get_juliang_proxies_view, name='proxyip_juliang_proxies'),
]
