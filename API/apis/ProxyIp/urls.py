# API路由
from django.urls import path, include

# 域名前缀: /api/ProxyIp/
urlpatterns = [
    path('66daili/', include('API.apis.ProxyIp.ProxyIP_66daili.urls')),  # 66免费代理IP
    path('qy/', include('API.apis.ProxyIp.ProxyIP_qy.urls')),            # 青雨动态代理IP
    path('qy_res/', include('API.apis.ProxyIp.ProxyIP_qy_res.urls')),    # 青雨住宅长效代理
    path('91http/', include('API.apis.ProxyIp.ProxyIP_91http.urls')),    # 91HTTP动态代理IP
    path('juliang/', include('API.apis.ProxyIp.ProxyIP_juliang.urls')),  # 巨量代理IP
    path('static/', include('API.apis.ProxyIp.ProxyIP_Static.urls')),    # 静态代理IP
    path('thordata/', include('API.apis.ProxyIp.ProxyIP_thordata.urls')),  # Thordata动态住宅代理
]