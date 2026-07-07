# Bing相关服务 API路由
from django.urls import path, include

# 域名前缀: /api/bing/
urlpatterns = [
    path('indexnow/', include('API.apis.bing.indexnow.urls')), # IndexNow URL提交服务
    path('search/', include('API.apis.bing.search.urls')), # 必应搜索 & 网页抓取服务
]
