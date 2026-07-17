# ProxyIP_66daili API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/66daili/
urlpatterns = [
    path('proxies', request.get_proxies_view, name='proxyip_66daili_proxies'),
]
