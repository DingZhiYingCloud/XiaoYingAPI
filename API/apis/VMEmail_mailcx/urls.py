# VMEmail 虚拟邮件(mail.cx) API 路由
from django.urls import path

from . import request

# 域名前缀: /api/VMEmail_mailcx/
urlpatterns = [
    path('domains', request.domains_view, name='vmemail_mailcx_domains'),          # 可用后缀域名列表
    path('generate', request.generate_view, name='vmemail_mailcx_generate'),        # 生成临时邮箱
    path('emails', request.emails_view, name='vmemail_mailcx_emails'),              # 邮件列表(长轮询)
    path('email_detail', request.email_detail_view, name='vmemail_mailcx_detail'),  # 邮件详情
]
