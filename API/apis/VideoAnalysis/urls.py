# 视频分析服务 API 路由
from django.urls import path, include



# 域名前缀: /api/video_analysis/

urlpatterns = [
    path('douyin/', include('API.apis.VideoAnalysis.Douyin.urls')), # 抖音视频/图文解析服务路由
]
