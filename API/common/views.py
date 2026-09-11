"""全局兜底视图

规则：
- /api/ 前缀：统一返回 JSON 错误（保持各 API 子服务的 JSON 契约）；
- 其它路径（官网网页）：渲染友好 HTML 错误页（400.html / 404.html / 500.html），
  避免用户看到 JSON 或 Django 调试页。

另提供占位视图 service_building_view：供「路由保留、服务暂时关闭」的旧前缀使用
（能力已迁移到新服务的接口，访问旧地址时返回统一的 JSON 提示，而不是 404）。
"""
from django.http import JsonResponse
from django.shortcuts import render

from API.common import StatusCode

_JSON_STATUS = {
    400: StatusCode.PARAM_FORMAT_ERROR,
    404: StatusCode.NOT_FOUND,
    500: StatusCode.INTERNAL_ERROR,
}


def _is_api(request) -> bool:
    return request.path.startswith('/api/')


def _json(request, status):
    return JsonResponse({
        'code': _JSON_STATUS.get(status, StatusCode.UNKNOWN_ERROR),
        'msg': '请求参数错误' if status == 400 else (
            f'请求的资源不存在: {request.path}' if status == 404 else '服务器内部错误'),
        'data': None,
    }, status=status)


def _page(request, template, status):
    try:
        return render(request, template, status=status)
    except Exception:
        # 错误页自身渲染失败（如数据库不可用）时退回最小 HTML，保证始终有响应
        from django.http import HttpResponse
        return HttpResponse(f'<h1>{status}</h1>', status=status, content_type='text/html')


def handler400(request, exception=None):
    """请求错误（400）"""
    if _is_api(request):
        return _json(request, 400)
    return _page(request, '400.html', 400)


def handler404(request, exception=None):
    """未匹配到任何路由（404）"""
    if _is_api(request):
        return _json(request, 404)
    return _page(request, '404.html', 404)


def handler500(request):
    """服务器内部异常（500）"""
    if _is_api(request):
        return _json(request, 500)
    return _page(request, '500.html', 500)


def service_building_view(request, **kwargs):
    """服务建设中占位响应

    用于「路由保留、服务暂时关闭」的旧前缀（如 /api/video_analysis/、/api/auto_comment/）：
    其中的能力已迁移到新服务（/api/douyin/），旧地址不再提供功能，
    但仍返回项目统一的 JSON 契约，方便调用方明确识别「服务不可用」而非「地址写错」。
    """
    return JsonResponse({
        'code': StatusCode.SERVICE_UNAVAILABLE,
        'msg': '服务建设中，暂不可用',
        'data': None,
    })
