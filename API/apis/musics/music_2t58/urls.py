# 爱听音乐网(2t58.com) API路由
from django.urls import path

from . import request

# 域名前缀: /api/music/2t58/
urlpatterns = [
    path('home', request.home_view, name='music_2t58_home'),        # 首页数据
    path('singer', request.singer_view, name='music_2t58_singer'),  # 歌手详情
    path('song', request.song_view, name='music_2t58_song'),        # 歌曲详情
    path('search', request.search_view, name='music_2t58_search'),  # 搜索音乐
]
