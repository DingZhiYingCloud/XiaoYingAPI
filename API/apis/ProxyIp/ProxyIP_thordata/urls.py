# ProxyIP_thordata API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/thordata/
urlpatterns = [
    path('proxies', request.get_thordata_proxies_view, name='proxyip_thordata_proxies'),
]
