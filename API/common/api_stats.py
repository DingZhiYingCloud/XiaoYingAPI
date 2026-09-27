"""API 调用统计：进程内缓冲 + 批量写入（按天 / 按小时双粒度预聚合）

设计要点：
1. **不落明细**：每次调用只在进程内累加，满 FLUSH_THRESHOLD 条或每 FLUSH_INTERVAL_SECONDS 秒
   批量写库，避免每个请求都写 SQLite。同时累加两个粒度：
   - 按天（ApiCallStat，全历史）：键 = 日期 + 端点 + 项目 + 状态码
   - 按小时（ApiCallStatHour，保留近 HOUR_RETENTION_DAYS 天）：键 = 上述 + 小时
   两者同一批落库、口径一致，因此保留期内「按小时汇总」与「按天合计」必然相等。
2. **多进程安全**：线上 uWSGI 多 worker 各自持有缓冲，落库用「先累加更新、无则插入」，
   并发插入冲突时退化为累加更新，因此各进程的数据最终都累加到同一行。
3. **重启最多少量数据**：缓冲未刷完时进程退出，最多丢失一个刷新窗口内的调用（已确认可接受）；
   进程正常退出时由 atexit 尽力刷一次。
4. **状态码口径**：优先取响应 JSON 里的业务 code（本项目 /api/ 统一返回 {code,msg,data}）；
   响应非 JSON 或异常时回退为 HTTP 状态码。业务 code 读取见 business_code()。
5. **统计范围**：仅 /api/ 请求；统计服务自身不计入（避免查询统计把统计刷高）；
   不存在的路径（扫描器探测）统一归并为 UNMATCHED_PATH，不打散服务榜与接口榜。

对外接口：
    record(path, cost_ms, status_code, app_id)  - 记录一次调用（缓冲区累加，必要时触发落库）
    flush()                                     - 立即把缓冲写入数据库
    service_of(path)                            - 由路径解析服务前缀
    business_code(response)                     - 由响应解析业务状态码
"""
import atexit
import json
import logging
import re
import threading
import time
from collections import defaultdict

from django.db import IntegrityError
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.urls import Resolver404, resolve
from django.utils import timezone

from API.models.Statistics.api_call_stat import NO_APP, ApiCallStat, ApiCallStatHour

logger = logging.getLogger('api.stats')

# 缓冲落库策略：满 200 个聚合键 或 每 5 秒 触发一次（任一粒度达到即落库）
FLUSH_THRESHOLD = 200
FLUSH_INTERVAL_SECONDS = 5

# 不计入统计的路径前缀（统计服务自身）
EXCLUDED_PREFIXES = ('/api/statistics/',)

# 未匹配任何真实路由的请求统一归并到这一条。
# 线上每天都在被扫描：/api/phpinfo.php、/api/.git-credentials/、/api/appsettings.json 之类，
# 每条垃圾路径若各自成行，服务榜与接口榜会被几十条无意义记录打散，真正要看的口径被淹没。
# 归并后仍能从 nginx 访问日志 / logs/app.log 查到具体被探测的路径。
UNMATCHED_PATH = '/api/_unmatched_/'

# 解析响应体取业务 code 的大小上限（字节）：更大的响应体不再解析
# （大响应体基本都是成功响应，不值得为取 code 付出解析成本）
MAX_PARSE_BYTES = 64 * 1024

# 两个粒度的聚合键字段顺序（与缓冲区 key 一一对应）
_DAY_KEY_FIELDS = ('stat_date', 'path', 'app_id', 'status_code')
_HOUR_KEY_FIELDS = ('stat_date', 'stat_hour', 'path', 'app_id', 'status_code')

# key = 聚合键元组 -> [调用次数, 总耗时, 最大耗时]
_buffer = defaultdict(lambda: [0, 0, 0])
_hour_buffer = defaultdict(lambda: [0, 0, 0])
_lock = threading.Lock()
_last_flush = time.monotonic()
_flush_thread = None

# 路径参数占位符（如 <uuid:music_id>、<id>）统一归一为该标记，避免同一接口按不同 ID 拆成多行
PARAM_PLACEHOLDER = '<param>'
_PARAM_RE = re.compile(r'<[^>]+>')
# 可安全用作统计路径的路由模板：仅由路径片段与转换器构成（正则路由如 ^api/.*$ 不适用）
_ROUTE_SAFE_RE = re.compile(r'^[\w\-./<>:]*$')


def normalize_path(path):
    """把路径里的路径参数统一归一（/musics/<uuid:music_id> -> /musics/<param>）"""
    return _PARAM_RE.sub(PARAM_PLACEHOLDER, path)


def request_path(request):
    """取用于统计的路径

    优先用「匹配到的路由模板」而非真实请求路径：带路径参数的接口
    （如 /api/music/xiaoying/musics/<uuid>）若按真实 UUID 记录，会为每个 ID 生成一行，
    行数爆炸且排行被打散；改用路由模板后可正确归并到同一行。

    拿不到路由模板时（认证被拒的请求在中间件里就返回了，Django 还没做 URL 解析；
    或路径落到 ^api/.*$ 的 404 兜底正则），再补一次解析：
    - 解析到真实路由 → 同样用**路由模板**（未签名的带参接口也不会按 ID 拆行），
      因此「被拒的真实接口」仍然可辨认，排障价值不减；
    - 解析不到 → 路径根本不存在（扫描器探测），统一归并为 UNMATCHED_PATH。
    """
    match = getattr(request, 'resolver_match', None)
    route = getattr(match, 'route', '') if match else ''
    if route and _ROUTE_SAFE_RE.match(route):
        return normalize_path('/' + route)
    resolved = _resolved_route(normalize_path(request.path))
    return UNMATCHED_PATH if resolved is None else normalize_path('/' + resolved)


def _resolved_route(path):
    """补解析路径，返回可用于统计的路由模板；解析不到或落到 404 兜底正则时返回 None

    _ROUTE_SAFE_RE 只认「路径片段 + 转换器」形式的路由模板，^api/.*$ 这类兜底正则含
    ^ $ * 会被排除，因此用它判定「解析结果是不是一条真实接口」。
    """
    try:
        match = resolve(path)
    except Resolver404:
        return None
    route = getattr(match, 'route', '')
    return route if _ROUTE_SAFE_RE.match(route) else None


def service_of(path):
    """由请求路径解析服务前缀：取 /api/ 后的第 1 段，如 /api/email/v1/send -> /api/email/"""
    parts = path.split('/')
    if len(parts) >= 3 and parts[1] == 'api' and parts[2]:
        return f'/api/{parts[2]}/'
    return '/api/'


def business_code(response):
    """取响应的业务状态码：优先 JSON 响应体里的 code，取不到则回退 HTTP 状态码"""
    content_type = response.get('Content-Type', '') or ''
    if (not response.streaming and content_type.startswith('application/json')
            and len(response.content) <= MAX_PARSE_BYTES):
        try:
            payload = json.loads(response.content)
        except (ValueError, TypeError):
            return response.status_code
        code = payload.get('code') if isinstance(payload, dict) else None
        if isinstance(code, int):
            return code
    return response.status_code


def record(path, cost_ms, status_code, app_id=NO_APP):
    """记录一次调用（进程内聚合，按需批量落库）

    同时累加按天与按小时两个粒度；任一缓冲达到阈值即触发落库。

    :param path: 请求路径
    :param cost_ms: 本次请求耗时（毫秒）
    :param status_code: 业务状态码（见 business_code）
    :param app_id: 接入项目 APPID；开放接口 / 未认证请求传 NO_APP
    """
    if not path.startswith('/api/') or path.startswith(EXCLUDED_PREFIXES):
        return

    cost = max(0, int(cost_ms))
    now = timezone.localtime()          # 本地时间（TIME_ZONE=Asia/Shanghai）
    stat_date = now.date()
    app_id = app_id or NO_APP
    code = int(status_code)

    _ensure_flush_thread()
    with _lock:
        _bump(_buffer[(stat_date, path, app_id, code)], cost)
        _bump(_hour_buffer[(stat_date, now.hour, path, app_id, code)], cost)
        due = (len(_buffer) >= FLUSH_THRESHOLD
               or len(_hour_buffer) >= FLUSH_THRESHOLD
               or (time.monotonic() - _last_flush) >= FLUSH_INTERVAL_SECONDS)
    if due:
        flush()


def _bump(item, cost):
    """把一次调用的次数与耗时累加进缓冲项（调用方需持有 _lock）"""
    item[0] += 1
    item[1] += cost
    if cost > item[2]:
        item[2] = cost


def flush():
    """把两个粒度的缓冲都写入数据库（各自独立处理，互不影响）"""
    global _last_flush
    with _lock:
        day_batch = list(_buffer.items())
        _buffer.clear()
        hour_batch = list(_hour_buffer.items())
        _hour_buffer.clear()
        _last_flush = time.monotonic()
    _flush_one(ApiCallStat, _DAY_KEY_FIELDS, day_batch, '按天')
    _flush_one(ApiCallStatHour, _HOUR_KEY_FIELDS, hour_batch, '按小时')


def _flush_one(model, key_fields, batch, label):
    """写一批聚合数据；失败只记日志丢弃（统计失败绝不冒泡到业务请求）"""
    if not batch:
        return
    try:
        _write_batch(model, key_fields, batch)
    except Exception:
        logger.exception('API 调用统计（%s）写入失败，本批 %d 个聚合键被丢弃', label, len(batch))


def _lookup(key_fields, key):
    """聚合键元组 -> ORM 查询/创建用的字段字典"""
    return dict(zip(key_fields, key))


def _accumulate(model, lookup, count, cost_sum, cost_max, now):
    """按聚合维度累加更新一行，返回受影响行数（0 表示该行还不存在）"""
    return model.objects.filter(**lookup).update(
        call_count=F('call_count') + count,
        cost_sum_ms=F('cost_sum_ms') + cost_sum,
        cost_max_ms=Greatest(F('cost_max_ms'), Value(cost_max)),
        updated_time=now,
    )


def _write_batch(model, key_fields, batch):
    """逐键写库：已存在则累加，不存在则新建"""
    now = timezone.now()
    for key, (count, cost_sum, cost_max) in batch:
        lookup = _lookup(key_fields, key)
        if _accumulate(model, lookup, count, cost_sum, cost_max, now):
            continue
        try:
            model.objects.create(
                **lookup, service=service_of(lookup['path']),
                call_count=count, cost_sum_ms=cost_sum, cost_max_ms=cost_max,
            )
        except IntegrityError:
            # 并发下已由其它进程插入同一聚合键：退化为累加更新
            _accumulate(model, lookup, count, cost_sum, cost_max, now)


def _flush_loop():
    """后台定时刷新线程（守护线程，随进程退出）"""
    from django.db import connection
    while True:
        time.sleep(FLUSH_INTERVAL_SECONDS)
        try:
            flush()
        finally:
            # 后台线程用完即关连接，避免在非请求线程上长期占用数据库连接
            connection.close()


def _ensure_flush_thread():
    """首次记录时惰性启动后台刷新线程（仅启动一次）"""
    global _flush_thread
    if _flush_thread is not None:
        return
    with _lock:
        if _flush_thread is not None:
            return
        _flush_thread = threading.Thread(target=_flush_loop, name='api-stats-flush', daemon=True)
        _flush_thread.start()


def _flush_at_exit():
    """进程退出时尽力刷一次（失败不影响退出）"""
    try:
        flush()
    except Exception:
        pass


atexit.register(_flush_at_exit)
