# 抖音服务 API 路由
from django.urls import path, include

# 域名前缀: /api/douyin/
urlpatterns = [
    path('video/', include('API.apis.Douyin.Video.urls')),      # 视频/图文解析线路
    path('comment/', include('API.apis.Douyin.Comment.urls')),   # 评论发布线路
]
