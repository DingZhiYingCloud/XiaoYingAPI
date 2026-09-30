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
from API.common import api_stats


# ==================== 服务策略查询缓存 ====================
# ApiAuthMiddleware 每个 /api/ 请求都会做一次策略前缀匹配。
# 策略数量少、变更不频繁，引入进程内 TTL 缓存避免请求级 DB 查询：
#   - 默认 60s，可用 settings.API_SERVICE_POLICY_CACHE_TTL 调整（秒）
#   - 后台保存 / 删除策略、改动白名单（apps）后由 API/apps.py 的信号主动失效；
#     显式调用 invalidate_api_service_policy_cache() 亦可立即失效（测试 / 管理命令用）
# 同时缓存「白名单策略 -> 授权项目 app_id 集合」，让白名单校验也走缓存、不逐请求查 M2M。
_POLICY_CACHE = {'ts': 0.0, 'policies': [], 'apps': {}}


def invalidate_api_service_policy_cache():
    """立即使服务策略缓存失效（后台改动策略 / 白名单后调用）"""
    _POLICY_CACHE['policies'] = []
    _POLICY_CACHE['apps'] = {}
    _POLICY_CACHE['ts'] = 0.0


def _policy_nodes():
    """读取全部服务策略（进程内 TTL 缓存）

    策略本身不分启用 / 停用：状态由 status 字段表达（normal/dev/maintenance/offline），
    故全部策略都参与匹配。
    """
    ttl = getattr(settings, 'API_SERVICE_POLICY_CACHE_TTL', 60)
    now = time.monotonic()
    if _POLICY_CACHE['policies'] and now - _POLICY_CACHE['ts'] < ttl:
        return _POLICY_CACHE['policies']
    from API.models.Auth.policy import ApiServicePolicy
    policies = list(ApiServicePolicy.objects
                    .values('id', 'path_prefix', 'status', 'auth_mode', 'app_scope',
                            'docs_visible', 'audience'))
    apps = {}
    for policy_id, app_id in (ApiServicePolicy.objects.filter(app_scope='whitelist')
                              .values_list('id', 'apps__app_id')):
        if app_id:
            apps.setdefault(policy_id, set()).add(app_id)
    _POLICY_CACHE['policies'] = policies
    _POLICY_CACHE['apps'] = apps
    _POLICY_CACHE['ts'] = now
    return policies


def _prefix_match(path, prefix):
    """前缀命中判定（带段边界，避免 /api/foo 误命中 /api/foobar）

    - path == prefix：精确命中；
    - prefix 以 '/' 结尾：目录式前缀，path 以其为前缀即命中；
    - 否则为叶子前缀：仅 path 等于它或以 ``prefix + '/'`` 开头才命中。
    """
    if path == prefix:
        return True
    if prefix.endswith('/'):
        return path.startswith(prefix)
    return path.startswith(prefix + '/')


def _policy_chain(path):
    """命中该路径的全部策略，按 path_prefix 长度降序（最具体在前）"""
    matched = [p for p in _policy_nodes() if _prefix_match(path, p['path_prefix'])]
    matched.sort(key=lambda p: len(p['path_prefix']), reverse=True)
    return matched


def policy_allows_app(policy_id, app_id):
    """该策略自己的白名单是否包含该调用项目"""
    return app_id in _POLICY_CACHE['apps'].get(policy_id, set())


# resolve_service_policy() 在各字段都没命中时的全局兜底（fail-closed）
DEFAULT_STATUS = 'normal'
DEFAULT_AUTH_MODE = 'auth'
DEFAULT_APP_SCOPE = 'all'
DEFAULT_DOCS_VISIBLE = 'visible'
DEFAULT_AUDIENCE = 'normal'


def resolve_service_policy(path):
    """逐字段逐级继承，返回某路径的生效策略

    在该路径命中的策略链上（最具体在前），每个字段取第一个非 inherit 的值；
    都没命中时用全局兜底：status=normal / auth_mode=auth（fail-closed）/ app_scope=all。

    返回：{'status', 'auth_mode', 'app_scope', 'docs_visible', 'audience',
          'whitelist_policy_id', 'chain'}
    - whitelist_policy_id：生效值为 whitelist 时，那条策略的 id（白名单只认它自己的名单）
    """
    status = auth_mode = app_scope = None
    docs_visible = audience = None
    whitelist_policy_id = None
    chain = _policy_chain(path)
    for policy in chain:
        if status is None and policy['status'] != 'inherit':
            status = policy['status']
        if auth_mode is None and policy['auth_mode'] != 'inherit':
            auth_mode = policy['auth_mode']
        if app_scope is None and policy['app_scope'] != 'inherit':
            app_scope = policy['app_scope']
            if app_scope == 'whitelist':
                whitelist_policy_id = policy['id']
        if docs_visible is None and policy['docs_visible'] != 'inherit':
            docs_visible = policy['docs_visible']
        if audience is None and policy['audience'] != 'inherit':
            audience = policy['audience']
        if (status is not None and auth_mode is not None and app_scope is not None
                and docs_visible is not None and audience is not None):
            break
    return {
        'status': status or DEFAULT_STATUS,
        'auth_mode': auth_mode or DEFAULT_AUTH_MODE,
        'app_scope': app_scope or DEFAULT_APP_SCOPE,
        'docs_visible': docs_visible or DEFAULT_DOCS_VISIBLE,
        'audience': audience or DEFAULT_AUDIENCE,
        'whitelist_policy_id': whitelist_policy_id,
        'chain': chain,
    }


def requires_auth(path):
    """认证判定的唯一口径：生效 auth_mode == open 时放行，其余一律需要签名

    基于 resolve_service_policy() 的逐级继承结果判定，保证「页面展示的生效结果」
    与中间件真实鉴权永远一致（**不要在别处复制这段判定逻辑**）。
    服务级 / 线路级 / 端点级策略及各字段 inherit 的继承都在 resolve 内统一处理，
    未命中任何策略时 fail-closed 落回 auth（需要签名）。
    """
    return resolve_service_policy(path)['auth_mode'] != 'open'


def is_docs_hidden(path):
    """该路径是否对官网文档中心隐藏（唯一口径，供文档页 / 在线调试过滤用）

    「文档隐藏」同时作用于：/docs/ 文档页的端点列表、服务目录与左侧菜单、
    以及 /docs/_call/ 在线调试白名单（该调试页是公开的，隐藏的接口不得可调试）。
    """
    return resolve_service_policy(path)['docs_visible'] == 'hidden'


def is_admin_only(path):
    """该路径是否「仅专属管理员」（仅后台内部使用，对外调用一律 20020）"""
    return resolve_service_policy(path)['audience'] == 'admin_only'


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


class ApiJsonErrorMiddleware:
    """对 /api/ 前缀的 404 / 405 统一转为项目 JSON 格式

    - 404：请求的 /api/ 路径未匹配任何路由时，Django 在 DEBUG=True 下会返回 HTML
      调试页，此中间件统一转 JSON。不受 DEBUG 开关影响，生产环境同样生效。
    - 405：视图上的 @require_http_methods 返回的是 Django 原生 HTML 405，
      按统一 JSON 契约解析的对接方会解析失败，这里统一转 JSON（METHOD_NOT_ALLOWED）。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/'):
            if response.status_code == 404:
                return JsonResponse({
                    'code': StatusCode.NOT_FOUND,
                    'msg': f'请求的资源不存在: {request.path}',
                    'data': None,
                }, status=404)
            if response.status_code == 405:
                return JsonResponse({
                    'code': StatusCode.METHOD_NOT_ALLOWED,
                    'msg': f'请求方法不允许: {request.method} {request.path}',
                    'data': None,
                }, status=405)
        return response


class ApiRequestLogMiddleware:
    """请求日志中间件（A-05 整改）+ API 调用统计（A-03）

    为每个请求生成 request_id（UUID 前 16 位，回写响应头 X-Request-Id），
    请求结束后在 app.log 记一行 key=value 日志：
    request_id / method / path / status / cost_ms / app（auth_app.app_id，未认证为 '-'）。
    视图层未捕获异常就地记录完整堆栈到 error.log（同样带 request_id），
    一次故障可用 request_id 在 app.log/error.log 间全链路关联追溯。

    注册顺序要求：**必须在 ApiAuthMiddleware 之前**（即更外层）。
    认证失败的请求由 ApiAuthMiddleware 直接返回、不会向下调用，若本中间件在内层则
    这类请求既无日志也不进统计；放到外层后才能覆盖「认证被拒」「未匹配路由」等请求。
    此时 request.auth_app 仍可读到——它是认证中间件在下行阶段挂到同一个 request 上的。

    统计口径与写入策略见 API/common/api_stats.py。
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
        cost_ms = (time.monotonic() - start) * 1000
        response['X-Request-Id'] = request.request_id
        self._logger.info(
            'request_id=%s method=%s path=%s status=%s cost_ms=%.1f app=%s',
            request.request_id, request.method, request.path, response.status_code,
            cost_ms, app_id)
        # 调用统计（A-03）：进程内聚合 + 批量落库，见 API/common/api_stats.py。
        # 统计失败不影响业务（模块内已兜底），仅 /api/ 请求计入；
        # 路径取路由模板并归一参数，避免带 UUID 的接口被拆成大量行。
        api_stats.record(api_stats.request_path(request), cost_ms,
                         api_stats.business_code(response), app_id)
        return response


# 公开 GET 路径（免签名）：邮箱激活链接位于验证邮件内，点击链接本身即一次性凭证，
# 浏览器访问不带签名参数；注册/登录方式配置为客户端公开信息，均无需项目签名。
# 注意：全局默认 fail-closed（未命中策略一律要求签名），
# 仅此处列出的 GET 路径与显式 open 的策略节点可匿名访问。
PUBLIC_GET_PATHS = (
    '/api/user_center/users/verify/email',
    '/api/user_center/users/methods',
)


# 会直接拦截请求的策略状态 -> 返回的业务码（命中即拦，不做签名校验）
# 其余状态（normal / dev）只作前台展示标记、不拦截：开发中的服务仍需联调，放行更合理。
_STATUS_BLOCK_CODES = {
    'maintenance': StatusCode.SERVICE_MAINTENANCE,
    'offline': StatusCode.SERVICE_OFFLINE,
}


class ApiAuthMiddleware:
    """API 服务认证中间件

    根据服务策略表（ApiServicePolicy，服务 / 线路 / 端点三级逐级继承）决定 /api/ 请求是否放行：

    1. **状态拦截（最优先）**：生效 status 为 maintenance（30004 服务维护中）或 offline
       （30005 服务已下线）时直接返回对应业务码，且**不做签名校验**（匿名请求同样收到）；
       normal / dev 只作前台展示标记，不拦截（开发中的服务需要能实际联调）。
    2. **专属管理员拦截**：生效 audience=admin_only 的接口仅供后台内部使用，
       对外一律返回 20020（无权限），不区分是否带签名。
    3. **认证判定**：由 requires_auth() 统一给出（基于 resolve_service_policy()）。
       · 需要签名：校验签名（app_id/timestamp/nonce/sign），通过后把项目对象挂到
         request.auth_app 供视图直接使用；失败返回统一 20011
       · 开放：仅显式 open 的策略节点，以及 PUBLIC_GET_PATHS 列出的公开 GET 路径
    4. **项目白名单（签名通过后）**：生效 app_scope=whitelist 且当前项目不在
       这条策略的名单内 → 返回 20020（FORBIDDEN）。open 模式不校验签名、拿不到调用项目，
       白名单对其无意义。

    对外签名契约与原先视图内校验完全一致，对接方无感知。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            effective = resolve_service_policy(request.path)
            # 1) 状态拦截最优先：维护中 / 已下线直接返回对应业务码（匿名也不做签名校验）
            block_code = _STATUS_BLOCK_CODES.get(effective['status'])
            if block_code is not None:
                return JsonResponse({
                    'code': block_code,
                    'msg': StatusCode.get_message(block_code),
                    'data': None,
                })
            # 2) 「仅专属管理员」的接口仅供后台内部使用：对外一律拒绝（不区分是否带签名）
            if effective['audience'] == 'admin_only':
                return JsonResponse({
                    'code': StatusCode.FORBIDDEN,
                    'msg': '该接口仅限后台内部使用，不对外开放',
                    'data': None,
                })
            # 公开 GET 路径（如邮件内激活链接、注册/登录方式配置）免签名
            is_public_get = request.method == 'GET' and request.path in PUBLIC_GET_PATHS
            if not is_public_get and requires_auth(request.path):
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
                # 3) 白名单：签名通过（已拿到调用项目）后再判；open 模式无签名，白名单不生效
                if (effective['app_scope'] == 'whitelist'
                        and not policy_allows_app(effective['whitelist_policy_id'],
                                                  result.app_id)):
                    return JsonResponse({
                        'code': StatusCode.FORBIDDEN,
                        'msg': f'该项目未获授权调用此服务: {result.app_id}',
                        'data': None,
                    })
        return self.get_response(request)
