# API路由
from django.urls import path, include

# 域名前缀: /api/music/
urlpatterns = [
    path('2t58/', include('API.apis.musics.music_2t58.urls')), # 爱听音乐网服务路由
    path('xiaoying/', include('API.apis.musics.xiaoying.urls')), # 小影音乐服务路由
]