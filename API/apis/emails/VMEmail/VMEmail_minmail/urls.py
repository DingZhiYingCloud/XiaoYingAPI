# VMEmail 虚拟邮件(minmail.app) API路由
from django.urls import path

from . import request

# 域名前缀: /api/email/VMEmail/minmail/
urlpatterns = [
    path('generate', request.generate_view, name='vmemail_minmail_generate'),  # 生成/获取临时邮箱
    path('emails', request.emails_view, name='vmemail_minmail_emails'),        # 获取邮件列表
]
