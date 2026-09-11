# 视频分析服务 API 路由（已暂时关闭）
#
# 原抖音解析能力已迁移到「抖音」服务：/api/douyin/video/parse
# 本前缀路由保留，访问时统一返回「服务建设中」，避免调用方拿到 404 无法区分。
from django.urls import path

from API.common.views import service_building_view

# 域名前缀: /api/video_analysis/
urlpatterns = [
    path('<path:rest>', service_building_view, name='video_analysis_building'),
]
