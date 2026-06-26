# Seekin 视频解析 API路由
from django.urls import path

from . import request

# 域名前缀: /api/video_analysis/seekin/
urlpatterns = [
    path('parse', request.parse_view, name='video_analysis_seekin_parse'),                          # 解析抖音视频
    path('parse/xiaohongshu', request.parse_xiaohongshu_view, name='video_analysis_seekin_xhs'),    # 解析小红书内容
    path('parse/bilibili', request.parse_bilibili_view, name='video_analysis_seekin_bili'),         # 解析哔哩哔哩视频
]
