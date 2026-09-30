"""API 服务树（服务 → 线路 → 端点）运行期枚举

供超管控制台「服务策略」页的三级联动下拉使用，后续文档中心也可复用。

数据源与取舍：
1. **以 Django URLconf 的真实路由为准**：递归遍历 ``django.urls.get_resolver()``，
   只取 ``/api/`` 前缀下的 URLPattern 叶子路由（``re_path`` 的兜底路由如 ``^api/.*$``
   会被自然排除）。层级按路径段划分：``/api/<service>/`` 为服务级、
   ``/api/<service>/<channel>/`` 为线路级、更长的完整路径为端点级。
2. **文档注册表用于补中文名并归类**：读 ``API/website/docs`` 的 ``all_docs()``，
   按服务前缀（精确）与线路 slug（忽略大小写）匹配，把真实路由归类到具体服务 / 线路，
   并用文档声明的端点路径补端点名。文档里没有登记的路由，名称回退为路径片段 slug，
   并在返回值里标记 ``registered=False``。

之所以以真实路由为准（而不是直接照抄文档注册表）：策略的 ``path_prefix`` 必须能真实
命中请求路径，只有 URLconf 才是「哪些路径真实存在」的唯一权威；文档注册表可能滞后于代码。

含参数的路由要截断：``/api/movies/movie_555/detail/<str:id>`` 的端点路径截为
``/api/movies/movie_555/detail``（参数段及其之后全部丢弃），否则前缀匹配永远失效。
"""
from django.urls import URLPattern, URLResolver, get_resolver

# 服务前缀固定以「/api/」开头，且服务 / 线路前缀带结尾斜杠（目录式），
# 仅当该层本身是一条「裸路由」（如 /api/seo/friend_links）时才省略结尾斜杠，
# 以保证前缀能同时命中「裸路径」与「其下子路径」。
_API_ROOT = '/api/'


def _iter_routes(resolver=None, prefix=''):
    """递归遍历 URLconf，产出全部叶子路由的完整路径串（含未截断的参数段）"""
    resolver = resolver or get_resolver()
    for pattern in resolver.url_patterns:
        text = str(pattern.pattern)
        full = prefix + text
        if isinstance(pattern, URLResolver):
            yield from _iter_routes(pattern, full)
        elif isinstance(pattern, URLPattern):
            yield full


def _truncate(full):
    """把一条完整路由截断为「端点路径」；不在 /api/ 下或为空则返回 None

    截断规则：遇到第一个含参数（``<...>``）的段即停止，其后全部丢弃。
    """
    segments = [seg for seg in full.split('/') if seg]
    kept = []
    for seg in segments:
        if '<' in seg:
            break
        kept.append(seg)
    if not kept or kept[0] != 'api':
        return None
    return '/' + '/'.join(kept)


def _all_api_paths():
    """全部 /api/ 下真实路由的（去重、已截断）路径，按字典序返回"""
    paths = set()
    for full in _iter_routes():
        path = _truncate(full)
        if path and path.startswith(_API_ROOT):
            paths.add(path)
    return sorted(paths)


def _doc_index():
    """构建文档索引：服务前缀 -> 文档；以及「端点基线路径 -> 端点名」映射

    端点基线路径 = 文档里声明的端点路径同样按参数段截断后的结果，便于与
    真实路由截断后的路径对齐（文档里带占位符的写法也能命中）。
    """
    from .docs import all_docs

    by_prefix = {}
    endpoint_names = {}
    for doc in all_docs():
        by_prefix[doc.prefix] = doc
        for channel in doc.channels:
            for endpoint in channel.endpoints:
                base = _truncate(endpoint.path.lstrip('/'))
                if base:
                    endpoint_names.setdefault(base, endpoint.name)
    return by_prefix, endpoint_names


def service_tree():
    """枚举 API 服务树（服务 → 线路 → 端点）

    返回结构::

        [{'slug', 'name', 'prefix', 'registered',
          'channels': [{'slug', 'name', 'prefix', 'registered',
                        'endpoints': [{'path', 'name', 'registered'}]}]}]
    """
    by_prefix, endpoint_names = _doc_index()

    # 先按真实路由分段归类：service -> channel -> endpoints
    services = {}
    for path in _all_api_paths():
        segments = [seg for seg in path.strip('/').split('/') if seg]  # 含前导 'api'
        if len(segments) < 3:
            # /api/<service> 本身：只登记服务，没有线路 / 端点
            if len(segments) == 2:
                services.setdefault(segments[1], {'channels': {}})
            continue
        service_slug = segments[1]
        channel_slug = segments[2]
        node = services.setdefault(service_slug, {'channels': {}})
        channel = node['channels'].setdefault(
            channel_slug, {'endpoints': set(), 'bare': False})
        if len(segments) == 3:
            # /api/<svc>/<ch> 本身是一条「裸路由」：该层即线路（其下暂无更深端点），
            # 线路前缀不带结尾斜杠，以同时命中裸路径与其下（将来新增的）子路径
            channel['bare'] = True
        else:
            channel['endpoints'].add(path)

    tree = []
    for service_slug in sorted(services):
        service_prefix = f'{_API_ROOT}{service_slug}/'
        doc = by_prefix.get(service_prefix)
        channels = []
        for channel_slug in sorted(services[service_slug]['channels']):
            raw = services[service_slug]['channels'][channel_slug]
            bare = raw['bare']
            endpoint_paths = sorted(raw['endpoints'])
            channel_prefix = f'{_API_ROOT}{service_slug}/{channel_slug}' + ('' if bare else '/')

            doc_channel = None
            if doc is not None:
                doc_channel = next(
                    (ch for ch in doc.channels if ch.slug.lower() == channel_slug.lower()), None)
            # 线路名：文档线路名 -> 文档端点名（该层本身即端点）-> slug
            if doc_channel is not None:
                channel_name, channel_registered = doc_channel.name, True
            elif channel_prefix in endpoint_names:
                channel_name, channel_registered = endpoint_names[channel_prefix], True
            else:
                channel_name, channel_registered = channel_slug, False

            endpoints = []
            for path in endpoint_paths:
                if path in endpoint_names:
                    endpoints.append(
                        {'path': path, 'name': endpoint_names[path], 'registered': True})
                else:
                    endpoints.append({
                        'path': path,
                        'name': path.strip('/').split('/')[-1],
                        'registered': False,
                    })

            channels.append({
                'slug': channel_slug,
                'name': channel_name,
                'prefix': channel_prefix,
                'registered': channel_registered,
                'endpoints': endpoints,
            })

        tree.append({
            'slug': service_slug,
            'name': doc.name if doc is not None else service_slug,
            'prefix': service_prefix,
            'registered': doc is not None,
            'channels': channels,
        })
    return tree


def choices():
    """供控制台三级联动下拉使用的枚举数据（等价于 service_tree()）"""
    return service_tree()


def normalize_endpoint_path(path):
    """把「文档里声明的端点路径」归一为服务树 / 服务策略使用的真实路由口径

    文档声明可能带参数段（如 ``/api/seo/friend_links/<id>``），而服务树与
    ``ApiServicePolicy.path_prefix`` 用的都是截断后的路径（``/api/seo/friend_links``）。
    所有按路径挂载的数据（策略、公告）都必须用同一口径，否则前后台对不上。
    """
    return _truncate(path) or path


def service_node(prefix):
    """按服务前缀取服务树节点（找不到返回 None），供需要线路前缀的调用方复用"""
    return next((svc for svc in service_tree() if svc['prefix'] == prefix), None)
