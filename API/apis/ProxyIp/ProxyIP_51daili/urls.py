# ProxyIP_51daili API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/51daili/
urlpatterns = [
    path('proxies', request.get_51daili_proxies_view, name='proxyip_51daili_proxies'),
]
