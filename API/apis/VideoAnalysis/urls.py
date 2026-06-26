# 视频分析服务 API 路由
from django.urls import path, include



# 域名前缀: /api/video_analysis/

urlpatterns = [
    path('seekin/', include('API.apis.VideoAnalysis.seekin.urls')), # 视频分析服务路由
]
