"""API 调用统计：进程内缓冲 + 批量写入（按天预聚合）

设计要点：
1. **不落明细**：每次调用只在进程内按「日期 + 端点 + 项目 + 状态码」累加，满
   FLUSH_THRESHOLD 条或每 FLUSH_INTERVAL_SECONDS 秒批量写库，避免每个请求都写 SQLite。
2. **多进程安全**：线上 uWSGI 多 worker 各自持有缓冲，落库用「先累加更新、无则插入」，
   并发插入冲突时退化为累加更新，因此各进程的数据最终都累加到同一行。
3. **重启最多少量数据**：缓冲未刷完时进程退出，最多丢失一个刷新窗口内的调用（已确认可接受）；
   进程正常退出时由 atexit 尽力刷一次。
4. **状态码口径**：优先取响应 JSON 里的业务 code（本项目 /api/ 统一返回 {code,msg,data}）；
   响应非 JSON 或异常时回退为 HTTP 状态码。业务 code 读取见 business_code()。
5. **统计范围**：仅 /api/ 请求；统计服务自身不计入（避免查询统计把统计刷高）。

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
from django.utils import timezone

from API.models.Statistics.api_call_stat import NO_APP, ApiCallStat

logger = logging.getLogger('api.stats')

# 缓冲落库策略：满 200 个聚合键 或 每 5 秒 触发一次
FLUSH_THRESHOLD = 200
FLUSH_INTERVAL_SECONDS = 5

# 不计入统计的路径前缀（统计服务自身）
EXCLUDED_PREFIXES = ('/api/statistics/',)

# 解析响应体取业务 code 的大小上限（字节）：更大的响应体不再解析
# （大响应体基本都是成功响应，不值得为取 code 付出解析成本）
MAX_PARSE_BYTES = 64 * 1024

# key = (stat_date, path, app_id, status_code) -> [调用次数, 总耗时, 最大耗时]
_buffer = defaultdict(lambda: [0, 0, 0])
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
    未匹配到路由（认证被拒 / 404 兜底）或正则路由时，退回真实请求路径。
    """
    match = getattr(request, 'resolver_match', None)
    route = getattr(match, 'route', '') if match else ''
    if route and _ROUTE_SAFE_RE.match(route):
        return normalize_path('/' + route)
    return normalize_path(request.path)


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
    """记录一次 API 调用（进程内聚合，按需批量落库）

    :param path: 请求路径
    :param cost_ms: 本次请求耗时（毫秒）
    :param status_code: 业务状态码（见 business_code）
    :param app_id: 接入项目 APPID；开放接口 / 未认证请求传 NO_APP
    """
    if not path.startswith('/api/') or path.startswith(EXCLUDED_PREFIXES):
        return

    cost = max(0, int(cost_ms))
    key = (timezone.localdate(), path, app_id or NO_APP, int(status_code))

    _ensure_flush_thread()
    with _lock:
        item = _buffer[key]
        item[0] += 1
        item[1] += cost
        if cost > item[2]:
            item[2] = cost
        due = (len(_buffer) >= FLUSH_THRESHOLD
               or (time.monotonic() - _last_flush) >= FLUSH_INTERVAL_SECONDS)
    if due:
        flush()


def flush():
    """把当前缓冲批量写入数据库（空缓冲直接返回）"""
    global _last_flush
    with _lock:
        batch = list(_buffer.items())
        _buffer.clear()
        _last_flush = time.monotonic()
    if not batch:
        return
    try:
        _write_batch(batch)
    except Exception:
        # 统计失败绝不能影响业务请求：记录日志后丢弃本批
        logger.exception('API 调用统计写入失败，本批 %d 个聚合键被丢弃', len(batch))


def _accumulate(stat_date, path, app_id, status_code, count, cost_sum, cost_max, now):
    """按聚合维度累加更新一行，返回受影响行数（0 表示该行还不存在）"""
    return ApiCallStat.objects.filter(
        stat_date=stat_date, path=path, app_id=app_id, status_code=status_code,
    ).update(
        call_count=F('call_count') + count,
        cost_sum_ms=F('cost_sum_ms') + cost_sum,
        cost_max_ms=Greatest(F('cost_max_ms'), Value(cost_max)),
        updated_time=now,
    )


def _write_batch(batch):
    """逐键写库：已存在则累加，不存在则新建"""
    now = timezone.now()
    for (stat_date, path, app_id, status_code), (count, cost_sum, cost_max) in batch:
        args = (stat_date, path, app_id, status_code, count, cost_sum, cost_max, now)
        if _accumulate(*args):
            continue
        try:
            ApiCallStat.objects.create(
                stat_date=stat_date, path=path, app_id=app_id, status_code=status_code,
                service=service_of(path), call_count=count,
                cost_sum_ms=cost_sum, cost_max_ms=cost_max,
            )
        except IntegrityError:
            # 并发下已由其它进程插入同一聚合键：退化为累加更新
            _accumulate(*args)


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
