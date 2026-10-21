"""超管控制台 - 验证码专项监控

页面：
    GET /console/captcha/?days=14    自研验证码的生成 / 通过 / 失败 / 拦截监控

数据来源：
- 趋势与分线路指标：`CaptchaStat`（`API/apis/captcha_self/stats.py` 写入，按天 + 线路累计，
  官网表单与开放接口共用同一本账）；
- 在手库存：`CaptchaChallenge` / `SliderChallenge` / `ClickWordChallenge` 三张挑战表实时统计
  （未使用且未过期 = 有效在手，超过有效期 = 待清理）。

口径提醒（页面上也写明）：
- `failed` 只算业务失败（答案错 / 过期 / 已使用 / 轨迹异常 / 不存在），不含被限流拦截的请求；
- `blocked` 是被 IP 限流或连续失败冷却挡下的请求数，按触发线路归属，总量精确；
- 三张挑战表会被生成接口惰性清理，所以库存只能看「此刻」，不能回算历史。
"""
from collections import Counter
from datetime import timedelta

from django.db.models import Avg
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from API.apis.captcha_self.behavior import HIT_LABELS
from API.apis.captcha_self.stats import REASON_FIELDS, REASON_ORDER
from API.models import CaptchaStat
from API.models.Captcha.behavior import BehaviorSample
from API.models.Captcha.captcha import CaptchaChallenge
from API.models.Captcha.click_word import ClickWordChallenge
from API.models.Captcha.slider import SliderChallenge

from .admin_auth import superadmin_required

#: 监控窗口可选天数（默认 14 天）
WINDOW_CHOICES = (7, 14, 30)
DEFAULT_DAYS = 14

#: 分线路展示顺序与名称
LINES = (
    (CaptchaStat.KIND_CHAR, '字符图片'),
    (CaptchaStat.KIND_ARITHMETIC, '算术'),
    (CaptchaStat.KIND_SLIDER, '滑块'),
    (CaptchaStat.KIND_CLICK, '汉字点选'),
)

_REASON_LABELS = dict(CaptchaStat.REASON_CHOICES)


def _rate(passed, total):
    """通过率（百分比，保留一位小数；无样本时为 0）"""
    return round(passed * 100.0 / total, 1) if total else 0.0


def _parse_days(raw):
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return days if days in WINDOW_CHOICES else DEFAULT_DAYS


def _sum_rows(rows, fields):
    """对行集合按字段求和"""
    return {field: sum(getattr(row, field) for row in rows) for field in fields}


def _inventory():
    """三张挑战表的在手库存快照"""
    now = timezone.now()
    items = (
        (CaptchaChallenge, '字符 / 算术'),
        (SliderChallenge, '滑块'),
        (ClickWordChallenge, '汉字点选'),
    )
    rows = []
    for model, label in items:
        active = model.objects.filter(used=False, expire_time__gte=now).count()
        used = model.objects.filter(used=True).count()
        expired = model.objects.filter(used=False, expire_time__lt=now).count()
        rows.append({
            'label': _(label),
            'active': active,
            'used': used,
            'expired': expired,
        })
    return rows


def _behavior_panel(start, today):
    """行为验证（影子模式）：窗口内的分数分布、档位占比、命中规则与最近样本"""
    queryset = BehaviorSample.objects.filter(create_time__date__gte=start)
    total = queryset.count()

    bands = []
    for key, label in BehaviorSample.BAND_CHOICES:
        count = queryset.filter(band=key).count()
        bands.append({
            'key': key,
            'label': _(label),
            'count': count,
            'rate': round(count * 100.0 / total, 1) if total else 0.0,
        })

    today_queryset = BehaviorSample.objects.filter(create_time__date=today)
    today_total = today_queryset.count()
    today_average = today_queryset.aggregate(value=Avg('score'))['value'] or 0
    average = queryset.aggregate(value=Avg('score'))['value'] or 0

    scores = list(queryset.values_list('score', flat=True)[:2000])
    buckets = []
    for lower in range(0, 100, 10):
        upper = lower + 9
        count = sum(1 for value in scores if lower <= value <= upper)
        buckets.append({
            'label': f'{lower}-{upper}',
            'count': count,
            'rate': round(count * 100.0 / len(scores), 1) if scores else 0.0,
        })

    hit_counter = Counter()
    for hits in queryset.values_list('hits', flat=True)[:2000]:
        for hit in (hits or []):
            hit_counter[hit] += 1
    top_hits = [
        {'key': key, 'label': _(HIT_LABELS.get(key, key)), 'count': count}
        for key, count in hit_counter.most_common(8)
    ]

    recent = []
    for sample in queryset[:15]:
        recent.append({
            'time': sample.create_time,
            'scene': _(sample.get_scene_display()),
            'score': sample.score,
            'band': _(sample.get_band_display()),
            'band_key': sample.band,
            'hits': [_(HIT_LABELS.get(hit, hit)) for hit in (sample.hits or [])],
        })

    return {
        'total': total,
        'today_total': today_total,
        'average': round(average, 1),
        'today_average': round(today_average, 1),
        'high_rate': next((item['rate'] for item in bands if item['key'] == 'high'), 0.0),
        'bands': bands,
        'buckets': buckets,
        'top_hits': top_hits,
        'recent': recent,
    }


@superadmin_required
def captcha_monitor_view(request):
    """验证码监控面板：今日概览 + 分线路 + 趋势 + 失败原因 + 库存"""
    days = _parse_days(request.GET.get('days'))
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = list(CaptchaStat.objects.filter(day__gte=start).order_by('day', 'kind'))
    fields = ('generated', 'passed', 'failed', 'blocked')

    # ── 分线路（窗口内累计） ──
    line_rows = []
    for kind, label in LINES:
        subset = [row for row in rows if row.kind == kind]
        data = _sum_rows(subset, fields)
        data.update({
            'key': kind,
            'label': _(label),
            'total_checks': data['passed'] + data['failed'],
            'rate': _rate(data['passed'], data['passed'] + data['failed']),
        })
        line_rows.append(data)
    window = _sum_rows(rows, fields)
    window['total_checks'] = window['passed'] + window['failed']
    window['rate'] = _rate(window['passed'], window['total_checks'])

    # ── 今日概览 ──
    today_rows = [row for row in rows if row.day == today]
    today_stat = _sum_rows(today_rows, fields)
    today_stat['total_checks'] = today_stat['passed'] + today_stat['failed']
    today_stat['rate'] = _rate(today_stat['passed'], today_stat['total_checks'])

    # ── 逐日趋势（生成量的百分比用于画条，最大值至少为 1 避免除零） ──
    trend = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        day_rows = [row for row in rows if row.day == day]
        data = _sum_rows(day_rows, fields)
        data['day'] = day
        data['total_checks'] = data['passed'] + data['failed']
        data['rate'] = _rate(data['passed'], data['total_checks'])
        trend.append(data)
    peak = max([item['generated'] for item in trend] or [0]) or 1
    for item in trend:
        item['bar'] = round(item['generated'] * 100.0 / peak, 1)

    # ── 失败原因分布（窗口内累计） ──
    failed_total = window['failed']
    reasons = []
    for key in REASON_ORDER:
        count = sum(getattr(row, REASON_FIELDS[key]) for row in rows)
        reasons.append({
            'key': key,
            'label': _(_REASON_LABELS.get(key, key)),
            'count': count,
            'rate': round(count * 100.0 / failed_total, 1) if failed_total else 0.0,
        })

    return render(request, 'console/captcha.html', {
        'days': days,
        'window_choices': WINDOW_CHOICES,
        'today': today,
        'overview': today_stat,
        'window': window,
        'line_rows': line_rows,
        'trend': trend,
        'reasons': reasons,
        'inventory': _inventory(),
        'behavior': _behavior_panel(start, today),
        'window_label': _('%(days)s 天') % {'days': days},
    })
