# 项目URL配置
from django.conf.urls.static import static
from django.conf import settings
from django.urls import path, include, re_path
from django.contrib import admin
from django.views.generic import RedirectView
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
]

# 静态文件 & 媒体文件服务
# DEBUG=True 时 Django 自动通过 static() 辅助函数服务
# DEBUG=False 时 static() 返回空列表，需要手动添加路由
if not settings.DEBUG:
    # 静态文件：从 STATICFILES_DIRS 源目录直接服务
    static_root = settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else settings.STATIC_ROOT
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': static_root}),
    ]
    # 媒体文件：从 MEDIA_ROOT 直接服务
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

