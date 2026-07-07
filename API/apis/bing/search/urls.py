# 必应搜索 & 网页抓取 API路由
from django.urls import path

from . import request

# 域名前缀: /api/bing/search/
urlpatterns = [
    path('search', request.search_view, name='bing_search'),
    path('crawl', request.crawl_view, name='bing_crawl'),
]
