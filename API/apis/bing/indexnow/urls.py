# Bing IndexNow API路由
from django.urls import path

from . import request

# 域名前缀: /api/bing/indexnow/
urlpatterns = [
    path('generate-key', request.generate_key_view, name='indexnow_generate_key'),
    path('submit', request.submit_view, name='indexnow_submit'),
]
