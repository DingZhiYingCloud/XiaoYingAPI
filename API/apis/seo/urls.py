# SEO 服务总路由
from django.urls import path, include

# 域名前缀: /api/seo/
urlpatterns = [
    path('', include('API.apis.seo.friend_links.urls')),  # 友情链接
]
