# 推送服务 · QQBot 线路 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/push/qqbot/
urlpatterns = [
    path('send', request.send_view, name='push_qqbot_send'),  # 发送 QQ 消息
]
