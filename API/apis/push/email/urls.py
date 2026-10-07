# 推送服务 · 邮件线路 API 路由
from django.urls import path

from . import request

# 域名前缀: /api/push/email/
urlpatterns = [
    path('send', request.send_view, name='push_email_send'),  # 发送邮件
]
