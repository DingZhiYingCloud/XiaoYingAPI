# 抖音视频/图文解析 API路由
from django.urls import path

from . import request

# 域名前缀: /api/douyin/video/
urlpatterns = [
    path('parse', request.parse_view, name='douyin_video_parse'),  # 解析抖音视频/图文
]
