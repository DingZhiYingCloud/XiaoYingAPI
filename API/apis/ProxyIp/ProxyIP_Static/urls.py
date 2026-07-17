# ProxyIP_Static API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/static/
urlpatterns = [
    path('proxies', request.proxies_view, name='proxyip_static_proxies'),
    path('proxies/reload', request.reload_proxies_view, name='proxyip_static_reload'),
]
