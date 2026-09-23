# ImageHosting_picui API路由
from django.urls import path

from . import request

# 域名前缀: /api/ImageHosting/picui/
urlpatterns = [
    path('upload', request.upload_view, name='image_hosting_picui_upload'),
    path('tokens', request.tokens_view, name='image_hosting_picui_tokens'),
]
