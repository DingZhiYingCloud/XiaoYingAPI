"""API 调用统计查询（读侧）

与写入侧（API/common/api_stats.py）分离：本模块只做聚合查询，供三处复用——
超管看板（/console/stats/）、文档中心「累计调用次数」、公开统计接口（/api/statistics/）。

口径说明：
- 「成功」= 业务状态码为 StatusCode.SUCCESS（10000）；其余均为失败。
- days=None 表示不限时间（全部历史）；days=N 表示最近 N 天（含今天）。
- 时间按 stat_date（本地日期）过滤，与写入侧一致。
"""
from datetime import timedelta

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from API.common.api_stats import normalize_path
from API.common.status_code import StatusCode
from API.models.Statistics.api_call_stat import NO_APP, ApiCallStat

# 状态码分布展示用的中文名（业务码 -> 文案），其余走 HTTP 语义
_SUCCESS = Q(status_code=StatusCode.SUCCESS)


def _start_date(days):
    """最近 N 天（含今天）的起始日期"""
    return timezone.localdate() - timedelta(days=days - 1)


def _filtered(days):
    qs = ApiCallStat.objects.all()
    if days:
        qs = qs.filter(stat_date__gte=_start_date(days))
    return qs


def _group(field, days, limit=None):
    """按某维度分组汇总，返回带次数/成功/失败/平均耗时/最大耗时的列表"""
    rows = (_filtered(days).values(field)
            .annotate(calls=Sum('call_count'),
                      success=Sum('call_count', filter=_SUCCESS),
                      cost=Sum('cost_sum_ms'),
                      max_ms=Max('cost_max_ms'))
            .order_by('-calls'))
    if limit:
        rows = rows[:limit]
    return [{
        'key': row[field],
        'calls': row['calls'] or 0,
        'success': row['success'] or 0,
        'failed': (row['calls'] or 0) - (row['success'] or 0),
        'avg_ms': round((row['cost'] or 0) / row['calls'], 1) if row['calls'] else 0,
        'max_ms': row['max_ms'] or 0,
    } for row in rows]


# ==================== 超管看板 ====================

def overview(days):
    """概览：总调用、成功、失败、平均耗时、最大耗时、活跃项目数"""
    agg = _filtered(days).aggregate(
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
        'success_rate': round(success * 100 / calls, 2) if calls else 0,
        'avg_ms': round((agg['cost'] or 0) / calls, 1) if calls else 0,
        'max_ms': agg['max_ms'] or 0,
        'active_apps': agg['apps'] or 0,
    }


def daily_trend(days):
    """按天趋势（补齐没有数据的日期，便于前端画连续曲线）

    :param days: 天数（如 7 / 30）
    """
    rows = (_filtered(days).values('stat_date')
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


def service_ranking(days, limit=None):
    """按服务维度汇总（如 /api/email/）"""
    return _group('service', days, limit)


def endpoint_ranking(days, limit=20):
    """按具体端点汇总"""
    return _group('path', days, limit)


def app_ranking(days, limit=20):
    """按接入项目汇总（NO_APP 表示开放接口/未认证请求）"""
    return _group('app_id', days, limit)


def status_code_distribution(days):
    """按状态码汇总（文案由调用方按当前语言翻译，本层不做 i18n）"""
    return _group('status_code', days)


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
