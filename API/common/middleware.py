"""API 路径 404 兜底中间件

当请求的 /api/ 路径未匹配任何路由时，Django 在 DEBUG=True 下会返回 HTML 调试页，
而非项目统一 JSON 格式。此中间件拦截 /api/ 前缀的 404 响应并转为 JSON。
不受 DEBUG 开关影响，生产环境同样生效。
"""
from django.http import JsonResponse

from API.common import StatusCode


class ApiJson404Middleware:
    """对 /api/ 前缀未匹配的路由返回 JSON 404"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404 and request.path.startswith('/api/'):
            return JsonResponse({
                'code': StatusCode.NOT_FOUND,
                'msg': f'请求的资源不存在: {request.path}',
                'data': None,
            }, status=404)
        return response
