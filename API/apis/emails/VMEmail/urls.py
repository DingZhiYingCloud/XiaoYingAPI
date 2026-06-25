# API路由
from django.urls import path, include

# 域名前缀: /api/emails/VMEmail/
urlpatterns = [
    path('minmail/', include('API.apis.emails.VMEmail.VMEmail_minmail.urls')), # 虚拟邮箱 - 提供收取邮件服务
]