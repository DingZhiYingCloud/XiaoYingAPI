# 短剧服务 API 路由（聚合）
from django.urls import path, include

# 域名前缀: /api/dramas/
urlpatterns = [
    path('hongguo/', include('API.apis.dramas.hongguo.urls')), # 红果短剧网页版线路
]
