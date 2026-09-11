# 抖音评论发布 API路由
from django.urls import path

from . import request

# 域名前缀: /api/douyin/comment/
urlpatterns = [
    path('publish', request.publish_view, name='douyin_comment_publish'),  # 发布一条抖音一级评论
]
