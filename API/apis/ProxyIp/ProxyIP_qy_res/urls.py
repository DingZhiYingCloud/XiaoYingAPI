# ProxyIP_qy_res API路由
from django.urls import path

from . import request

# 域名前缀: /api/ProxyIp/qy_res/
urlpatterns = [
    path('proxies', request.get_qy_res_proxies_view, name='proxyip_qy_res_proxies'),
]
