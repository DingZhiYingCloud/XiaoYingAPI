"""接口公告（文档中心展示）

用途：超管在后台发布公告，挂到 **服务 / 线路 / 端点** 三级 API 对象上，在官网文档中心
对应位置展示（如「该接口参数即将调整」「本线路正在灰度」）。

挂载口径：`path_prefix` 用**真实路由前缀**，与「服务策略」（`ApiServicePolicy`）完全一致，
后台的候选目标直接取自 `API/website/service_tree.py` 的服务树，避免两套口径对不上：

- 服务级  `/api/dramas/`
- 线路级  `/api/dramas/hongguo/`（该线路下所有接口共用；一条线路可挂多条）
- 端点级  `/api/dramas/hongguo/play`

一条线路可以有多条公告，按 `sort`（数字小在前）依次平铺展示。

多语言：公告是数据库动态内容，**不做翻译** —— 后台填什么语言的文本，前台就原样显示，
所以三语访客看到的是同一份原文（与文档正文的三语翻译机制互不影响）。

生效规则由 `is_visible` 判定：启用 + 落在 [start_time, end_time] 区间内（两端可空）。
"""
from django.db import models
from django.utils import timezone

from API.common.base import BaseModel


class Announcement(BaseModel):
    """接口公告（服务 / 线路 / 端点三级挂载）"""

    SCOPE_CHOICES = [
        ('service', '服务'),
        ('channel', '线路'),
        ('endpoint', '端点'),
    ]
    LEVEL_CHOICES = [
        ('info', '信息'),
        ('success', '成功'),
        ('warning', '提醒'),
        ('error', '警告'),
    ]
    # 级别的展示定义（配色 + 图标）集中在这里，模板不得写死
    LEVEL_DEFS = {
        'info': {'label': '信息', 'alert': 'alert-info', 'icon': 'info'},
        'success': {'label': '成功', 'alert': 'alert-success', 'icon': 'circle-check'},
        'warning': {'label': '提醒', 'alert': 'alert-warning', 'icon': 'triangle-alert'},
        'error': {'label': '警告', 'alert': 'alert-error', 'icon': 'circle-x'},
    }

    title = models.CharField('标题', max_length=100)
    content = models.TextField('正文',
                               help_text='原样展示（保留换行）；填什么语言就显示什么语言，不做翻译')
    level = models.CharField('级别', max_length=10, choices=LEVEL_CHOICES, default='info',
                             help_text='决定公告的配色与图标')
    scope = models.CharField('挂载层级', max_length=10, choices=SCOPE_CHOICES, default='service',
                             help_text='服务=整个服务；线路=该线路下所有接口；端点=单个接口路径')
    path_prefix = models.CharField('URL前缀', max_length=200, db_index=True,
                                   help_text='服务级如 /api/dramas/ ；线路级如 /api/dramas/hongguo/ ；'
                                             '端点级如 /api/dramas/hongguo/play')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前（同层级内排序）')
    enabled = models.BooleanField('启用', default=True)
    start_time = models.DateTimeField('生效开始', null=True, blank=True,
                                      help_text='留空表示立即生效')
    end_time = models.DateTimeField('生效结束', null=True, blank=True,
                                    help_text='留空表示长期有效')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'docs_announcement'
        verbose_name = '接口公告'
        verbose_name_plural = '接口公告'
        ordering = ('sort', 'create_time')

    def __str__(self):
        return f'{self.get_scope_display()}:{self.path_prefix} - {self.title}'

    @property
    def level_def(self):
        """该级别的展示定义（配色 / 图标），未识别的级别回退到「信息」"""
        return self.LEVEL_DEFS.get(self.level) or self.LEVEL_DEFS['info']

    @property
    def is_visible(self):
        """当前是否应当展示（启用 + 在生效时间段内）"""
        if not self.enabled:
            return False
        now = timezone.now()
        if self.start_time and now < self.start_time:
            return False
        if self.end_time and now > self.end_time:
            return False
        return True

    @staticmethod
    def visible_queryset(now=None):
        """当前应当展示的公告查询集（过滤在数据库侧做，文档页只按前缀分组）"""
        now = now or timezone.now()
        return (Announcement.objects
                .filter(enabled=True)
                .filter(models.Q(start_time__isnull=True) | models.Q(start_time__lte=now))
                .filter(models.Q(end_time__isnull=True) | models.Q(end_time__gte=now)))
