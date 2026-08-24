# 小影音乐 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/music/xiaoying/
urlpatterns = [
    # 音乐集合操作: GET 列表 / POST 创建
    path('musics', request.musics_view, name='xiaoying_musics'),
    path('musics/', request.musics_view, name='xiaoying_musics_slash'),
    # 音乐单条操作: GET 详情(含播放源) / PATCH 更新 / DELETE 删除
    path('musics/<uuid:music_id>', request.music_detail_view, name='xiaoying_music_detail'),
    path('musics/<uuid:music_id>/', request.music_detail_view, name='xiaoying_music_detail_slash'),

    # 播放源: 仅 POST 创建 / PATCH 更新 / DELETE 删除
    # 播放源不提供独立列表/详情查询，通过「获取音乐详情」返回
    path('music_sources', request.music_source_create_view, name='xiaoying_music_source_create'),
    path('music_sources/', request.music_source_create_view, name='xiaoying_music_source_create_slash'),
    path('music_sources/<uuid:source_id>', request.music_source_detail_view, name='xiaoying_music_source_detail'),
    path('music_sources/<uuid:source_id>/', request.music_source_detail_view, name='xiaoying_music_source_detail_slash'),
]
