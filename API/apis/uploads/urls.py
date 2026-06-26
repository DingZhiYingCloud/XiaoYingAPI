# 文件上传服务 API 路由
from django.urls import path

from API.apis.uploads import request

# 域名前缀: /api/upload/
urlpatterns = [
    path('image', request.image_upload_view, name='upload_image'),
    path('video', request.video_upload_view, name='upload_video'),
    path('file', request.file_upload_view, name='upload_file'),
]
