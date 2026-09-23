# ImageHosting_scdn API路由
from django.urls import path

from . import request

# 域名前缀: /api/ImageHosting/scdn/
urlpatterns = [
    path('upload', request.upload_view, name='image_hosting_scdn_upload'),
]
