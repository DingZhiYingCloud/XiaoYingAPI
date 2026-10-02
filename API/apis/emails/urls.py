# 邮箱 服务
from django.urls import path, include


# 邮箱API路由配置
# 域名前缀: /api/emails/
urlpatterns = [
    path('v1/', include('API.apis.emails.v1.urls')), # 邮箱v1版本路由
]

