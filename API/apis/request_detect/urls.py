# 请求身份识别 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/request_detect/
urlpatterns = [
    path('detect', request.detect_view, name='request_detect'),
    path('detect/', request.detect_view, name='request_detect_slash'),
]
