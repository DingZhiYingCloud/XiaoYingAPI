# 项目URL配置
import os
import re

from django.conf.urls.static import static
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404
from django.urls import path, include, re_path
from django.utils._os import safe_join
from django.views.generic import RedirectView
from django.views.static import serve

from API.common.media import range_response
from API.common.views import handler404 as _web404_view

# 危险可渲染类型扩展名：/media/ 下此类文件强制附件下载，禁止内联渲染（S-02 整改）
DANGEROUS_MEDIA_EXTS = {'.svg', '.html', '.htm', '.xhtml', '.xml', '.js',
                        '.mht', '.mhtml', '.php', '.phtml'}


def _media_serve(request, path, document_root):
    """带安全响应头 + Range 支持的 /media/ 文件服务。

    对所有媒体文件统一加 X-Content-Type-Options: nosniff；
    对可渲染/可执行类型（svg/html/xml/js/php 等）强制 Content-Disposition: attachment，
    防止上传到 /media/ 的恶意文件在浏览器中内联执行（存储型 XSS）。

    反馈附件例外：它们可能包含用户的私人截图/视频，**不允许**从 /media/ 匿名直读，
    必须走 `website:feedback_attachment` 受控下载（校验本人 / 超管）。
    """
    normalized = path.replace('\\', '/').lstrip('/')
    if normalized.startswith('uploads/feedback/'):
        raise Http404('该附件仅支持通过反馈页访问')

    try:
        full_path = safe_join(document_root, path)
    except SuspiciousFileOperation:
        raise Http404('媒体文件路径非法')
    if not os.path.isfile(full_path):
        raise Http404('媒体文件不存在')

    response = range_response(request, full_path)
    if response is None:
        response = serve(request, path, document_root)
    response['Accept-Ranges'] = 'bytes'
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
# DEBUG=True 时静态文件由 Django 服务，DEBUG=False 时由 WhiteNoise 中间件服务
# （Django 5.1+ 的 serve() 视图在 DEBUG=False 下用于静态文件会返回 400）。
# 媒体文件统一走 _media_serve：DEBUG 与生产同一套安全头 + Range 行为，
# 避免开发环境能拖动进度条、上线后 Safari / 微信播放音频失败。
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', _media_serve, {'document_root': settings.MEDIA_ROOT}),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# 网页 404 兜底（放在最后，且排除 /static /media）：
# DEBUG=True 时 Django 对未匹配路由默认弹“技术调试页”，这里接管为友好 404 页；
# /api 的未匹配路径同样在此兜底并返回统一 JSON（保持 API 契约），
# /static /media 由上面的静态路由先行匹配。
urlpatterns.append(re_path(r'^api/.*$', _web404_view))
urlpatterns.append(re_path(r'^(?!api/|static/|media/).*$', _web404_view))

