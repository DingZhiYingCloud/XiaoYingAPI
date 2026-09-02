# 问题反馈中心 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/feedback/
urlpatterns = [
    path('create', request.create_view, name='feedback_create'),    # 提交反馈
    path('reply', request.reply_view, name='feedback_reply'),       # 追加/回复评论
    path('list', request.list_view, name='feedback_list'),          # 项目内反馈列表
    path('detail', request.detail_view, name='feedback_detail'),    # 反馈详情+评论树
    path('replies', request.replies_view, name='feedback_replies'), # 某条评论的二级评论列表(分页,全部子孙)
]
