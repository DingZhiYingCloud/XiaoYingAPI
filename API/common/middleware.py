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

_logger = logging.getLogger('api.request')


# ==================== 服务策略查询缓存 ====================
# ApiAuthMiddleware 每个 /api/ 请求都会做一次策略前缀匹配。
# 策略数量少、变更不频繁，引入进程内 TTL 缓存避免请求级 DB 查询：
#   - 默认 60s，可用 settings.API_SERVICE_POLICY_CACHE_TTL 调整（秒）
#   - 后台保存 / 删除策略后由 API/apps.py 的信号主动失效；
#     显式调用 invalidate_api_service_policy_cache() 亦可立即失效（测试 / 管理命令用）
_POLICY_CACHE = {'ts': 0.0, 'policies': []}


def invalidate_api_service_policy_cache():
    """立即使服务策略缓存失效（后台改动策略后调用）"""
    _POLICY_CACHE['policies'] = []
    _POLICY_CACHE['ts'] = 0.0


def _policy_nodes():
    """读取全部服务策略并展开为「一前缀一节点」（进程内 TTL 缓存）

    策略本身不分启用 / 停用：状态由 status 字段表达（normal/dev/maintenance/offline），
    故全部策略都参与匹配。

    一条策略可覆盖多条线路（``extra_prefixes``），故这里把每条策略按其全部前缀
    展开成多个节点。端点级前缀由 service_tree 截断到最后一个静态段（不含转换器），
    因此前缀匹配对所有层级都成立。
    """
    ttl = getattr(settings, 'API_SERVICE_POLICY_CACHE_TTL', 60)
    now = time.monotonic()
    if _POLICY_CACHE['policies'] and now - _POLICY_CACHE['ts'] < ttl:
        return _POLICY_CACHE['policies']
    from API.models.Auth.policy import ApiServicePolicy
    policies = []
    for row in (ApiServicePolicy.objects
                .values('id', 'path_prefix', 'extra_prefixes', 'status', 'auth_mode',
                        'docs_visible', 'audience')):
        prefixes = [row['path_prefix'], *(row['extra_prefixes'] or [])]
        for prefix in prefixes:
            policies.append({**row, 'path_prefix': prefix})
    _POLICY_CACHE['policies'] = policies
    _POLICY_CACHE['ts'] = now
    return policies


def prefix_match(path, prefix):
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
    matched = [p for p in _policy_nodes() if prefix_match(path, p['path_prefix'])]
    matched.sort(key=lambda p: len(p['path_prefix']), reverse=True)
    return matched


# resolve_service_policy() 在各字段都没命中时的全局兜底（fail-closed）
DEFAULT_STATUS = 'normal'
DEFAULT_AUTH_MODE = 'auth'
DEFAULT_DOCS_VISIBLE = 'visible'
DEFAULT_AUDIENCE = 'normal'


def resolve_service_policy(path):
    """逐字段逐级继承，返回某路径的生效策略

    在该路径命中的策略链上（最具体在前），每个字段取第一个非 inherit 的值；
    都没命中时用全局兜底：status=normal / auth_mode=auth（fail-closed）。

    返回：{'status', 'auth_mode', 'docs_visible', 'audience', 'chain'}
    """
    status = auth_mode = None
    docs_visible = audience = None
    chain = _policy_chain(path)
    for policy in chain:
        if status is None and policy['status'] != 'inherit':
            status = policy['status']
        if auth_mode is None and policy['auth_mode'] != 'inherit':
            auth_mode = policy['auth_mode']
        if docs_visible is None and policy['docs_visible'] != 'inherit':
            docs_visible = policy['docs_visible']
        if audience is None and policy['audience'] != 'inherit':
            audience = policy['audience']
        if (status is not None and auth_mode is not None
                and docs_visible is not None and audience is not None):
            break
    return {
        'status': status or DEFAULT_STATUS,
        'auth_mode': auth_mode or DEFAULT_AUTH_MODE,
        'docs_visible': docs_visible or DEFAULT_DOCS_VISIBLE,
        'audience': audience or DEFAULT_AUDIENCE,
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
        # 调用统计（A-03）：进程内聚合 + 后台批量落库，见 API/common/api_stats.py。
        # 统计失败不影响业务（模块内已兜底），仅 /api/ 请求计入；
        # 路径取路由模板并归一参数，避免带 UUID 的接口被拆成大量行。
        # 这里再兜一层：响应已经生成好了，统计出任何问题都不该把它变成 500。
        try:
            api_stats.record(api_stats.request_path(request), cost_ms,
                             api_stats.business_code(response), app_id)
        except Exception:
            self._logger.exception('调用统计记录失败（不影响业务响应）')
        return response


# 公开路径（免签名，GET / HEAD）：这些请求由浏览器或第三方播放器**直连**，天然带不了
# 项目签名，只能免签放行：
#   - 邮箱激活链接：点击链接本身即一次性凭证，链接里带的是自己的 token；
#   - 注册 / 登录方式配置：客户端公开信息；
#   - 红果短剧网页直出流 / 微博视频代理播放：<video> 标签直连，鉴权由下发的时效令牌承担
#     （播放器会为拖动进度条发多次 Range 请求，项目签名的 nonce 是一次性的，用不了）。
# 为什么代码里还要列一遍（DB 里同样有对应的 open 策略）：策略表是运营数据，会被误删、
# 换环境也不会自动重建（部分种子只存在于数据迁移里，迁移标记已执行就不会重跑）。
# 这几个例外一旦丢失，登录 / 播放会直接整片挂掉，因此留一份**与 DB 解耦**的代码兜底，
# DB 里那条 open 策略退化为「双保险」。
# 注意：全局默认 fail-closed（未命中策略一律要求签名），
# 仅此处列出的路径与显式 open 的策略节点可匿名访问。
PUBLIC_PATHS = (
    '/api/user_center/users/verify/email',
    '/api/user_center/users/methods',
    '/api/dramas/hongguo/stream',
    '/api/weibo/video',
)


# 会直接拦截请求的策略状态 -> 返回的业务码（命中即拦，不做签名校验）
# 口径：**只有 normal（正常）可调用**；dev / maintenance / offline 一律硬拦截，
# 各自返回一个业务码，便于调用方分辨是「开发中」「维护中」还是「已下线」。
_STATUS_BLOCK_CODES = {
    'dev': StatusCode.SERVICE_DEVELOPING,
    'maintenance': StatusCode.SERVICE_MAINTENANCE,
    'offline': StatusCode.SERVICE_OFFLINE,
}


class ApiAuthMiddleware:
    """API 服务认证中间件

    根据服务策略表（ApiServicePolicy，服务 / 线路 / 端点三级逐级继承）决定 /api/ 请求是否放行：

    1. **状态拦截（最优先）**：口径是**只有 normal（正常）可调用** —— 生效 status 为
       dev（30006 服务开发中）/ maintenance（30004 服务维护中）/ offline（30005 服务已下线）
       时直接返回对应业务码，且**不做签名校验**（匿名请求同样收到）。
       即：想让某个接口可调用，必须把生效状态配成「正常」。
    2. **专属管理员拦截**：生效 audience=admin_only 的接口仅供后台内部使用，
       对外一律返回 20020（无权限），不区分是否带签名。
    3. **认证判定**：由 requires_auth() 统一给出（基于 resolve_service_policy()）。
       · 需要签名：校验签名（app_id/timestamp/nonce/sign），通过后把项目对象挂到
         request.auth_app 供视图直接使用；失败返回统一 20011
       · 开放：仅显式 open 的策略节点，以及 PUBLIC_PATHS 列出的公开路径（GET / HEAD）

    **不按次计费**：只要签名通过就放行，项目可调用全部对外开放的接口（历史上有过
    「点数余额 + 按次扣点」的额度门槛，已整体下线）。

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
            # 公开路径（邮件内激活链接、注册/登录方式配置、红果直出流）免签名
            is_public = (request.method in ('GET', 'HEAD')
                         and request.path in PUBLIC_PATHS)
            if not is_public and requires_auth(request.path):
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


class IPBanMiddleware:
    """IP 封禁：/api/ 直接拒绝，网页侧只做标记（由母版顶部横幅提示）

    - **注册顺序**：放在 `ApiRequestLogMiddleware` 之后、`ApiAuthMiddleware` 之前 ——
      被封禁的请求仍会进请求日志与调用统计，同时**不做签名校验**就返回「IP 已被封禁」。
    - `/api/**`：命中生效中的封禁一律返回统一 JSON（业务码 `IP_BANNED`）。
    - **网页侧不拦截**（访客仍可浏览）：只把封禁记录挂到 `request.ip_ban`、
      并把来源 IP 挂到 `request.client_ip`，由 `API/website/context.py` 渲染顶部提示条，
      让访客看到封禁原因与到期时间，并知道要联系管理员解禁。
    - `/console/**` 与静态资源**永不参与判定**：管理员自己被封后仍要能进后台解禁，
      否则等于把自己锁在门外（静态资源由 WhiteNoise 在本中间件之前就返回了）。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from API.common.ip_guard import client_ip, find_effective_ban

        ip = client_ip(request)
        request.client_ip = ip
        request.ip_ban = None
        if _is_bannable_path(request.path) and ip:
            ban = find_effective_ban(ip)
            request.ip_ban = ban
            if ban is not None and request.path.startswith('/api/'):
                return JsonResponse({
                    'code': StatusCode.IP_BANNED,
                    'msg': f'IP 已被封禁：{ban.reason}',
                    'data': None,
                })
        return self.get_response(request)


def _is_bannable_path(path: str) -> bool:
    """该路径是否参与 IP 封禁判定（控制台与后台入口永远放行）"""
    return not (path.startswith('/console/') or path.startswith('/admin/'))
