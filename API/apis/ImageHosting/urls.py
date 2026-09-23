# API路由
from django.urls import path, include

# 域名前缀: /api/ImageHosting/
urlpatterns = [
    path('scdn/', include('API.apis.ImageHosting.ImageHosting_scdn.urls')),  # scdn.io 图床
    path('picui/', include('API.apis.ImageHosting.ImageHosting_picui.urls')),  # PicUI 图床
]
