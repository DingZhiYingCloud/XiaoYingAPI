# 电影服务 API 路由（聚合）
from django.urls import path, include

# 域名前缀: /api/movies/
urlpatterns = [
    path('movie_555/', include('API.apis.movies.movie_555.urls')), # 555电影线路服务路由
]
