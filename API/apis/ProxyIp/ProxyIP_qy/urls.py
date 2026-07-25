# ProxyIP_qy API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/qy/
urlpatterns = [
    path('proxies', request.get_qy_proxies_view, name='proxyip_qy_proxies'),
]
