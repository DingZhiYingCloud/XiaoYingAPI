"""API 路径 404 兜底中间件 + API 认证中间件 + CSRF 中间件（S-07 整改）

当请求的 /api/ 路径未匹配任何路由时，Django 在 DEBUG=True 下会返回 HTML 调试页，
而非项目统一 JSON 格式。此中间件拦截 /api/ 前缀的 404 响应并转为 JSON。
不受 DEBUG 开关影响，生产环境同样生效。
"""
import logging
import time
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware

from API.common import StatusCode


# ==================== 分类树查询缓存（A-02 整改） ====================
# ApiAuthMiddleware 每个 /api/ 请求都会查一次 ApiCategory 全表做前缀匹配。
# 节点数量少（数十级）、变更不频繁，引入进程内 TTL 缓存避免请求级 DB 查询：
#   - 默认 60s，可用 settings.API_CATEGORY_CACHE_TTL 调整（秒）
#   - 后台保存/删除 ApiCategory（apps.ready 信号）与 rebuild_category_tree 命令
#     执行后主动失效，保证后台改认证模式后即时生效，无需等 TTL
_CATEGORY_CACHE = {'ts': 0.0, 'nodes': []}


def invalidate_api_category_cache():
    """A-02：立即使分类树缓存失效（后台改动分类 / 重建命令后调用）"""
    _CATEGORY_CACHE['nodes'] = []
    _CATEGORY_CACHE['ts'] = 0.0


def _category_nodes():
    """读取启用分类节点列表（进程内 TTL 缓存，TTL 内只查一次库）"""
    ttl = getattr(settings, 'API_CATEGORY_CACHE_TTL', 60)
    now = time.monotonic()
    if _CATEGORY_CACHE['nodes'] and now - _CATEGORY_CACHE['ts'] < ttl:
        return _CATEGORY_CACHE['nodes']
    from API.models.Auth.category import ApiCategory
    nodes = list(ApiCategory.objects.filter(status=True)
                 .values('id', 'path_prefix', 'parent_id', 'auth_mode'))
    _CATEGORY_CACHE['nodes'] = nodes
    _CATEGORY_CACHE['ts'] = now
    return nodes


class ApiCsrfExemptMiddleware(CsrfViewMiddleware):
    """全局 CSRF 防护（S-07 整改）

    Django 标准 CSRF 中间件此前被整体注释，导致 /admin/ 等后台页面无 CSRF 校验。
    现恢复 CSRF 防护并仅对 /api/ 前缀豁免：
    - /admin/ 及后台表单恢复正常 CSRF 校验（缺 csrfmiddlewaretoken 的 POST 返回 403）
    - /api/ 接口已由 ApiAuthMiddleware 做签名认证，豁免 CSRF 保证对接方零改动
    """

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.path.startswith('/api/'):
            return None
        return super().process_view(request, callback, callback_args, callback_kwargs)


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


class ApiRequestLogMiddleware:
    """请求日志中间件（A-05 整改）

    为每个请求生成 request_id（UUID 前 16 位，回写响应头 X-Request-Id），
    请求结束后在 app.log 记一行 key=value 日志：
    request_id / method / path / status / cost_ms / app(auth_app.app_id, 未认证为 '-'）。
    视图层未捕获异常就地记录完整堆栈到 error.log（同样带 request_id），
    一次故障可用 request_id 在 app.log/error.log 间全链路关联追溯。

    注意：注册顺序须在 ApiAuthMiddleware 之后（读取 auth_app）、且尽量靠内层，
    才能同时覆盖认证通过后到达视图层的请求与视图抛出的异常。
    """

    _logger = logging.getLogger('api.request')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex[:16]
        start = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            self._logger.exception(
                'request_id=%s method=%s path=%s status=500 cost_ms=%.1f exception=uncaught',
                request.request_id, request.method, request.path,
                (time.monotonic() - start) * 1000)
            raise
        app_id = getattr(getattr(request, 'auth_app', None), 'app_id', '-')
        response['X-Request-Id'] = request.request_id
        self._logger.info(
            'request_id=%s method=%s path=%s status=%s cost_ms=%.1f app=%s',
            request.request_id, request.method, request.path, response.status_code,
            (time.monotonic() - start) * 1000, app_id)
        return response


# 公开 GET 路径（免签名）：邮箱激活链接位于验证邮件内，点击链接本身即一次性凭证，
# 浏览器访问不带签名参数；注册/登录方式配置为客户端公开信息，均无需项目签名。
# 注意：A-01 后全局默认 fail-closed（分类树未匹配/全 inherit 一律要求签名），
# 仅此处列出的 GET 路径与分类树中显式 open 的节点可匿名访问。
# （captcha_auth/aliyun 整体为显式 open——开放集成设计，config/verify 均免签，见分类树）
PUBLIC_GET_PATHS = (
    '/api/user_center/users/verify/email',
    '/api/user_center/users/methods',
)


class ApiAuthMiddleware:
    """API 服务认证中间件

    根据 ApiCategory 分类树配置，决定 /api/ 请求是否需要用户中心认证（A-01 fail-closed）：
    - 匹配规则：请求路径按「最长前缀」命中一个分类节点，再沿父链向上找第一个
      非 inherit 的认证模式生效（auth=需认证 / open=开放）
    - 覆盖能力：父级设 auth 后，可单独把某个子级设 open，实现「父级认证、子级开放」
    - A-01 安全默认（fail-closed）：未命中任何分类节点 / 整条链全为 inherit /
      命中分类已停用，一律按「需要认证」处理——新增服务在未显式配置前默认不可匿名访问
    - 要求认证：校验签名（app_id/timestamp/nonce/sign），通过后把项目对象挂到
      request.auth_app 供视图直接使用；失败返回统一 20011
    - 开放：仅分类树显式 open 的节点，以及 PUBLIC_GET_PATHS 列出的公开 GET 路径

    对外签名契约与原先视图内校验完全一致，对接方无感知。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            # 公开 GET 路径（如邮件内激活链接、图形认证初始化）免签名
            is_public_get = request.method == 'GET' and request.path in PUBLIC_GET_PATHS
            if not is_public_get and self._requires_auth(request.path):
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
        """分类树继承判定（A-01 fail-closed）

        最长前缀命中节点后，沿父链取第一个非 inherit 的模式：
        - 命中 auth → 需要认证；命中 open → 开放
        - 未命中任何节点 / 全链均为 inherit / 命中节点已停用 → 需要认证（安全默认）
        分类节点经 _category_nodes() 进程内 TTL 缓存读取（A-02），后台改动即时失效。
        """
        nodes = _category_nodes()
        best, best_len = None, -1
        for node in nodes:
            if path.startswith(node['path_prefix']) and len(node['path_prefix']) > best_len:
                best, best_len = node, len(node['path_prefix'])
        if best is None:
            return True  # 未命中分类节点：fail-closed，默认需要认证
        by_id = {node['id']: node for node in nodes}
        seen = set()
        while best is not None and best['id'] not in seen:
            seen.add(best['id'])
            if best['auth_mode'] != 'inherit':
                return best['auth_mode'] == 'auth'
            best = by_id.get(best['parent_id'])
        return True  # 全为 inherit / 父链成环：fail-closed，默认需要认证
