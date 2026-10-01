# API路由
from django.urls import include, path

# 域名前缀: /api/ProxyIp/
# 只保留两条线路：51代理 与 巨量代理
urlpatterns = [
    path('juliang/', include('API.apis.ProxyIp.ProxyIP_juliang.urls')),  # 巨量代理IP
    path('51daili/', include('API.apis.ProxyIp.ProxyIP_51daili.urls')),  # 51代理 动态代理IP
]
