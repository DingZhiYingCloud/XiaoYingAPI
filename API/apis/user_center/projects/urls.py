# 用户中心 - 接入项目 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/user_center/projects/
urlpatterns = [
    path('info', request.project_info_view, name='user_center_project_info'),  # 项目信息
]
