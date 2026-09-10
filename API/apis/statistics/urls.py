# API 调用统计服务路由
from django.urls import path

from . import request

# 域名前缀: /api/statistics/
urlpatterns = [
    path('api_calls', request.api_calls_view, name='statistics_api_calls'),   # 单接口调用量
    path('services', request.services_view, name='statistics_services'),      # 服务调用量排行
]
