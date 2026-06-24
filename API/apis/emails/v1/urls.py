# 邮箱 服务
from django.urls import path, include

from API.apis.emails.v1.request import send_email_view


# 邮箱v1版本API路由
# 完整访问路径: /api/email/v1/send
urlpatterns = [
    path('send', send_email_view, name='send_email'),  # 发送邮件
]
