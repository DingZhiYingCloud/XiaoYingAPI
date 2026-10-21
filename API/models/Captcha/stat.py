"""自研验证码统计模型

    CaptchaStat - 按「天 + 线路」累计的验证码指标（监控面板数据源）

字段说明:
    day          - 统计日期（按服务器本地时区切日）
    kind         - 线路（char=字符 / arithmetic=算术 / slider=滑块 / click=汉字点选）
    generated    - 生成次数
    passed       - 校验通过次数
    failed       - 校验失败次数（不含被限流 / 冷却拦截的请求）
    blocked      - 被限流或连续失败冷却拦截的次数
    fail_*       - 失败原因分解（过期 / 已使用 / 答案错 / 轨迹异常 / 不存在）

为什么单独建表而不是从挑战表现算：
    `CaptchaChallenge` 等三张表只保留短有效期记录，生成接口还会惰性清理过期行，
    过期即删，无法回算历史趋势；`used` 也不区分「通过」还是「答错」。
    因此把聚合计数单独落库，按天一行，查询便宜且不受清理影响。

写入走 `API/apis/captcha_self/stats.py`（`F()` 原子累加），读取在控制台监控面板。
"""
from django.db import models

from API.common.base import BaseModel


class CaptchaStat(BaseModel):
    """验证码按天 · 按线路的累计指标"""

    KIND_CHAR = 'char'
    KIND_ARITHMETIC = 'arithmetic'
    KIND_SLIDER = 'slider'
    KIND_CLICK = 'click'
    KIND_CHOICES = [
        (KIND_CHAR, '字符图片'),
        (KIND_ARITHMETIC, '算术'),
        (KIND_SLIDER, '滑块'),
        (KIND_CLICK, '汉字点选'),
    ]

    #: 失败原因 → 字段名（与前端展示顺序一致）
    REASON_CHOICES = [
        ('expired', '已过期'),
        ('used', '已使用'),
        ('wrong', '答案错误'),
        ('abnormal', '轨迹异常'),
        ('invalid', '不存在'),
    ]

    day = models.DateField('统计日期', db_index=True, help_text='按服务器本地时区切日')
    kind = models.CharField('线路', max_length=12, choices=KIND_CHOICES,
                            help_text='char / arithmetic / slider / click')
    generated = models.PositiveIntegerField('生成次数', default=0)
    passed = models.PositiveIntegerField('通过次数', default=0)
    failed = models.PositiveIntegerField('失败次数', default=0,
                                         help_text='答案错误 / 过期 / 已使用等业务失败，不含限流拦截')
    blocked = models.PositiveIntegerField('拦截次数', default=0,
                                          help_text='被 IP 限流或连续失败冷却拦截的请求')
    fail_expired = models.PositiveIntegerField('失败-已过期', default=0)
    fail_used = models.PositiveIntegerField('失败-已使用', default=0)
    fail_wrong = models.PositiveIntegerField('失败-答案错误', default=0)
    fail_abnormal = models.PositiveIntegerField('失败-轨迹异常', default=0)
    fail_invalid = models.PositiveIntegerField('失败-不存在', default=0)

    class Meta:
        db_table = 'captcha_stat'
        verbose_name = '验证码统计'
        verbose_name_plural = '验证码统计'
        ordering = ['-day', 'kind']
        constraints = [
            models.UniqueConstraint(fields=['day', 'kind'],
                                    name='uniq_captcha_stat_day_kind'),
        ]

    def __str__(self):
        return f'{self.day} {self.get_kind_display()}：生成 {self.generated} / 通过 {self.passed} / 失败 {self.failed}'
