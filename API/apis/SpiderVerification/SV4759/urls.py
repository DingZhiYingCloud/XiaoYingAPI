# 4759蜘蛛IP验证 API路由
from django.urls import path

from . import request

# 域名前缀: /api/spider_verification/sv4759/
urlpatterns = [
    path('verify', request.verify_view, name='sv4759_verify'),
]
