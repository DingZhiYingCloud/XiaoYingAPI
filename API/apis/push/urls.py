# 消息推送服务路由（聚合：服务根只 include 各推送线路）
from django.urls import path, include

# 域名前缀: /api/push/
urlpatterns = [
    path('serverchan/', include('API.apis.push.serverchan.urls')),  # Server酱
]
