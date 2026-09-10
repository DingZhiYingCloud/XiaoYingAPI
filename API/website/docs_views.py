"""API 文档中心视图：文档目录 / 服务文档页 / 在线调试代调代理

在线调试设计：
- 文档页表单把参数提交到本模块 `/docs/_call/`（JSON），由服务端转发到真实
  /api/ 端点，浏览器不直连、不持有密钥；
- 用户如需调用“需签名”的接口，在文档页填写自己的 APPID/APPSECRET，随本次请求
  提交到服务端完成 HMAC-SHA256 签名后转发（密钥不落库、不响应回前端）；
- 开放（open）端点可不填凭据直接调试；
- 仅允许转发注册表（API.website.docs.ALL_ENDPOINTS）中已声明的端点路径。
"""
import json
import secrets
import time
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from API.apis.user_center.sign import build_sign
from API.common import api_stats_query
from .docs import ALL_ENDPOINTS, all_docs, get_doc, localize
from .services import SERVICES, localize as localize_services


def index(request):
    """/docs/ 文档目录：左侧为全量服务导航（见中间件注入 docs_menu），
    右侧按“服务对外状态”展示全量服务卡（可进入的 = 已接入文档且非 建设中/已下线）。"""
    from .service_status import annotate as _annotate_status
    by_prefix = {d.prefix: d for d in all_docs()}
    services = []
    for svc in _annotate_status(localize_services(SERVICES), lambda p: p in by_prefix):
        doc = by_prefix.get(svc['url_prefix'])
        if doc is not None:
            svc = {**svc, 'slug': doc.slug, 'channel_count': len(doc.channels)}
        services.append(svc)
    return render(request, 'docs/index.html', {
        'services': services,
        'online_count': sum(1 for s in services if s['status'] in ('open', 'testing', 'maintenance')),
    })


def service(request, slug: str):
    """/docs/<slug>/ 单个服务文档页（线路 tab + 端点调试）"""
    from .service_status import annotate as _annotate_status
    doc = get_doc(slug)
    if doc is None:
        return render(request, '404.html', status=404)
    doc = localize(doc)  # 文档内容按当前语言翻译（副本）
    # 累计调用次数（全部历史）：公开信息，未登录也能看到每个接口被调用了多少次
    counts = api_stats_query.endpoint_call_counts(
        [ep.path for channel in doc.channels for ep in channel.endpoints])
    for channel in doc.channels:
        for endpoint in channel.endpoints:
            endpoint.call_count = counts.get(endpoint.path, 0)
    # 服务状态（手动优先）；已接入文档的服务默认开放，非开放态在页面顶部给横幅提示
    status = _annotate_status([{'url_prefix': doc.prefix}], lambda p: True)[0]
    return render(request, 'docs/service.html', {'doc': doc, 'status': status})


def _read_json_body(request):
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


@require_POST
def call(request):
    """在线调试代调：白名单 + 可选代签 + 转发真实 /api/ 端点

    支持 GET / POST / PATCH / DELETE；URL 模板中的 <uuid> 由路径参数
    （music_id / source_id）替换；同名重复字段（如 singer）以多次传参发送，
    签名按服务端 POST.dict()（取同名最后一项）的口径计算，保证验签一致。
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
    method = (payload.get('method') or '').upper().strip()
    allowed_methods = ALL_ENDPOINTS.get(path)
    if not allowed_methods:
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

    # 路径占位符替换（从业务参数取值并移出）：
    #   <uuid> ← music_id / source_id；<id> ← link_id（数字主键）
    if '<uuid>' in path:
        path_value = None
        for key in ('music_id', 'source_id'):
            val = groups.pop(key, None)
            if val is not None and not isinstance(val, list):
                path_value = val
                break
        if not path_value:
            return JsonResponse({'http_status': 400, 'json': None,
                                 'text': '该接口需要路径参数 music_id/source_id'})
        path = path.replace('<uuid>', path_value)
    elif '<id>' in path:
        val = groups.pop('link_id', None)
        if val is None or isinstance(val, list):
            return JsonResponse({'http_status': 400, 'json': None,
                                 'text': '该接口需要路径参数 link_id'})
        path = path.replace('<id>', str(val))

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

    # 站内转发（复用同一 Django 进程，完整走一遍认证/业务中间件）
    from django.test import Client
    client = Client(raise_request_exception=False)
    started = time.monotonic()

    if method == 'GET':
        response = client.get(path, {**groups, **auth_params})
    elif method == 'PATCH':
        # 非 POST 方法 request.POST 为空：签名公共参数放 query，
        # 业务字段以 urlencoded 字符串作为表单体（Django 测试客户端不自动编码 dict）
        response = client.patch(path, urlencode(groups, doseq=True),
                                content_type='application/x-www-form-urlencoded',
                                QUERY_STRING=urlencode(auth_params))
    elif method == 'DELETE':
        if groups:
            # 需要业务参数的 DELETE（如静态代理按 ip:port 删除）：
            # 业务字段以 JSON body 传递（非 POST 的 request.POST 为空，不参与验签），
            # 签名公共参数仍放 query，与中间件验签口径一致。
            response = client.delete(path, data=json.dumps(groups),
                                     content_type='application/json',
                                     QUERY_STRING=urlencode(auth_params))
        else:
            response = client.delete(path, QUERY_STRING=urlencode(auth_params))
    else:  # POST（含文件上传）
        # Client.post 默认 multipart：文件对象需随 data 一起传（无独立 files 参数）
        body = {**groups, **auth_params}
        if files:
            body.update(files)
        response = client.post(path, body)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    raw = response.content.decode('utf-8', 'ignore')
    parsed = None
    if response['Content-Type'].startswith('application/json'):
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None

    return JsonResponse({
        'http_status': response.status_code,
        'elapsed_ms': elapsed_ms,
        'content_type': response['Content-Type'],
        'json': parsed,
        'text': raw,
    })
