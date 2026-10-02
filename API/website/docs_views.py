"""API 文档中心视图：文档目录 / 服务文档页 / 在线调试代调代理

在线调试设计：
- 文档页表单把参数提交到本模块 `/docs/_call/`（JSON），由服务端转发到真实
  /api/ 端点，浏览器不直连、不持有密钥；
- 用户如需调用“需签名”的接口，在文档页填写自己的 APPID/APPSECRET，随本次请求
  提交到服务端完成 HMAC-SHA256 签名后转发（密钥不落库、不响应回前端）；
- 开放（open）端点可不填凭据直接调试；
- 仅允许转发注册表（API.website.docs.ALL_ENDPOINTS）中已声明的端点路径；
- SSE 响应（AI 接口 stream=true）逐块透传，调试面板可逐字打印，其余响应仍为一次性 JSON。
"""
import html
import json
import secrets
import time
from urllib.parse import urlencode

import markdown
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from API.apis.user_center.sign import build_sign
from API.common import StatusCode, api_stats_query
from .docs import ALL_ENDPOINT_SPECS, ALL_ENDPOINTS, all_docs, get_doc, localize
from .services import SERVICES, localize as localize_services

# 调试面板回显的正文上限：超过即截断。
# 某些接口（如短剧出流）返回的是几十 MB 的二进制流，若不限制，正文会被读进内存、
# 序列化成 JSON（非 ASCII 转义后还会膨胀）再交给浏览器渲染 —— 实测 39MB 视频变成
# 50MB 的 JSON 响应，页面直接卡死。故二进制/流式响应一律不回显正文。
_TEXT_LIMIT = 200 * 1024


def _is_textual(content_type):
    """该响应正文是否适合在调试面板里回显（文本 / JSON / XML 等）"""
    ctype = (content_type or '').split(';')[0].strip().lower()
    return (ctype.startswith('text/')
            or ctype in ('application/json', 'application/xml', 'application/javascript',
                         'application/x-www-form-urlencoded')
            or ctype.endswith('+json') or ctype.endswith('+xml'))


# 请求方法对应的徽标配色（模式徽标/接口目录共用；未列出的方法用中性灰）
METHOD_BADGES = {'GET': 'badge-success', 'POST': 'badge-info',
                 'PATCH': 'badge-warning', 'DELETE': 'badge-error'}


def index(request):
    """/docs/ 文档目录：左侧为全量服务导航（见中间件注入 docs_menu），
    右侧按“服务对外状态”展示全量服务卡（可进入的 = 已接入文档且非 开发中/已下线）。

    服务策略里被设为「文档隐藏」的服务不在此展示（见 middleware.is_docs_hidden）。
    """
    from API.common.middleware import is_docs_hidden
    from .service_status import STATUS_KEYS, annotate as _annotate_status, status_def
    by_prefix = {d.prefix: d for d in all_docs() if not is_docs_hidden(d.prefix)}
    services = []
    for svc in _annotate_status(localize_services(SERVICES), lambda p: p in by_prefix):
        if is_docs_hidden(svc['url_prefix']):
            continue
        doc = by_prefix.get(svc['url_prefix'])
        if doc is not None:
            svc = {**svc, 'slug': doc.slug, 'channel_count': len(doc.channels)}
        services.append(svc)
    return render(request, 'docs/index.html', {
        'services': services,
        'online_count': sum(1 for s in services if s['status'] in ('normal', 'dev', 'maintenance')),
        # 状态图例（含图标）取自 service_status，避免模板重复维护状态文案与配色
        'status_legend': [status_def(key) for key in STATUS_KEYS],
    })


def errors(request):
    """/docs/errors/ 对外错误码总表：按状态码类别分组，给出触发场景与处理建议。

    内容源见 API.website.docs.errors（只收录真的会返回的码）。
    """
    from .docs.errors import error_groups
    groups = error_groups()
    return render(request, 'docs/errors.html', {
        'groups': groups,
        'total': sum(len(group['codes']) for group in groups),
    })


@require_GET
@never_cache
def my_projects(request):
    """/docs/_projects/ 当前访客可选用的接入项目（含密钥）

    文档页右侧「鉴权设置」卡的下拉数据源：选中即自动填入 APPID / APPSECRET，
    省得手抄。**密钥只在这个响应里下发**，不写进文档页 HTML
    —— 文档页是公开且可被缓存的，把密钥渲染进去会被缓存 / 分享出去。

    取谁的项目：项目一律由后台管理员创建、不再归属到具体用户，因此**只对 Django 超管会话
    下发全部启用项目**（超管本就能在控制台看到所有密钥）；其余访客一律空列表，不泄露信息。
    """
    from API.models import UserApp

    if getattr(request.user, 'is_superuser', False):
        apps = UserApp.objects.filter(status=True)
    else:
        apps = UserApp.objects.none()
    projects = [{'app_id': app.app_id, 'name': app.name, 'app_secret': app.app_secret}
                for app in apps.order_by('name')]
    return JsonResponse({'code': StatusCode.SUCCESS, 'msg': '成功',
                         'data': {'projects': projects}})


# 说明文本的 Markdown 渲染。
# 各服务文档的「服务说明 / 线路说明 / 端点备注 / 参数说明」本来就按 Markdown 书写
# （**加粗**、`代码`、列表），若原样交给模板只会把记号显示出来，故渲染前统一转成 HTML。
# 扩展只用 extra（表格 / 围栏代码 / 定义列表）与 sane_lists（列表紧贴段落也能解析）。
_MD_EXTENSIONS = ['extra', 'sane_lists']


def _md(text: str) -> str:
    """整段 Markdown → HTML（块级：标题 / 列表 / 表格 / 围栏代码都渲染）

    先转义原始 HTML 再转换：说明里存在 `<topic_id>`、`<img src>` 这类**本来就该显示出来**
    的占位符，不转义会被浏览器当成未知标签直接吞掉（这是声明式文本，不是可执行 HTML）。
    """
    return markdown.markdown(html.escape(text), extensions=_MD_EXTENSIONS) if text else ''


def _md_inline(text: str) -> str:
    """行内 Markdown → HTML

    给本来就嵌在 <p> / <li> 里的短句用（参数说明、端点备注、线路说明）：只保留
    **加粗**、`代码`、链接这类行内标记，并剥掉 markdown 自动包上的单层 <p>，
    避免渲染出 <p> 套 <p> 这种非法结构。多段落时保持原样交给浏览器处理。
    """
    out = _md(text)
    if out.count('<p>') == 1 and out.startswith('<p>') and out.endswith('</p>'):
        return out[3:-4]
    return out


def _attach_markdown(doc):
    """把声明里的说明文本渲染成 HTML 挂到文档副本上（供模板直接 |safe 输出）

    必须在 localize() 之后调用：.po 里存的是**带 Markdown 记号的原文**，先翻译再渲染，
    两种语言的记号才会一致（顺序反过来会把 HTML 当词条去查译文）。
    """
    doc.intro_html = _md('\n\n'.join(doc.intro))
    for channel in doc.channels:
        channel.note_html = _md_inline(channel.note)
        for endpoint in channel.endpoints:
            endpoint.notes_html = [_md_inline(n) for n in endpoint.notes]
            for param in endpoint.params:
                param.desc_html = _md_inline(param.desc)
            # 响应字段表：按字段路径算缩进层级（`list[].id` → 1、`a.b.c` → 2），
            # 让一张扁平表在页面上呈现层级；嵌套说明不需要另建树形结构
            for field_spec in endpoint.response_fields:
                field_spec.indent = _field_indent(field_spec.name)


def _field_indent(name):
    """字段路径的缩进层级：按 `.` 分段，段数 - 1（顶层字段为 0）"""
    return max(0, len([part for part in str(name).split('.') if part]) - 1)


def service(request, slug: str):
    """/docs/<slug>/ 单个服务文档页（线路 tab + 端点调试）

    服务策略里被设为「文档隐藏」的服务 / 端点不会出现在本页：服务级隐藏返回 404，
    端点级隐藏从列表中移除（某线路下端点全部隐藏时，该线路也不再展示）。
    """
    from API.common.middleware import is_docs_hidden
    from .service_status import annotate as _annotate_status, channel_status_fields
    doc = get_doc(slug)
    if doc is None or is_docs_hidden(doc.prefix):
        return render(request, '404.html', status=404)
    doc = localize(doc)  # 文档内容按当前语言翻译（副本）
    doc.channels = [channel for channel in doc.channels
                    if any(not is_docs_hidden(ep.path) for ep in channel.endpoints)]
    for channel in doc.channels:
        channel.endpoints = [ep for ep in channel.endpoints if not is_docs_hidden(ep.path)]
    # 累计调用次数（全部历史）：公开信息，未登录也能看到每个接口被调用了多少次
    counts = api_stats_query.endpoint_call_counts(
        [ep.path for channel in doc.channels for ep in channel.endpoints])
    for channel in doc.channels:
        endpoint_paths = [ep.path for ep in channel.endpoints]
        for endpoint in channel.endpoints:
            endpoint.call_count = counts.get(endpoint.path, 0)
            endpoint.method_badge = METHOD_BADGES.get(endpoint.method, 'badge-ghost')
            # 库内账号选择器：本服务声明了账号查询接口、且该端点用 account_id 传登录凭据时渲染
            # （取库内账号 UUID 的端点都能靠它一键填入，省得手抄）
            if doc.account_search_path and any(p.name == 'account_id' for p in endpoint.params):
                endpoint.account_picker_path = doc.account_search_path
        # 线路状态（取该线路下端点最严重者）：与左侧导航同源，供顶部线路 Tab 显示状态图标
        for field, value in channel_status_fields(endpoint_paths).items():
            setattr(channel, field, value)
    # 超管发布的接口公告（服务 / 线路 / 端点三级）
    _attach_announcements(doc)
    # 动态下拉选项（声明里只写 dynamic_options 名字，如 AI 模型清单来自数据库）
    _resolve_dynamic_options(doc)
    # 说明类文本按 Markdown 渲染成 HTML（翻译之后再做，见 _attach_markdown）
    _attach_markdown(doc)
    # 本机凭据（声明 local=True 的参数，如抖音登录 Cookie）：不在参数表单里渲染，
    # 改由右侧栏「本机凭据」卡片提供。同一凭据可能被多个端点复用，按参数名去重，
    # 展示信息取首次声明的那一份（label / 说明 / 占位符，此时已翻译并渲染好 HTML）。
    local_params, seen_names = [], set()
    for channel in doc.channels:
        for endpoint in channel.endpoints:
            for param in endpoint.params:
                if param.local and param.name not in seen_names:
                    seen_names.add(param.name)
                    local_params.append(param)
    # 是否真的渲染出了公告（有则加载公告条的展开 / 关闭增强脚本）
    has_announcement = bool(
        doc.announcements
        or any(channel.announcements for channel in doc.channels)
        or any(ep.announcements for channel in doc.channels for ep in channel.endpoints))
    # 服务状态（服务策略优先）；已接入文档的服务默认正常，非正常态在页面顶部给横幅提示
    status = _annotate_status([{'url_prefix': doc.prefix}], lambda p: True)[0]
    # 是否存在需要在线播放器的端点（如 m3u8 播放地址），有则加载播放器脚本
    has_player = any(ep.player for channel in doc.channels for ep in channel.endpoints)
    # 是否存在图片解码类端点（声明了 image_help），有则加载图片预览脚本
    has_image = any(ep.image_help for channel in doc.channels for ep in channel.endpoints)
    # 是否存在注册辅助 UI（一键填写 / 批量注册面板），有则加载注册辅助脚本
    has_register_ui = any(ep.auto_fill_path or ep.batch_register_path
                          for channel in doc.channels for ep in channel.endpoints)
    # 是否存在「参数选择器」面板（账号选择器 / 礼物面板），有则加载对应脚本
    has_picker = any(ep.gift_picker_path or getattr(ep, 'account_picker_path', '')
                     for channel in doc.channels for ep in channel.endpoints)
    # 是否存在返回 Markdown 正文的端点（如 AI 对话），有则加载 marked 与渲染脚本
    has_markdown = any(ep.markdown for channel in doc.channels for ep in channel.endpoints)
    # 本服务端点总数：供「接口目录」浮窗显示数量（仅 1 个端点时不渲染该浮窗）
    endpoint_count = sum(len(channel.endpoints) for channel in doc.channels)
    return render(request, 'docs/service.html',
                  {'doc': doc, 'status': status, 'has_player': has_player, 'has_image': has_image,
                   'has_register_ui': has_register_ui, 'has_picker': has_picker,
                   'has_markdown': has_markdown,
                   'has_announcement': has_announcement,
                   'local_params': local_params,
                   'endpoint_count': endpoint_count})


def _attach_announcements(doc):
    """把生效中的公告按 服务 / 线路 / 端点 三级挂到文档对象上（超管在后台发布）

    挂载口径与服务树 / 服务策略完全一致，见 ``service_tree.normalize_endpoint_path()``：
    服务级比对 ``doc.prefix``，线路级比对服务树里的线路前缀，端点级比对归一化后的端点路径。
    无公告时零开销：先查库，查不到就直接返回，不遍历服务树。
    """
    from API.models import Announcement
    from .service_tree import normalize_endpoint_path, service_node

    # 先给三级都置空，模板里可直接遍历，不必判存在性
    doc.announcements = []
    for channel in doc.channels:
        channel.announcements = []
        for endpoint in channel.endpoints:
            endpoint.announcements = []

    visible = list(Announcement.visible_queryset())     # 已按 sort / create_time 排序
    if not visible:
        return
    grouped = {}
    for item in visible:
        grouped.setdefault((item.scope, item.path_prefix), []).append(item)

    doc.announcements = grouped.get(('service', doc.prefix), [])
    node = service_node(doc.prefix)
    channel_prefixes = ({ch['slug'].lower(): ch['prefix'] for ch in node['channels']}
                        if node else {})
    for channel in doc.channels:
        prefix = channel_prefixes.get((channel.slug or '').lower())
        if prefix:
            channel.announcements = grouped.get(('channel', prefix), [])
        for endpoint in channel.endpoints:
            key = normalize_endpoint_path(endpoint.path)
            endpoint.announcements = grouped.get(('endpoint', key), [])


def _resolve_dynamic_options(doc):
    """把声明里 dynamic_options 指定的下拉选项在渲染前填好

    选项来自运行期数据（当前是 AI 模型清单，存在 ai_model 表里）。
    声明只写提供者名字，取值逻辑集中注册在 ``docs.OPTION_LOADERS``，
    避免把「会变的清单」写死在文档声明里。
    """
    from .docs import OPTION_LOADERS
    for channel in doc.channels:
        for endpoint in channel.endpoints:
            for param in endpoint.params:
                name = getattr(param, 'dynamic_options', '')
                if not name:
                    continue
                loader = OPTION_LOADERS.get(name)
                param.options = loader() if loader else []


def _read_json_body(request):
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _stream_through(response):
    """把内层 SSE 响应原样逐块透传给浏览器（如 AI 接口 stream=true）

    内层响应来自 django.test.Client，迭代 streaming_content 会驱动视图里的生成器，
    因此上游每吐一块这里就转发一块，文档页得以逐字打印；若按普通响应处理（把整条流
    join 起来再序列化成 JSON），实时性就没了。

    仅在「内层响应本身是 SSE」时走这里：参数校验失败等场景返回的是普通 JSON，
    仍走 call() 里的一次性分支，行为与从前完全一致。
    """
    def relay():
        try:
            for chunk in response.streaming_content:
                yield chunk
        finally:
            response.close()          # 客户端提前断开 / 正常结束都释放上游连接

    out = StreamingHttpResponse(relay(), content_type=response['Content-Type'],
                                status=response.status_code)
    out['Cache-Control'] = 'no-cache'
    out['X-Accel-Buffering'] = 'no'   # 禁用 nginx 缓冲，保证分片逐块抵达浏览器
    return out


def _shell_quote(value) -> str:
    """POSIX shell 单引号转义：拼出的 curl 要能直接粘进终端执行"""
    return "'" + str(value).replace("'", "'\\''") + "'"


def _param_pairs(params):
    """把 {k: v} / {k: [v1, v2]} 摊平成 [(k, v)]（同名多值 = 多次传参）"""
    pairs = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(item)) for item in value)
        else:
            pairs.append((key, str(value)))
    return pairs


def _curl_command(base_url, method, groups, auth_params, files):
    """由本次实际转发的请求拼出「等价 curl」，供调试面板一键复制

    形态与代调转发完全一致（粘贴执行即可复现本次请求）：
      GET    —— 业务参数与签名参数都在 query；
      POST   —— 两者都在 urlencoded 表单体（与签名口径一致）；含文件时用 -F（文件路径留占位符）；
      PATCH  —— 签名参数在 query（非 POST 的 request.POST 为空），业务参数在 urlencoded 体；
      DELETE —— 签名参数在 query，业务参数（如有）以 JSON 体发送。
    """
    def body_pairs(params):
        out = []
        for key, value in _param_pairs(params):
            out.append('-d ' + _shell_quote(f'{key}={value}'))
        return out

    if method == 'GET':
        query = urlencode({**groups, **auth_params}, doseq=True)
        return ' \\\n  '.join(['curl', _shell_quote(f'{base_url}?{query}' if query else base_url)])

    if method == 'POST':
        lines = ['curl -X POST', _shell_quote(base_url)] + body_pairs({**groups, **auth_params})
        lines += ['-F ' + _shell_quote(f'{name}=@<本地文件路径>') for name in files]
        return ' \\\n  '.join(lines)

    if method == 'PATCH':
        query = urlencode(auth_params, doseq=True)
        url = f'{base_url}?{query}' if query else base_url
        return ' \\\n  '.join(['curl -X PATCH', _shell_quote(url)] + body_pairs(groups))

    # DELETE
    query = urlencode(auth_params, doseq=True)
    url = f'{base_url}?{query}' if query else base_url
    lines = ['curl -X DELETE', _shell_quote(url)]
    if groups:
        lines += ['-H ' + _shell_quote('Content-Type: application/json'),
                  '-d ' + _shell_quote(json.dumps(groups, ensure_ascii=False))]
    return ' \\\n  '.join(lines)


@require_POST
def call(request):
    """在线调试代调：白名单 + 可选代签 + 转发真实 /api/ 端点

    支持 GET / POST / PATCH / DELETE；URL 模板中的路径占位符（如 <uuid> / <id>）
    由端点文档声明（EndpointSpec.path_params）指定用哪个业务参数替换；同名重复字段
    （如 singer）以多次传参发送，签名按服务端 POST.dict()（取同名最后一项）的口径
    计算，保证验签一致。
    """
    # 解析载荷：支持两种提交方式
    # 1) JSON（老方式，无文件）：{path, method, params, app_id, app_secret}
    # 2) multipart/form-data（新方式，可携带真实文件上传）：
    #    path/method/app_id/app_secret + 业务字段同名多次 + 文件字段按参数名
    payload = None
    files = {}
    if 'application/json' in (request.content_type or ''):
        payload = _read_json_body(request)
        if payload is None:
            return JsonResponse({'http_status': 400, 'json': None,
                                 'text': '请求体必须是 JSON 对象'})
    else:
        # multipart/form-data：Django 已在 CSRF/中间件阶段解析过 POST/FILES，
        # 这里禁止再读 request.body（会抛 RawPostDataException）
        if not (request.POST.get('path') or '').strip():
            return JsonResponse({'http_status': 400, 'json': None,
                                 'text': '请求体必须是 JSON 对象或包含 path 的表单'})
        files = {}
        for _fname, _up in request.FILES.items():
            # 读字节重建新文件对象再转发，避免外层 UploadedFile 生命周期问题
            from django.core.files.uploadedfile import SimpleUploadedFile
            files[_fname] = SimpleUploadedFile(
                _up.name or _fname, _up.read(),
                content_type=_up.content_type or 'application/octet-stream')
        params = {}
        for key, values in request.POST.lists():
            if key in ('path', 'method', 'app_id', 'app_secret'):
                continue
            cleaned = [v for v in values if v not in (None, '') and str(v).strip() != '']
            if cleaned:
                params[key] = cleaned[0] if len(cleaned) == 1 else cleaned
        payload = {
            'path': (request.POST.get('path') or '').strip(),
            'method': (request.POST.get('method') or '').upper().strip(),
            'app_id': (request.POST.get('app_id') or '').strip(),
            'app_secret': (request.POST.get('app_secret') or '').strip(),
            'params': params,
        }

    path = (payload.get('path') or '').strip()
    declared_path = path                     # 计算属性用声明路径（含 <uuid>/<id> 占位符）
    method = (payload.get('method') or '').upper().strip()
    allowed_methods = ALL_ENDPOINTS.get(path)
    if not allowed_methods:
        return JsonResponse({'http_status': 404, 'json': None,
                             'text': '不允许调试的接口路径（未在文档注册表中声明）'})
    # 「文档隐藏」的端点不得在此调试（本调试页是公开的，与之同源）
    from API.common.middleware import is_docs_hidden
    if is_docs_hidden(declared_path):
        return JsonResponse({'http_status': 404, 'json': None,
                             'text': '不允许调试的接口路径（未在文档注册表中声明）'})
    if method not in allowed_methods:
        return JsonResponse({'http_status': 400, 'json': None,
                             'text': f'该接口仅支持 {" / ".join(sorted(allowed_methods))}，请勿篡改请求方法'})

    raw_params = payload.get('params') or {}
    # 归一化：字符串单值 / 数组多值（数组 = 同名多次传参）
    groups = {}
    for key, value in raw_params.items():
        if isinstance(value, (list, tuple)):
            cleaned = [str(v) for v in value if v not in (None, '') and str(v).strip()]
            if not cleaned:
                continue
            groups[str(key)] = cleaned if len(cleaned) > 1 else cleaned[0]
        else:
            if value in (None, '') or str(value).strip() == '':
                continue
            groups[str(key)] = str(value)

    # 路径占位符替换（按端点在文档中声明的 path_params 取值并移出业务参数）：
    #   如 {'uuid': 'account_id'} 表示把表单里的 account_id 填进 URL 的 <uuid>。
    #   声明见各服务文档模块的 EndpointSpec(path_params=...)。
    ep_spec = ALL_ENDPOINT_SPECS.get(declared_path)
    for holder, param_name in ((ep_spec.path_params if ep_spec else None) or {}).items():
        placeholder = f'<{holder}>'
        if placeholder not in path:
            continue
        val = groups.pop(param_name, None)
        if val is None or isinstance(val, list):
            return JsonResponse({'http_status': 400, 'json': None,
                                 'text': f'该接口需要路径参数 {param_name}'})
        path = path.replace(placeholder, str(val))

    # 签名口径：与中间件一致 —— 取同名参数的“最后一个值”（POST.dict() 行为）
    collapsed = {k: (v if not isinstance(v, list) else v[-1]) for k, v in groups.items()}

    app_id = (payload.get('app_id') or '').strip()
    app_secret = (payload.get('app_secret') or '').strip()

    if app_id and app_secret:
        auth_params = {
            'app_id': app_id,
            'timestamp': str(int(time.time())),
            'nonce': secrets.token_hex(16),
        }
        if method in ('PATCH', 'DELETE'):
            # PATCH/DELETE 的 request.POST 为空，中间件只校验 query 中的签名参数，
            # 故签名仅覆盖签名参数本身（业务字段走表单体/无体，不参与验签）
            auth_params['sign'] = build_sign(dict(auth_params), app_secret)
        else:
            auth_params['sign'] = build_sign({**collapsed, **auth_params}, app_secret)
    else:
        auth_params = {}

    if files and method != 'POST':
        return JsonResponse({'http_status': 400, 'json': None,
                             'text': '文件上传仅支持 POST 接口'})

    # 等价 curl（供面板一键复制）：必须在路径占位符替换、签名参数生成之后拼，
    # 才能反映本次真正发出去的请求。needs_sign 用与中间件同口径的 requires_auth 判定。
    from API.common.middleware import requires_auth
    curl_text = _curl_command(request.build_absolute_uri(path), method,
                              groups, auth_params, files)
    curl_meta = {'curl': curl_text,
                 'signed': bool(auth_params),
                 'needs_sign': requires_auth(declared_path)}

    # 站内转发（复用同一 Django 进程，完整走一遍认证/业务中间件）
    from django.test import Client
    client = Client(raise_request_exception=False)
    started = time.monotonic()

    # 转发时把**原始 Host 与协议**带上：测试客户端的默认 host 是 testserver，
    # 不带上，子请求里 request.build_absolute_uri() 就会拼出 `http://testserver/...`，
    # 而这类「绝对地址」正是要展示给用户去播放的（如短剧播放地址），复制出去根本打不开。
    forwarded = {'HTTP_HOST': request.get_host()}
    if request.is_secure():
        forwarded['wsgi.url_scheme'] = 'https'

    if method == 'GET':
        response = client.get(path, {**groups, **auth_params}, **forwarded)
    elif method == 'PATCH':
        # 非 POST 方法 request.POST 为空：签名公共参数放 query，
        # 业务字段以 urlencoded 字符串作为表单体（Django 测试客户端不自动编码 dict）
        response = client.patch(path, urlencode(groups, doseq=True),
                                content_type='application/x-www-form-urlencoded',
                                QUERY_STRING=urlencode(auth_params), **forwarded)
    elif method == 'DELETE':
        if groups:
            # 需要业务参数的 DELETE（如静态代理按 ip:port 删除）：
            # 业务字段以 JSON body 传递（非 POST 的 request.POST 为空，不参与验签），
            # 签名公共参数仍放 query，与中间件验签口径一致。
            response = client.delete(path, data=json.dumps(groups),
                                     content_type='application/json',
                                     QUERY_STRING=urlencode(auth_params), **forwarded)
        else:
            response = client.delete(path, QUERY_STRING=urlencode(auth_params), **forwarded)
    else:  # POST（含文件上传）
        # Client.post 默认 multipart：文件对象需随 data 一起传（无独立 files 参数）
        body = {**groups, **auth_params}
        if files:
            body.update(files)
        response = client.post(path, body, **forwarded)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    content_type = response['Content-Type']

    # SSE 响应（AI 接口 stream=true）逐块透传，让调试面板真正流式打印。
    # 必须放在 _is_textual 判断之前：text/event-stream 也属于 text/*，否则会被
    # 当成普通文本整条读完再一次性返回。
    if (content_type or '').split(';')[0].strip().lower() == 'text/event-stream':
        return _stream_through(response)

    # 二进制 / 流式正文（如短剧出流返回 video/mp4）不回显：这类响应动辄几十 MB，
    # 读进内存再序列化成 JSON 会把浏览器卡死（实测 39MB 视频 → 50MB JSON 响应）。
    # 这类接口本来就是给 <video> / 播放器直接访问的，调试面板只回状态与大小。
    if not _is_textual(content_type):
        response.close()                      # 释放底层文件句柄，不消费正文
        # 面板既然不回显正文，就必须把「地址」交出来 —— 否则用户拿到一句「请把该地址交给
        # 播放器」，却在页面上找不到该复制哪一段。
        # 只拼**业务参数**，不带本次生成的签名参数：签名是一次性的（nonce 在有效窗口内
        # 重复即判重放），原样贴到浏览器再发一次会被拒，带上反而让人以为地址是坏的。
        # 需要签名的接口因此本来就不能这样直开（下面按 needs_sign 提示），免签接口（如短剧出流）可以。
        open_url = ''
        if method == 'GET':
            query = urlencode(groups, doseq=True)
            open_url = request.build_absolute_uri(f'{path}?{query}' if query else path)
        return JsonResponse({
            'http_status': response.status_code,
            'elapsed_ms': elapsed_ms,
            'content_type': content_type,
            'content_length': response.get('Content-Length') or '',
            'json': None,
            'open_url': open_url,
            'text': '该接口返回二进制 / 流式内容（如视频流），调试面板不回显正文；'
                    '请把该地址直接交给播放器或浏览器打开。',
            **curl_meta,
        })

    # 其余流式文本响应（非 SSE）没有 .content，必须先消费 streaming_content；
    # 否则读取时会抛 AttributeError 让调试接口整个 500（原实现只按普通响应处理）。
    if response.streaming:
        # 消费内层流式正文后必须显式关闭：中途异常（解码失败 / 上游断流）时若只依赖 GC，
        # 底层连接与临时文件会在不确定的时间才被回收（与 _stream_through 的口径一致）。
        try:
            raw = b''.join(response.streaming_content).decode('utf-8', 'ignore')
        finally:
            response.close()
    else:
        raw = response.content.decode('utf-8', 'ignore')
    parsed = None
    if content_type.startswith('application/json'):
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
    if len(raw) > _TEXT_LIMIT:                # 先解析再截断，避免大 JSON 因截断而解析失败
        raw = raw[:_TEXT_LIMIT] + f'\n…（正文超过 {_TEXT_LIMIT // 1024} KB，已截断）'

    return JsonResponse({
        'http_status': response.status_code,
        'elapsed_ms': elapsed_ms,
        'content_type': content_type,
        'json': parsed,
        'text': raw,
        **curl_meta,
    })
