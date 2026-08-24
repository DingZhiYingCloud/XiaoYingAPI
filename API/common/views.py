"""全局兜底视图

统一返回 JSON 格式的错误响应，避免 Django 默认 HTML 错误页。
例如访问不存在的路径、路径参数格式不匹配（如 UUID 路由传入非 UUID）时，
Django 会触发 handler404；未捕获异常触发 handler500。
"""
from django.http import JsonResponse

from API.common import StatusCode


def handler404(request, exception=None):
    """未匹配到任何路由时返回 JSON 404（兼容所有 API 子服务）"""
    return JsonResponse({
        'code': StatusCode.NOT_FOUND,
        'msg': f'请求的资源不存在: {request.path}',
        'data': None,
    }, status=404)


def handler500(request):
    """服务器内部异常时返回 JSON 500"""
    return JsonResponse({
        'code': StatusCode.INTERNAL_ERROR,
        'msg': '服务器内部错误',
        'data': None,
    }, status=500)
