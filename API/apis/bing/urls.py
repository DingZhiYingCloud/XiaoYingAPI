# Bing相关服务 API路由
from django.urls import path, include

# 域名前缀: /api/bing/
urlpatterns = [
    path('indexnow/', include('API.apis.bing.indexnow.urls')), # IndexNow URL提交服务
]
