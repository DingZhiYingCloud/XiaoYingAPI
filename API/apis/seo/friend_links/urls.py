# 友情链接 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/seo/friend_links/
urlpatterns = [
    # 集合操作: GET 列表 / POST 创建
    path('friend_links', request.friend_links_view, name='friend_links_collection'),
    path('friend_links/', request.friend_links_view, name='friend_links_collection_slash'),
    # 单条操作: GET 详情 / PATCH 更新 / DELETE 删除
    path('friend_links/<int:link_id>', request.friend_link_detail_view, name='friend_link_detail'),
    path('friend_links/<int:link_id>/', request.friend_link_detail_view, name='friend_link_detail_slash'),
]
