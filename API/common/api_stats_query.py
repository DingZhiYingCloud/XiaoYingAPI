"""API 调用统计查询（读侧）

与写入侧（API/common/api_stats.py）分离：本模块只做聚合查询，供三处复用——
超管看板（/console/stats/）、文档中心「累计调用次数」、公开统计接口（/api/statistics/）。

口径说明：
- 「成功」= 业务状态码为 StatusCode.SUCCESS（10000）；其余均为失败。
- days=None 表示不限时间（全部历史）；days=N 表示最近 N 天（含今天）。
- 时间按 stat_date（本地日期）过滤，与写入侧一致。
- 排行类函数统一返回 calls / success / failed / success_rate / failed_rate /
  avg_ms / max_ms，调用方无需自己算比率。
- 小时维度（hour_analysis / service_hour_matrix）读 ApiCallStatHour，数据只覆盖最近
  HOUR_RETENTION_DAYS 天，超出部分自动截断；按天表是全历史真值，不受影响。
- 筛选（service / app_id）只影响读，不影响写入口径。
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from API.common.api_stats import normalize_path
from API.common.status_code import StatusCode
from API.models.Statistics.api_call_stat import (
    HOUR_RETENTION_DAYS, NO_APP, ApiCallStat, ApiCallStatHour,
)

# 成功判定（业务码 == 10000）
_SUCCESS = Q(status_code=StatusCode.SUCCESS)

# 排行排序键：调用方传语义名，避免在各处写裸字段名
_ORDER_KEYS = {
    'calls': 'calls',
    'failed': 'failed',
    'failed_rate': 'failed_rate',
    'avg_ms': 'avg_ms',
    'max_ms': 'max_ms',
}


def _start_date(days):
    """最近 N 天（含今天）的起始日期"""
    return timezone.localdate() - timedelta(days=days - 1)


def _refine(qs, days=None, service=None, app_id=None, start=None, end=None):
    """给查询集套上时间范围与维度筛选（start/end 优先于 days）"""
    if start is not None:
        qs = qs.filter(stat_date__gte=start)
    elif days:
        qs = qs.filter(stat_date__gte=_start_date(days))
    if end is not None:
        qs = qs.filter(stat_date__lte=end)
    if service:
        qs = qs.filter(service=service)
    if app_id:
        qs = qs.filter(app_id=app_id)
    return qs


def _day_qs(days=None, service=None, app_id=None, start=None, end=None):
    """按天表的筛选查询集（全历史真值）"""
    return _refine(ApiCallStat.objects.all(), days, service, app_id, start, end)


def _hour_qs(days, service=None, app_id=None):
    """小时表的筛选查询集：范围截断到保留期内（更早的小时行已被 prune 删除）"""
    end = timezone.localdate()
    start = max(end - timedelta(days=days - 1),
                end - timedelta(days=HOUR_RETENTION_DAYS - 1))
    return _refine(ApiCallStatHour.objects.all(), None, service, app_id, start, end)


def _rate(part, total):
    """百分比（保留 2 位），总数为 0 时返回 0"""
    return round(part * 100 / total, 2) if total else 0.0


def _shape(field, row):
    """把一条分组聚合结果整形为统一的排行行"""
    calls = row['calls'] or 0
    success = row['success'] or 0
    failed = calls - success
    return {
        'key': row[field],
        'calls': calls,
        'success': success,
        'failed': failed,
        'success_rate': _rate(success, calls),
        'failed_rate': _rate(failed, calls),
        'avg_ms': round((row['cost'] or 0) / calls, 1) if calls else 0,
        'max_ms': row['max_ms'] or 0,
    }


def _group(field, days=None, limit=None, service=None, app_id=None,
           order='calls', min_calls=0, start=None, end=None):
    """按某维度分组汇总并排序

    :param order: 排序依据（calls / failed / failed_rate / avg_ms / max_ms），降序
    :param min_calls: 只保留调用量不低于该值的分组（用于失败率榜剔除小样本噪声）
    """
    rows = (_day_qs(days, service, app_id, start, end).values(field)
            .annotate(calls=Sum('call_count'),
                      success=Sum('call_count', filter=_SUCCESS),
                      cost=Sum('cost_sum_ms'),
                      max_ms=Max('cost_max_ms')))
    items = [_shape(field, row) for row in rows]
    if min_calls:
        items = [item for item in items if item['calls'] >= min_calls]
    items.sort(key=lambda item: item[_ORDER_KEYS[order]], reverse=True)
    return items[:limit] if limit else items


# ==================== 超管看板 ====================

def _overview_of(qs):
    """单个时间窗口的概览指标"""
    agg = qs.aggregate(
        calls=Sum('call_count'),
        success=Sum('call_count', filter=_SUCCESS),
        cost=Sum('cost_sum_ms'),
        max_ms=Max('cost_max_ms'),
        apps=Count('app_id', distinct=True, filter=~Q(app_id=NO_APP)),
    )
    calls = agg['calls'] or 0
    success = agg['success'] or 0
    return {
        'calls': calls,
        'success': success,
        'failed': calls - success,
        'success_rate': _rate(success, calls),
        'failed_rate': _rate(calls - success, calls),
        'avg_ms': round((agg['cost'] or 0) / calls, 1) if calls else 0,
        'max_ms': agg['max_ms'] or 0,
        'active_apps': agg['apps'] or 0,
    }


def overview(days, service=None, app_id=None):
    """概览：总调用、成功、失败、成功率、平均耗时、最大耗时、活跃项目数"""
    return _overview_of(_day_qs(days, service, app_id))


def overview_compare(days, service=None, app_id=None):
    """概览 + 环比：与「紧邻的等长上一周期」对比

    返回当前窗口的概览，并附加：
        prev            - 上一周期概览
        calls_delta     - 调用量环比（百分比，上一周期为 0 时记 None）
        success_rate_delta - 成功率环比（百分点）
    """
    start = _start_date(days)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    current = _overview_of(_day_qs(start=start, end=timezone.localdate(),
                                  service=service, app_id=app_id))
    prev = _overview_of(_day_qs(start=prev_start, end=prev_end,
                                service=service, app_id=app_id))
    current['prev'] = prev
    current['calls_delta'] = (round((current['calls'] - prev['calls']) * 100 / prev['calls'], 1)
                              if prev['calls'] else None)
    current['success_rate_delta'] = round(current['success_rate'] - prev['success_rate'], 2)
    return current


def daily_trend(days, service=None, app_id=None):
    """按天趋势（补齐没有数据的日期，便于前端画连续曲线）"""
    rows = (_day_qs(days, service, app_id).values('stat_date')
            .annotate(calls=Sum('call_count'),
                      success=Sum('call_count', filter=_SUCCESS)))
    by_date = {row['stat_date']: row for row in rows}
    today = timezone.localdate()
    trend = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        row = by_date.get(day)
        calls = (row['calls'] or 0) if row else 0
        success = (row['success'] or 0) if row else 0
        trend.append({'date': day.isoformat(), 'calls': calls,
                      'success': success, 'failed': calls - success})
    return trend


def service_ranking(days, limit=None, service=None, app_id=None, order='calls', min_calls=0):
    """按服务维度汇总（如 /api/email/）

    :param service: 只看某个服务（用于看板筛选后服务表同步收敛）
    """
    return _group('service', days, limit, service=service, app_id=app_id,
                  order=order, min_calls=min_calls)


def endpoint_ranking(days, limit=20, service=None, app_id=None,
                     order='calls', min_calls=0):
    """按具体端点汇总"""
    return _group('path', days, limit, service=service, app_id=app_id,
                  order=order, min_calls=min_calls)


def app_ranking(days, limit=20, service=None, with_top_service=False):
    """按接入项目汇总（NO_APP 表示开放接口/未认证请求）

    :param with_top_service: 是否附带每个项目调用量最高的服务（多一次分组查询）
    """
    items = _group('app_id', days, limit, service=service)
    if not with_top_service or not items:
        return items
    keys = [item['key'] for item in items]
    rows = (_day_qs(days, service=service).filter(app_id__in=keys)
            .values('app_id', 'service').annotate(calls=Sum('call_count')))
    best = {}
    for row in rows:
        calls = row['calls'] or 0
        if row['app_id'] not in best or calls > best[row['app_id']][1]:
            best[row['app_id']] = (row['service'], calls)
    for item in items:
        top = best.get(item['key'])
        item['top_service'] = top[0] if top else ''
        item['top_service_share'] = round(top[1] * 100 / item['calls'], 1) if top and item['calls'] else 0
    return items


def status_code_distribution(days, service=None, app_id=None):
    """按状态码汇总（文案由调用方按当前语言翻译，本层不做 i18n）"""
    return _group('status_code', days, service=service, app_id=app_id)


def service_keys():
    """出现过调用记录的服务前缀（去重，供筛选下拉；与时间范围无关，选项稳定）

    注意：模型 Meta.ordering 含 stat_date，若不显式 order_by 会被 DISTINCT 连带选入，
    导致同一服务按天重复出现——这里显式按服务字段排序后再去重。
    """
    return list(ApiCallStat.objects.values_list('service', flat=True)
                .order_by('service').distinct())


def app_keys():
    """出现过调用记录的接入项目 APPID（去重，供筛选下拉）"""
    return list(ApiCallStat.objects.values_list('app_id', flat=True)
                .order_by('app_id').distinct())


def peak_days(days, service=None, app_id=None, limit=5):
    """调用量最高的几天（按天表，可用全历史范围）"""
    return _group('stat_date', days, limit, service=service, app_id=app_id)


def hour_analysis(days, service=None, app_id=None):
    """小时维度分析：时段分布 + 星期×小时热力图 + 峰值（一次查询，Python 侧派生）

    只覆盖小时表保留期（最近 HOUR_RETENTION_DAYS 天）；返回：
        profile      - 24 小时分布（calls/success/failed/success_rate/avg_ms/max_ms）
        heatmap      - 7×24 矩阵，行=星期（0=周一），列=小时
        heatmap_max  - 热力图最大值（供前端配色）
        top_slots    - 调用量最高的 (日期, 小时) 时点，最多 5 条
        peak         - 最高时点（top_slots[0]，无数据为 None）
        hour_days    - 实际覆盖天数（days 与保留期取小）
    """
    rows = (_hour_qs(days, service, app_id).values('stat_date', 'stat_hour')
            .annotate(calls=Sum('call_count'),
                      success=Sum('call_count', filter=_SUCCESS),
                      cost=Sum('cost_sum_ms'),
                      max_ms=Max('cost_max_ms')))
    profile = [{'hour': hour, 'calls': 0, 'success': 0, 'failed': 0,
                'success_rate': 0.0, 'avg_ms': 0, 'max_ms': 0} for hour in range(24)]
    heatmap = [[0] * 24 for _ in range(7)]
    slots = []
    for row in rows:
        calls = row['calls'] or 0
        success = row['success'] or 0
        hour = row['stat_hour']
        slot = profile[hour]
        slot['calls'] += calls
        slot['success'] += success
        slot['max_ms'] = max(slot['max_ms'], row['max_ms'] or 0)
        slot['avg_ms'] += row['cost'] or 0          # 先累计总耗时，最后算均值
        heatmap[row['stat_date'].weekday()][hour] += calls
        slots.append({'date': row['stat_date'], 'hour': hour, 'calls': calls,
                      'failed': calls - success})
    for slot in profile:
        slot['failed'] = slot['calls'] - slot['success']
        slot['success_rate'] = _rate(slot['success'], slot['calls'])
        slot['avg_ms'] = round(slot['avg_ms'] / slot['calls'], 1) if slot['calls'] else 0
    slots.sort(key=lambda item: item['calls'], reverse=True)
    return {
        'profile': profile,
        'heatmap': heatmap,
        'heatmap_max': max((max(row) for row in heatmap), default=0),
        'top_slots': slots[:5],
        'peak': slots[0] if slots else None,
        'hour_days': min(days, HOUR_RETENTION_DAYS),
    }


def service_hour_matrix(days, app_id=None, top=8):
    """服务 × 小时调用量矩阵，回答「什么时段哪个服务被调用最多」

    取调用量前 top 个服务，每个含 24 小时分布与总量（服务口径见 service_of）。
    """
    rows = (_hour_qs(days, app_id=app_id).values('service', 'stat_hour')
            .annotate(calls=Sum('call_count')))
    by_service = defaultdict(lambda: [0] * 24)
    for row in rows:
        by_service[row['service']][row['stat_hour']] += row['calls'] or 0
    ordered = sorted(by_service.items(), key=lambda item: -sum(item[1]))
    return [{'service': service, 'hours': hours, 'total': sum(hours)}
            for service, hours in ordered[:top]]


# ==================== 文档中心 ====================

def endpoint_call_counts(paths):
    """一批端点的累计调用次数（全部历史）：{声明路径: 次数}

    写入侧会把路径参数归一为 <param>（见 api_stats.normalize_path），这里同样归一后比较；
    同时兼容 URL 配置里「带 / 不带末尾斜杠」两种路由写法。
    """
    wanted = {}
    for path in paths:
        if path:
            wanted.setdefault(normalize_path(path), []).append(path)
    if not wanted:
        return {}

    variants = set()
    for norm in wanted:
        variants.update((norm, norm.rstrip('/') + '/'))
    rows = (ApiCallStat.objects.filter(path__in=list(variants))
            .values('path').annotate(total=Sum('call_count')))
    by_path = {row['path']: row['total'] or 0 for row in rows}

    result = {}
    for norm, declared_list in wanted.items():
        # 用集合去重：norm 本身以 / 结尾时两个候选会重合，避免重复累加
        candidates = {norm, norm.rstrip('/') + '/'}
        total = sum(by_path.get(c, 0) for c in candidates)
        for declared in declared_list:
            result[declared] = total
    return result


# ==================== 公开口径（仅调用次数，不含项目/耗时/失败率） ====================

def public_path_calls(path):
    """某接口的公开调用量：累计 + 今日

    路径参数会先归一（与写入侧一致），因此 /musics/<uuid> 这类带参接口也能查到。
    """
    norm = normalize_path(path)
    candidates = sorted({norm, norm.rstrip('/') + '/'})
    base = ApiCallStat.objects.filter(path__in=candidates)
    total = base.aggregate(t=Sum('call_count'))['t'] or 0
    today = (base.filter(stat_date=timezone.localdate())
             .aggregate(t=Sum('call_count'))['t'] or 0)
    return {'path': path, 'total_calls': total, 'today_calls': today}


def public_service_calls():
    """各服务的公开调用量（累计），按调用量降序"""
    rows = (ApiCallStat.objects.values('service')
            .annotate(total=Sum('call_count')).order_by('-total'))
    today = timezone.localdate()
    today_rows = (ApiCallStat.objects.filter(stat_date=today).values('service')
                  .annotate(total=Sum('call_count')))
    today_map = {row['service']: row['total'] or 0 for row in today_rows}
    return [{'service': row['service'], 'total_calls': row['total'] or 0,
             'today_calls': today_map.get(row['service'], 0)} for row in rows]
