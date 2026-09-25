# 555电影 线路 API路由
from django.urls import path

from . import request

# 域名前缀: /api/movies/movie_555/
urlpatterns = [
    path('categories', request.categories_view, name='movies_555_categories'),  # 分类列表
    path('home', request.home_view, name='movies_555_home'),                    # 首页聚合
    path('list', request.list_view, name='movies_555_list'),                    # 分类列表
    path('detail', request.detail_view, name='movies_555_detail'),              # 影片详情
    path('play', request.play_view, name='movies_555_play'),                    # 播放地址
    path('search', request.search_view, name='movies_555_search'),              # 搜索
]
