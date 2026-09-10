# 项目URL配置
import os

from django.conf.urls.static import static
from django.conf import settings
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.views.static import serve

from API.common.views import handler404 as _web404_view

# 危险可渲染类型扩展名：/media/ 下此类文件强制附件下载，禁止内联渲染（S-02 整改）
DANGEROUS_MEDIA_EXTS = {'.svg', '.html', '.htm', '.xhtml', '.xml', '.js',
                        '.mht', '.mhtml', '.php', '.phtml'}


def _media_serve(request, path, document_root):
    """带安全响应头的 /media/ 文件服务。

    对所有媒体文件统一加 X-Content-Type-Options: nosniff；
    对可渲染/可执行类型（svg/html/xml/js/php 等）强制 Content-Disposition: attachment，
    防止上传到 /media/ 的恶意文件在浏览器中内联执行（存储型 XSS）。
    """
    response = serve(request, path, document_root)
    response['X-Content-Type-Options'] = 'nosniff'
    ext = os.path.splitext(path)[1].lower()
    if ext in DANGEROUS_MEDIA_EXTS:
        filename = os.path.basename(path)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


urlpatterns = [
    # Django 原生后台已移除（前台 /login/ 统一登录 + 超管页面接管管理功能）
    path('api/', include('API.apis.urls')), # API路由
    path('', include('API.website.urls')), # 官网前台路由（首页/登录/注册/文档/控制台）
]

# 全局兜底：非 /api/ 网站页面渲染友好 HTML 错误页，/api/ 返回统一 JSON
handler400 = 'API.common.views.handler400'
handler404 = 'API.common.views.handler404'
handler500 = 'API.common.views.handler500'

# 静态文件 & 媒体文件服务
# DEBUG=True 时 Django 自动通过 static() 辅助函数服务
# DEBUG=False 时静态文件由 WhiteNoise 中间件服务（Django 5.1+ 的 serve() 视图在 DEBUG=False 时返回 400），
# 此处仅需为媒体文件补充路由
if not settings.DEBUG:
    # 媒体文件：从 MEDIA_ROOT 直接服务（带 S-02 安全响应头）
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', _media_serve, {'document_root': settings.MEDIA_ROOT}),
    ]
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# 网页 404 兜底（放在最后，且排除 /static /media）：
# DEBUG=True 时 Django 对未匹配路由默认弹“技术调试页”，这里接管为友好 404 页；
# /api 的未匹配路径同样在此兜底并返回统一 JSON（保持 API 契约），
# /static /media 由上面的静态路由先行匹配。
urlpatterns.append(re_path(r'^api/.*$', _web404_view))
urlpatterns.append(re_path(r'^(?!api/|static/|media/).*$', _web404_view))

