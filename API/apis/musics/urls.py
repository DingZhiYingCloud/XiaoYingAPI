# API路由
from django.urls import path, include

# 域名前缀: /api/music/
urlpatterns = [
    path('2t58/', include('API.apis.musics.music_2t58.urls')), # 音乐服务路由
]