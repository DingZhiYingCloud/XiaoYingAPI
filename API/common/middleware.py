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


class ApiAuthMiddleware:
    """API 服务认证中间件

    根据 ApiCategory 分类树配置，决定 /api/ 请求是否需要用户中心认证：
    - 匹配规则：请求路径按「最长前缀」命中一个分类节点，再沿父链向上找第一个
      非 inherit 的认证模式生效（auth=需认证 / open=开放）；整条链全为 inherit 默认开放
    - 覆盖能力：父级设 auth 后，可单独把某个子级设 open，实现「父级认证、子级开放」
    - 要求认证：校验签名（app_id/timestamp/nonce/sign），通过后把项目对象挂到
      request.auth_app 供视图直接使用；失败返回统一 20011
    - 开放：直接放行（默认开放）

    对外签名契约与原先视图内校验完全一致，对接方无感知。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/') and self._requires_auth(request.path):
            params = request.POST.dict()
            params.update({k: v for k, v in request.GET.items() if k not in params})
            from API.apis.user_center.sign import verify_sign
            ok, result = verify_sign(params)
            if not ok:
                return JsonResponse({
                    'code': StatusCode.AUTH_FAILED,
                    'msg': result,
                    'data': None,
                })
            request.auth_app = result
        return self.get_response(request)

    @staticmethod
    def _requires_auth(path):
        """分类树继承判定：最长前缀命中节点后，沿父链取第一个非 inherit 的模式"""
        from API.models.Auth.category import ApiCategory
        nodes = list(ApiCategory.objects.filter(status=True)
                     .values('id', 'path_prefix', 'parent_id', 'auth_mode'))
        best, best_len = None, -1
        for node in nodes:
            if path.startswith(node['path_prefix']) and len(node['path_prefix']) > best_len:
                best, best_len = node, len(node['path_prefix'])
        if best is None:
            return False
        by_id = {node['id']: node for node in nodes}
        seen = set()
        while best is not None and best['id'] not in seen:
            seen.add(best['id'])
            if best['auth_mode'] != 'inherit':
                return best['auth_mode'] == 'auth'
            best = by_id.get(best['parent_id'])
        return False  # 全为 inherit 或父链成环：默认开放
