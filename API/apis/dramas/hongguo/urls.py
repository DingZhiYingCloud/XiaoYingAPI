# 红果短剧网页版 线路 API路由
from django.urls import path

from . import request

# 域名前缀: /api/dramas/hongguo/
urlpatterns = [
    path('rank', request.rank_view, name='dramas_hongguo_rank'),                   # 榜单
    path('categories', request.categories_view, name='dramas_hongguo_categories'), # 分类列表
    path('list', request.list_view, name='dramas_hongguo_list'),                   # 分类列表
    path('search', request.search_view, name='dramas_hongguo_search'),             # 搜索
    path('detail', request.detail_view, name='dramas_hongguo_detail'),             # 剧集详情
    path('play', request.play_view, name='dramas_hongguo_play'),                   # 播放地址
    path('stream', request.stream_view, name='dramas_hongguo_stream'),             # 网页直出流
]
