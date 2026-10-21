"""自研验证码 · 行为验证（影子模式）

当前阶段只做「采集 → 打分 → 记录」，**不参与任何放行 / 拦截决策**：
官网表单提交时前端上报一组聚合特征，后端按规则给出 0-100 风险分并落一条样本，
监控面板用这些样本校准阈值。等真实分数分布稳定后，再开启分流
（低风险免验证码 / 中风险滑块 / 高风险点选）。

隐私边界：
- 前端只上报「聚合特征」：停留时长、指针移动次数与总距离、击键间隔、修正次数、
  焦点 / 可见性切换次数、`navigator.webdriver` 等环境信号；
- **不上报任何输入内容、不落原始坐标**，键间隔只保留最近 200 个；
- 样本只保留 30 天，每次写入顺带限批清理。

评分口径（标准档，低风险阈值 30）：
    < 30    低风险（未来可免验证码）
    30-69   中风险（未来出滑块）
    >= 70   高风险（未来出点选 / 字符 + 冷却）
"""
import logging
from datetime import timedelta

from django.utils import timezone

from API.models.Captcha.behavior import BehaviorSample

logger = logging.getLogger('captcha_self.behavior')

#: 低 / 中风险分界
LOW_MAX = 30
HIGH_MIN = 70

#: 样本保留天数
KEEP_DAYS = 30
#: 单次清理上限，避免一条 DELETE 锁表太久
CLEANUP_BATCH = 200

#: 命中项 → 展示名（模板里再翻译）
HIT_LABELS = {
    'too_fast': '提交过快',
    'no_pointer': '无指针移动',
    'instant_keys': '击键过快',
    'webdriver': '自动化驱动',
    'headless_ua': '无头浏览器',
    'hidden_tab': '多次切走页面',
    'focus_switch': '频繁失焦',
    'ip_burst': '同 IP 高频提交',
}


def band_of(score):
    """风险分 → 档位"""
    if score >= HIGH_MIN:
        return BehaviorSample.BAND_HIGH
    if score >= LOW_MAX:
        return BehaviorSample.BAND_MID
    return BehaviorSample.BAND_LOW


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def score_features(features):
    """按规则给聚合特征打分

    :param features: 前端上报的字典（字段缺失按 0 处理）
    :return: (score, hits) —— score 0-100，hits 为命中的规则键列表
    """
    if not isinstance(features, dict):
        return 100, ['no_features']

    total = 0
    hits = []

    dwell = _number(features.get('dwell_ms'))
    if dwell < 1500:
        total += 40
        hits.append('too_fast')

    moves = _number(features.get('pointer_moves'))
    if moves < 3:
        total += 25
        hits.append('no_pointer')

    raw_intervals = features.get('key_intervals') or []
    intervals = []
    if isinstance(raw_intervals, list):
        for item in raw_intervals[:200]:
            value = _number(item, default=-1)
            if value >= 0:
                intervals.append(value)
    key_count = _number(features.get('key_count'))
    if key_count >= 4 and intervals and max(intervals) < 30:
        total += 30
        hits.append('instant_keys')

    if features.get('webdriver'):
        total += 60
        hits.append('webdriver')
    if features.get('ua_headless'):
        total += 60
        hits.append('headless_ua')

    if _number(features.get('hidden_count')) >= 3:
        total += 10
        hits.append('hidden_tab')
    if _number(features.get('focus_changes')) >= 5:
        total += 10
        hits.append('focus_switch')

    return min(total, 100), hits


def record(scene, features, extra_hits=None):
    """打分并落一条样本（任何异常只记日志，不影响业务请求）

    :return: (score, band, hits)
    """
    score, hits = score_features(features)
    if extra_hits:
        hits = list(dict.fromkeys(list(hits) + list(extra_hits)))
    score = min(100, score)
    band = band_of(score)
    try:
        BehaviorSample.objects.create(scene=scene, score=score, band=band, hits=hits)
        _cleanup()
    except Exception:
        logger.exception('行为验证样本写入失败：scene=%s score=%s', scene, score)
    return score, band, hits


def _cleanup():
    """限批清理 30 天前的样本"""
    cutoff = timezone.now() - timedelta(days=KEEP_DAYS)
    ids = list(
        BehaviorSample.objects.filter(create_time__lt=cutoff)
        .values_list('id', flat=True)[:CLEANUP_BATCH]
    )
    if ids:
        BehaviorSample.objects.filter(id__in=ids).delete()
