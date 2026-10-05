# Server酱 消息推送线路 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/push/serverchan/
urlpatterns = [
    path('send', request.send_view, name='push_serverchan_send'),        # 发送消息
    path('status', request.status_view, name='push_serverchan_status'),  # 查询推送送达状态
]
