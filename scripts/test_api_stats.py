"""API 调用统计（两级预聚合：按天全量 + 按小时近 90 天）回归测试

覆盖范围：
    第 1 轮 写入口径一致性：同一窗口内「按小时汇总」== 「按天合计」
    第 2 轮 查询层：概览、环比、服务/接口/项目排行（含成功率与失败率）、状态码、峰值日期
    第 3 轮 小时维度：时段分布 24 项、7×24 热力图、峰值时点、服务×时段矩阵、保留期截断
    第 4 轮 筛选：service / app_id 只影响读，不影响写入口径
    第 5 轮 失败率页内标记阈值（样本不足不判定；5% 黄 / 20% 红）
    第 6 轮 清理命令 prune_api_call_hour：只删过期小时行，按天表不动；--dry-run 不删除
    第 7 轮 页面渲染：总览 / 服务详情 / 项目详情（超管可访问、含测试数据）+ 三语渲染 + 匿名跳登录
    第 8 轮 公开统计接口不回归（/api/statistics/）

隔离策略：全部测试数据用专属 APPID（TEST_APP）与专属路径前缀（/api/_statstest*），
测试结束统一删除，不触碰真实统计数据；不使用需要真实流量的写入路径。

运行方式：
    .venv\\Scripts\\python.exe scripts\\test_api_stats.py
"""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Q, Sum
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from API.common import StatusCode
from API.common import api_stats_query as query
from API.common.api_stats import service_of
from API.models.Security.setting import SecuritySetting
from API.models.Statistics.api_call_stat import (
    HOUR_RETENTION_DAYS, ApiCallStat, ApiCallStatHour,
)
from API.website import console

# 测试数据标识（app_id 上限 32 字符）
TEST_APP = 'teststats0001'
PATH_A = '/api/_statstest/alpha'
PATH_B = '/api/_statstest2/beta'
SVC_A = '/api/_statstest/'
SVC_B = '/api/_statstest2/'

_PASSED = 0
_FAILED = 0
_FAILURES = []


def check(name, condition, detail=''):
    """断言并输出结果"""
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f'  [PASS] {name}')
    else:
        _FAILED += 1
        _FAILURES.append(name)
        print(f'  [FAIL] {name} {detail}')


def section(title):
    print(f'\n{"=" * 70}\n{title}\n{"=" * 70}')


# ───────────────────────── 数据准备 / 清理 ─────────────────────────

def cleanup():
    """删除全部测试数据（按专属路径前缀与 APPID）"""
    cond = Q(app_id=TEST_APP) | Q(path__startswith='/api/_statstest')
    ApiCallStat.objects.filter(cond).delete()
    ApiCallStatHour.objects.filter(cond).delete()


def seed(stat_date, path, code, count, splits=None):
    """写入一条按天统计，并按 splits=[(小时, 次数), ...] 镜像到小时表

    按天表对「日期 + 路径 + 项目 + 状态码」唯一，因此同一天同接口同状态码只能有一条；
    小时分布通过 splits 拆分表达（不传表示只有按天数据，用于验证小时表保留期截断）。
    """
    base = dict(stat_date=stat_date, service=service_of(path), path=path,
                app_id=TEST_APP, status_code=code,
                call_count=count, cost_sum_ms=count * 10, cost_max_ms=100)
    ApiCallStat.objects.create(**base)
    for hour, hour_count in (splits or []):
        ApiCallStatHour.objects.create(
            stat_hour=hour, stat_date=stat_date, service=base['service'], path=path,
            app_id=TEST_APP, status_code=code, call_count=hour_count,
            cost_sum_ms=hour_count * 10, cost_max_ms=100)


def build_dataset():
    """构造可预期的测试数据

    今天(day 0)      ：路径A 成功 10（9 时 4 / 10 时 6）、路径A 认证失败 5（10 时）、路径B 成功 7（3 时）
    昨天(day 1)      ：路径A 成功 20（20 时）
    8 天前(day 8)    ：路径A 成功 40（20 时）—— 落在 days=7 的「上一周期」内
    100 天前(day 100)：路径A 成功 99（只有按天数据，用于验证小时表保留期截断）
    """
    today = timezone.localdate()
    day1 = today - timedelta(days=1)
    day8 = today - timedelta(days=8)
    day100 = today - timedelta(days=100)

    ok = StatusCode.SUCCESS
    auth_failed = StatusCode.AUTH_FAILED

    seed(today, PATH_A, ok, 10, splits=[(9, 4), (10, 6)])
    seed(today, PATH_A, auth_failed, 5, splits=[(10, 5)])
    seed(today, PATH_B, ok, 7, splits=[(3, 7)])
    seed(day1, PATH_A, ok, 20, splits=[(20, 20)])
    seed(day8, PATH_A, ok, 40, splits=[(20, 40)])
    seed(day100, PATH_A, ok, 99)


# ───────────────────────── 第 1 轮：口径一致性 ─────────────────────────

def round1_consistency():
    section('第 1 轮 写入口径一致性（按小时汇总 == 按天合计）')
    start = timezone.localdate() - timedelta(days=29)
    day_total = (ApiCallStat.objects.filter(app_id=TEST_APP, stat_date__gte=start)
                 .aggregate(total=Sum('call_count'))['total'] or 0)
    hour_total = (ApiCallStatHour.objects.filter(app_id=TEST_APP, stat_date__gte=start)
                  .aggregate(total=Sum('call_count'))['total'] or 0)
    check('样本非空（避免空集导致的假通过）', day_total > 0, f'day_total={day_total}')
    check('保留期内 按天合计 == 按小时汇总', day_total == hour_total,
          f'day={day_total} hour={hour_total}')
    check('查询层同样一致：overview(30) == 时段分布合计',
          query.overview(30, app_id=TEST_APP)['calls']
          == sum(p['calls'] for p in query.hour_analysis(30, app_id=TEST_APP)['profile']))


# ───────────────────────── 第 2 轮：查询层 ─────────────────────────

def round2_query():
    section('第 2 轮 查询层（概览 / 环比 / 排行 / 状态码 / 峰值日期）')
    ov = query.overview(7, app_id=TEST_APP)
    check('概览调用量 = 42', ov['calls'] == 42, f"calls={ov['calls']}")
    check('概览成功 = 37 / 失败 = 5', ov['success'] == 37 and ov['failed'] == 5,
          f"success={ov['success']} failed={ov['failed']}")
    check('概览成功率 = 88.1%', ov['success_rate'] == 88.1, f"rate={ov['success_rate']}")
    check('概览平均耗时 = 10.0ms', ov['avg_ms'] == 10.0, f"avg={ov['avg_ms']}")
    check('活跃项目数 = 1', ov['active_apps'] == 1, f"apps={ov['active_apps']}")

    cmp_ov = query.overview_compare(7, app_id=TEST_APP)
    check('环比：上一周期调用量 = 40', cmp_ov['prev']['calls'] == 40,
          f"prev={cmp_ov['prev']['calls']}")
    check('环比：调用量变化 +5.0%', cmp_ov['calls_delta'] == 5.0,
          f"delta={cmp_ov['calls_delta']}")

    trend = query.daily_trend(7, app_id=TEST_APP)
    check('趋势补齐 7 天', len(trend) == 7, f'len={len(trend)}')
    check('趋势最后一天 = 今日 22 次（成功 17 / 失败 5）',
          trend[-1]['calls'] == 22 and trend[-1]['success'] == 17 and trend[-1]['failed'] == 5,
          f"last={trend[-1]}")

    services = query.service_ranking(7, app_id=TEST_APP)
    check('服务排行：2 个服务，A(35) 在前', len(services) == 2
          and services[0]['key'] == SVC_A and services[0]['calls'] == 35,
          f'services={services}')
    check('服务排行带成功率/失败率（A 85.71% / B 100%）',
          services[0]['success_rate'] == 85.71 and services[0]['failed_rate'] == 14.29
          and services[1]['success_rate'] == 100.0 and services[1]['failed_rate'] == 0.0,
          f'services={services}')

    endpoints = query.endpoint_ranking(7, app_id=TEST_APP)
    check('接口排行：A(35) > B(7)',
          [r['key'] for r in endpoints] == [PATH_A, PATH_B]
          and endpoints[0]['calls'] == 35 and endpoints[0]['failed'] == 5,
          f'endpoints={endpoints}')

    failed_rank = query.endpoint_ranking(7, app_id=TEST_APP, order='failed')
    check('失败次数榜按失败量排序（A 5 次在前）', failed_rank[0]['key'] == PATH_A
          and failed_rank[0]['failed'] == 5, f'failed_rank={failed_rank}')

    tiny = query.endpoint_ranking(7, app_id=TEST_APP, min_calls=20)
    check('失败率榜剔除小样本（min_calls=20 只剩 A）',
          [r['key'] for r in tiny] == [PATH_A], f'tiny={tiny}')

    codes = query.status_code_distribution(7, app_id=TEST_APP)
    by_code = {row['key']: row['calls'] for row in codes}
    check('状态码分布：10000=37 / 20011=5',
          by_code.get(StatusCode.SUCCESS) == 37 and by_code.get(StatusCode.AUTH_FAILED) == 5,
          f'codes={by_code}')

    peaks = query.peak_days(30, app_id=TEST_APP, limit=5)
    check('峰值日期：40 次那天排第一', peaks[0]['calls'] == 40,
          f'peaks={peaks}')


# ───────────────────────── 第 3 轮：小时维度 ─────────────────────────

def round3_hourly():
    section('第 3 轮 小时维度（时段分布 / 热力图 / 峰值 / 矩阵 / 保留期）')
    hours = query.hour_analysis(30, app_id=TEST_APP)
    check('时段分布固定 24 项', len(hours['profile']) == 24, f"len={len(hours['profile'])}")
    check('时段分布合计 = 82', sum(p['calls'] for p in hours['profile']) == 82,
          f"sum={sum(p['calls'] for p in hours['profile'])}")
    check('20 时合计 60 次（昨天 20 + 8 天前 40）', hours['profile'][20]['calls'] == 60,
          f"h20={hours['profile'][20]}")
    check('热力图 7 行 × 24 列',
          len(hours['heatmap']) == 7 and all(len(row) == 24 for row in hours['heatmap']),
          f"rows={len(hours['heatmap'])}")
    check('峰值时点 = 8 天前 20 时（40 次）',
          hours['peak'] is not None and hours['peak']['calls'] == 40
          and hours['peak']['hour'] == 20, f"peak={hours['peak']}")
    check('峰值时点 Top5 降序', len(hours['top_slots']) == 5
          and [s['calls'] for s in hours['top_slots']] == sorted(
              [s['calls'] for s in hours['top_slots']], reverse=True),
          f"slots={hours['top_slots']}")

    matrix = query.service_hour_matrix(30, app_id=TEST_APP, top=6)
    check('服务×时段矩阵：2 个服务，A(75) 在前',
          len(matrix) == 2 and matrix[0]['total'] == 75 and matrix[1]['total'] == 7
          and matrix[0]['hours'][20] == 60,
          f'matrix={matrix}')

    long_range = query.hour_analysis(200, app_id=TEST_APP)
    check(f'小时窗口被截断到保留期 {HOUR_RETENTION_DAYS} 天',
          long_range['hour_days'] == HOUR_RETENTION_DAYS, f"hour_days={long_range['hour_days']}")
    check('按天表保留全历史（200 天前那条仍在）',
          query.overview(200, app_id=TEST_APP)['calls'] == 181,
          f"calls={query.overview(200, app_id=TEST_APP)['calls']}")


# ───────────────────────── 第 4 轮：筛选 ─────────────────────────

def round4_filters():
    section('第 4 轮 筛选（service / app_id 只影响读）')
    check('服务筛选 A：接口只剩 A',
          [r['key'] for r in query.endpoint_ranking(7, service=SVC_A)] == [PATH_A])
    check('服务筛选 B：调用量 7',
          query.overview(7, service=SVC_B)['calls'] == 7)
    check('项目筛选 + 服务筛选叠加：A 服务下该项目 35 次',
          query.overview(7, service=SVC_A, app_id=TEST_APP)['calls'] == 35)
    check('不存在的筛选值返回空（不报错）',
          query.overview(7, app_id='not-exists-app')['calls'] == 0)
    keys = query.service_keys()
    check('服务筛选选项含测试数据且无重复',
          SVC_A in keys and len(keys) == len(set(keys)), f'len={len(keys)}')
    app_key_list = query.app_keys()
    check('项目筛选选项含测试数据且无重复',
          TEST_APP in app_key_list and len(app_key_list) == len(set(app_key_list)),
          f'len={len(app_key_list)}')
    check('服务筛选后服务排行收敛为该服务一行',
          [r['key'] for r in query.service_ranking(7, service=SVC_A, app_id=TEST_APP)]
          == [SVC_A])


# ───────────────────────── 第 5 轮：失败率标记阈值 ─────────────────────────

def round5_rate_level():
    section('第 5 轮 失败率页内标记阈值（样本不足不判定）')
    level = console._rate_level
    check('样本 10 次即使 50% 也不判定', level({'calls': 10, 'failed_rate': 50}) == 'none')
    check('样本 20 次 4.9% → 正常', level({'calls': 20, 'failed_rate': 4.9}) == 'ok')
    check('样本 20 次 5% → 标黄', level({'calls': 20, 'failed_rate': 5}) == 'warn')
    check('样本 20 次 19.99% → 标黄', level({'calls': 20, 'failed_rate': 19.99}) == 'warn')
    check('样本 20 次 20% → 标红', level({'calls': 20, 'failed_rate': 20}) == 'danger')
    check('阈值常量与约定一致（5% 黄 / 20% 红 / 样本 20）',
          (console.STATS_RATE_WARN, console.STATS_RATE_DANGER, console.STATS_MIN_RATE_CALLS)
          == (5, 20, 20))
    rows = console._mark_rates([{'calls': 30, 'failed_rate': 30}, {'calls': 3, 'failed_rate': 30}])
    check('_mark_rates 逐行写入 rate_level',
          [r['rate_level'] for r in rows] == ['danger', 'none'], f'rows={rows}')


# ───────────────────────── 第 6 轮：清理命令 ─────────────────────────

def round6_prune():
    section('第 6 轮 清理命令 prune_api_call_hour')
    today = timezone.localdate()
    expired = today - timedelta(days=HOUR_RETENTION_DAYS + 5)
    ApiCallStatHour.objects.create(
        stat_date=expired, stat_hour=1, service=SVC_A, path=PATH_A, app_id=TEST_APP,
        status_code=StatusCode.SUCCESS, call_count=3, cost_sum_ms=30, cost_max_ms=10)

    before_day_rows = ApiCallStat.objects.filter(app_id=TEST_APP).count()
    call_command('prune_api_call_hour', '--dry-run')
    check('--dry-run 不删除任何行',
          ApiCallStatHour.objects.filter(stat_date=expired, app_id=TEST_APP).exists())

    call_command('prune_api_call_hour')
    check('过期小时行被删除',
          not ApiCallStatHour.objects.filter(stat_date=expired, app_id=TEST_APP).exists())
    check('保留期内小时行不受影响',
          ApiCallStatHour.objects.filter(stat_date=today, app_id=TEST_APP).exists())
    check('按天表完全不受影响（总行数与 100 天前的行均不变）',
          ApiCallStat.objects.filter(app_id=TEST_APP).count() == before_day_rows
          and ApiCallStat.objects.filter(
              app_id=TEST_APP, stat_date=today - timedelta(days=100)).exists(),
          f'before={before_day_rows}')

    today_hours = ApiCallStatHour.objects.filter(app_id=TEST_APP).count()
    call_command('prune_api_call_hour', days=HOUR_RETENTION_DAYS)
    check('重复执行幂等（无新删除）',
          ApiCallStatHour.objects.filter(app_id=TEST_APP).count() == today_hours)


# ───────────────────────── 第 7 轮：页面渲染 ─────────────────────────

def _superadmin():
    """返回 (已登录超管的测试客户端, 超管对象, 是否为本测试临时创建)"""
    user_model = get_user_model()
    admin = user_model.objects.filter(is_superuser=True, is_active=True).first()
    created = False
    if admin is None:
        admin = user_model.objects.create_superuser(
            username='stats_test_admin', email='stats_test_admin@example.com',
            password='stats-test-pass-123456')
        created = True
    client = Client()
    client.force_login(admin)
    return client, admin, created


def round7_pages():
    section('第 7 轮 页面渲染（总览 / 服务详情 / 项目详情 + 三语 + 匿名）')
    client, admin, created_admin = _superadmin()
    try:
        resp = client.get('/console/stats/')
        html = resp.content.decode()
        check('总览页 200', resp.status_code == 200, f'status={resp.status_code}')
        check('总览页含新增分析模块',
              all(text in html for text in ('日内高峰时段', '时段分布（24 小时）',
                                            '星期 × 小时热力图', '服务 × 时段矩阵',
                                            '失败最多的接口 Top 10', '调用量最高的日期')))
        check('总览页展示测试数据（APPID 出现在项目表）', TEST_APP in html)
        check('总览页带环比与失败率标记阈值说明',
              '环比上一周期' in html and '标黄' in html)
        check('无跨行 {# #} 注释泄漏', '{#' not in html)

        resp = client.get('/console/stats/', {'days': 30})
        check('?days=30 正常', resp.status_code == 200
              and '?days=30' in resp.content.decode())

        resp = client.get('/console/stats/', {'days': 30, 'service': SVC_A, 'app_id': TEST_APP})
        body = resp.content.decode()
        check('总览页筛选参数生效（渲染 200 且筛选项被选中）',
              resp.status_code == 200 and f'value="{SVC_A}" selected' in body,
              f'status={resp.status_code}')
        check('筛选后出现「重置」按钮', '重置' in body)
        service_link = f'href="{reverse("website:console_stats_service", args=[SVC_A.strip("/")])}" class="link link-hover text-sm"'
        check('服务筛选后服务排行表只剩该服务一行', body.count(service_link) == 1,
              f'count={body.count(service_link)}')

        resp = client.get('/console/stats/', {'days': 999})
        check('非法 days 回退默认范围', resp.status_code == 200)

        url = reverse('website:console_stats_service', args=[SVC_A.strip('/')])
        resp = client.get(url)
        check('服务详情页 200 且含服务名与接口',
              resp.status_code == 200 and PATH_A in resp.content.decode(),
              f'url={url} status={resp.status_code}')

        url = reverse('website:console_stats_app', args=[TEST_APP])
        resp = client.get(url)
        check('项目详情页 200 且含 APPID 与接口',
              resp.status_code == 200 and TEST_APP in resp.content.decode()
              and PATH_A in resp.content.decode(), f'url={url} status={resp.status_code}')

        # 多语言：en / zh-hant 下不得回退简体中文（探针取自新增模块标题与状态码说明文案）
        for lang, page, probes in (
                ('en', '/console/stats/', ('日内高峰时段', '认证失败', '失败率标记')),
                ('zh-hant', '/console/stats/', ('日内高峰时段', '失败率标记')),
                ('en', '/console/stats/service/api/_statstest/', ('日内高峰时段',)),
                ('zh-hant', '/console/stats/app/teststats0001/', ('日内高峰时段',))):
            lang_client = Client()
            lang_client.force_login(admin)
            lang_client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
            resp = lang_client.get(page)
            body = resp.content.decode()
            leaked = [probe for probe in probes if probe in body]
            check(f'{lang} 渲染 {page} 成功且无中文回退',
                  resp.status_code == 200 and not leaked,
                  f'status={resp.status_code} leaked={leaked}')

        # 英文页另做一处正向断言：状态码说明列确实译成了英文（数据里有 20011 认证失败）
        en_client = Client()
        en_client.force_login(admin)
        en_client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'en'
        en_body = en_client.get('/console/stats/').content.decode()
        check('英文页状态码说明已翻译（Authentication failed）',
              'Authentication failed' in en_body and '认证失败' not in en_body)

        # 匿名访问控制台：默认「后台入口隐身」开启 → 一律 404（与不存在的地址无差别，
        # 避免后台入口被路径探测发现）；关掉隐身才 302 跳登录。断言须按当前开关取值，
        # 写死 302 会在默认配置下恒失败（与 test_console_audit.py 同口径）。
        anon = Client()
        expected = 404 if SecuritySetting.get_solo().hide_console else 302
        resp = anon.get('/console/stats/')
        check('匿名访问总览页被拦（隐身 404 / 否则 302）',
              resp.status_code == expected
              and (expected == 404 or '/login/' in resp['Location']),
              f'status={resp.status_code}')
        resp = anon.get(reverse('website:console_stats_service', args=['api/_statstest']))
        check('匿名访问服务详情页被拦', resp.status_code == expected
              and (expected == 404 or '/login/' in resp['Location']),
              f'status={resp.status_code}')
        resp = anon.get(reverse('website:console_stats_app', args=[TEST_APP]))
        check('匿名访问项目详情页被拦', resp.status_code == expected
              and (expected == 404 or '/login/' in resp['Location']),
              f'status={resp.status_code}')
    finally:
        if created_admin:
            created_admin.delete()


# ───────────────────────── 第 8 轮：公开接口不回归 ─────────────────────────

def round8_public_api():
    section('第 8 轮 公开统计接口不回归（/api/statistics/）')
    anon = Client()
    payload = anon.get('/api/statistics/services').json()
    check('/api/statistics/services 免签名可访问且返回 10000',
          payload.get('code') == StatusCode.SUCCESS and isinstance(
              payload.get('data', {}).get('services'), list), f'payload={payload}')
    listed = [row['service'] for row in payload['data']['services']]
    check('公开服务排行含测试服务（口径与看板一致）', SVC_A in listed, f'listed={listed}')

    payload = anon.get('/api/statistics/api_calls').json()
    check('缺少 path 参数返回 20001', payload.get('code') == StatusCode.PARAM_MISSING,
          f'payload={payload}')
    payload = anon.get('/api/statistics/api_calls', {'path': '/api/_statstest/alpha'}).json()
    check('未登记路径返回 20003', payload.get('code') == StatusCode.PARAM_VALUE_INVALID,
          f'payload={payload}')


# ───────────────────────── 第 9 轮：统计口径标签 ─────────────────────────

def round9_labels():
    section('第 9 轮 统计口径标签（已删除项目 / 未匹配路径归并）')
    from types import SimpleNamespace

    from django.utils import timezone

    from API.common.api_stats import (UNMATCHED_PATH, canonical_path, purge_app,
                                      request_path, service_of)
    from API.models.Statistics.api_call_stat import (NO_APP, ApiCallStat,
                                                    ApiCallStatHour)
    from API.website import console

    class _Req:
        """最小请求替身：只需 path（无 resolver_match）与可选的路由模板"""

        def __init__(self, path, route=None):
            self.path = path
            if route:
                self.resolver_match = SimpleNamespace(route=route)

    check('扫描器探测路径被归并（/api/phpinfo.php/）',
          request_path(_Req('/api/phpinfo.php/')) == UNMATCHED_PATH,
          request_path(_Req('/api/phpinfo.php/')))
    check('扫描器探测路径被归并（/api/.git-credentials/）',
          request_path(_Req('/api/.git-credentials/')) == UNMATCHED_PATH)
    check('真实接口被拒时仍按真实路径记录（便于排查）',
          request_path(_Req('/api/movies/movie_555/list')) == '/api/movies/movie_555/list')
    check('未签名但真实存在的带参接口用路由模板（不按 ID 拆行）',
          request_path(_Req('/api/music/xiaoying/musics/12345678-1234-1234-1234-123456789012'))
          == '/api/music/xiaoying/musics/<param>',
          request_path(_Req('/api/music/xiaoying/musics/12345678-1234-1234-1234-123456789012')))
    check('命中路由模板时用模板（路径参数归一）',
          request_path(_Req('/api/movies/movie_555/detail/123',
                             route='api/movies/movie_555/detail/<str:vod_id>'))
          == '/api/movies/movie_555/detail/<param>')
    check('未匹配路径归属独立服务前缀',
          service_of(UNMATCHED_PATH) == '/api/_unmatched_/',
          service_of(UNMATCHED_PATH))

    missing = 'app_deleted_project_for_test'
    check('已删除项目：表格只显示类别（app_id 另有副行）',
          console._app_label(missing, {}) == '已删除项目',
          console._app_label(missing, {}))
    check('已删除项目：筛选下拉补 app_id 以免同名重复',
          console._app_label(missing, {}, for_option=True) == f'已删除项目 · {missing}')
    check('未删除项目显示项目名',
          console._app_label('app_ok', {'app_ok': '某项目'}) == '某项目')
    check('未认证请求仍显示「开放接口 / 未认证」',
          console._app_label(NO_APP, {}) == '开放接口 / 未认证')

    # canonical_path：把历史路径折算到当前口径（清理历史数据与实时记录共用同一函数）
    check('canonical_path：已是模板的原样保留',
          canonical_path('/api/music/xiaoying/musics/<param>')
          == '/api/music/xiaoying/musics/<param>')
    check('canonical_path：历史原始路径折算为路由模板',
          canonical_path('/api/music/xiaoying/musics/12345678-1234-1234-1234-123456789012')
          == '/api/music/xiaoying/musics/<param>')
    check('canonical_path：不存在的路径折算为未匹配',
          canonical_path('/api/phpinfo.php') == UNMATCHED_PATH)
    check('canonical_path 幂等（对结果再折算不变）',
          canonical_path(canonical_path('/api/phpinfo.php')) == UNMATCHED_PATH
          and canonical_path(canonical_path('/api/movies/movie_555/list'))
          == '/api/movies/movie_555/list')

    # purge_app：删除接入项目时清掉它在两张统计表里的行
    doomed = 'app_purge_test_0001'
    today = timezone.localdate()
    ApiCallStat.objects.create(stat_date=today, service=service_of(PATH_A), path=PATH_A,
                               app_id=doomed, status_code=10000, call_count=1,
                               cost_sum_ms=10, cost_max_ms=10)
    ApiCallStatHour.objects.create(stat_date=today, stat_hour=1, service=service_of(PATH_A),
                                   path=PATH_A, app_id=doomed, status_code=10000,
                                   call_count=1, cost_sum_ms=10, cost_max_ms=10)
    purged = purge_app(doomed)
    check('purge_app 清掉两张表里该项目的行',
          purged == 2 and not ApiCallStat.objects.filter(app_id=doomed).exists()
          and not ApiCallStatHour.objects.filter(app_id=doomed).exists(), f'purged={purged}')
    check('purge_app 不误删「开放接口 / 未认证」桶', purge_app(NO_APP) == 0
          and ApiCallStat.objects.filter(app_id=TEST_APP).exists())

    # 页面端到端：测试数据用的 TEST_APP 不在接入项目表里，统计页应显示「已删除项目」
    client, admin, created_admin = _superadmin()
    try:
        body = client.get('/console/stats/').content.decode()
        check('统计页把查不到名字的项目标为「已删除项目」', '已删除项目' in body)
        check('筛选下拉仍保留 app_id（便于对照排查）', TEST_APP in body)
    finally:
        if created_admin:
            created_admin.delete()


# ───────────────────────── 主流程 ─────────────────────────

def main():
    print('\nAPI 调用统计回归测试开始（两级预聚合）')
    cleanup()
    try:
        build_dataset()
        round1_consistency()
        round2_query()
        round3_hourly()
        round4_filters()
        round5_rate_level()
        round6_prune()
        round7_pages()
        round8_public_api()
        round9_labels()
    finally:
        cleanup()
        print('\n测试数据已清理')
    print(f'\n{"=" * 70}')
    print(f'总计：PASS {_PASSED} / FAIL {_FAILED}')
    if _FAILURES:
        print('失败项：')
        for name in _FAILURES:
            print(f'  - {name}')
    print('=' * 70)
    return 1 if _FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
