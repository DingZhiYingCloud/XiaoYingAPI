# 用户中心 API 路由
from django.urls import path, include

# 域名前缀: /api/user_center/
urlpatterns = [
    path('users/', include('API.apis.user_center.users.urls')),        # 用户相关 API
    path('projects/', include('API.apis.user_center.projects.urls')),  # 接入项目相关 API
]
