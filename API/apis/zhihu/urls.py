"""知乎服务路由

域名前缀: /api/zhihu/
"""
from django.urls import path

from . import request

urlpatterns = [
    path('hot', request.hot_view, name='zhihu_hot'),                # 知乎热榜
    path('question', request.question_view, name='zhihu_question'),  # 问题详情（回答/评论/相关）
    path('article', request.article_view, name='zhihu_article'),     # 专栏文章详情（评论/大家在搜）
    path('search', request.search_view, name='zhihu_search'),        # 综合搜索（正文/大家都在搜）
    path('check', request.check_view, name='zhihu_check'),          # 校验登录凭据是否有效
]
