# ProxyIP_91http API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/91http/
urlpatterns = [
    path('proxies', request.get_91http_proxies_view, name='proxyip_91http_proxies'),
]
