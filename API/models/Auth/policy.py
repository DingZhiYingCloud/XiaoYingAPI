"""API 服务策略模型（服务 → 线路 → 端点 三级，逐级继承）

三级粒度：
- 服务级  path_prefix 形如 ``/api/movies/``
- 线路级  path_prefix 形如 ``/api/movies/movie_555/``
- 端点级  path_prefix 形如 ``/api/movies/movie_555/list``（精确到单个接口路径）

每级的配置项都可单独设「跟随上级」（inherit），未设置则向上一级继承，
最终兜底：
- status       -> normal（正常）
- auth_mode    -> auth（需要签名，全局 fail-closed）
- app_scope    -> all（不限项目）
- docs_visible -> visible（展示在官网文档中心）
- audience     -> normal（对外正常可用）

生效顺序：请求路径按 path_prefix 命中「全部」策略，按前缀长度降序（最具体在前），
逐字段取第一个非 inherit 的值。认证判定的唯一口径是
``API/common/middleware.py`` 的 ``requires_auth()`` / ``resolve_service_policy()``。

注意：``auth_mode=open`` 时白名单无意义 —— 开放接口不校验签名、拿不到调用项目。
"""
from django.core.exceptions import ValidationError
from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import UserApp


class ApiServicePolicy(BaseModel):
    """API 服务策略（服务 / 线路 / 端点三级，逐级继承）"""

    LEVEL_CHOICES = [
        ('service', '服务'),
        ('channel', '线路'),
        ('endpoint', '端点'),
    ]
    STATUS_CHOICES = [
        ('inherit', '跟随上级'),
        ('normal', '正常'),
        ('dev', '开发中'),
        ('maintenance', '维护中'),
        ('offline', '已下线'),
    ]
    AUTH_MODE_CHOICES = [
        ('inherit', '跟随上级'),
        ('auth', '需要签名'),
        ('open', '开放'),
    ]
    APP_SCOPE_CHOICES = [
        ('inherit', '跟随上级'),
        ('all', '不限项目'),
        ('whitelist', '仅白名单项目'),
    ]
    DOCS_VISIBLE_CHOICES = [
        ('inherit', '跟随上级'),
        ('visible', '文档展示'),
        ('hidden', '文档隐藏'),
    ]
    AUDIENCE_CHOICES = [
        ('inherit', '跟随上级'),
        ('normal', '正常'),
        ('admin_only', '仅专属管理员'),
    ]

    name = models.CharField('策略名称', max_length=100)
    level = models.CharField('层级', max_length=10, choices=LEVEL_CHOICES, default='service',
                             help_text='服务=整个服务；线路=服务下的某条线路；端点=精确到单个接口路径')
    path_prefix = models.CharField('URL前缀', max_length=200, unique=True,
                                   help_text='服务级如 /api/movies/ ；线路级如 /api/movies/movie_555/ ；'
                                             '端点级如 /api/movies/movie_555/list')
    status = models.CharField('服务状态', max_length=12, choices=STATUS_CHOICES, default='inherit',
                              help_text='inherit=跟随上级；正常 / 开发中 / 维护中 / 已下线')
    auth_mode = models.CharField('认证模式', max_length=10, choices=AUTH_MODE_CHOICES, default='inherit',
                                 help_text='inherit=跟随上级；auth=需要签名；open=开放（无需签名）')
    app_scope = models.CharField('项目范围', max_length=10, choices=APP_SCOPE_CHOICES, default='inherit',
                                 help_text='inherit=跟随上级；all=不限项目；whitelist=仅白名单项目可调用')
    apps = models.ManyToManyField(UserApp, blank=True, related_name='service_policies',
                                  verbose_name='白名单项目',
                                  help_text='仅生效值 app_scope=whitelist 时生效：名单内的项目才可调用')
    docs_visible = models.CharField('文档可见性', max_length=10, choices=DOCS_VISIBLE_CHOICES,
                                    default='inherit',
                                    help_text='inherit=跟随上级；visible=展示在官网文档中心；'
                                              'hidden=在文档页与在线调试里隐藏（后台内部接口用）')
    audience = models.CharField('使用范围', max_length=12, choices=AUDIENCE_CHOICES, default='inherit',
                                help_text='inherit=跟随上级；normal=对外正常可用；'
                                          'admin_only=仅专属管理员（仅后台内部使用，外部调用返回 20020）')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        verbose_name = 'API服务策略'
        verbose_name_plural = 'API服务策略'
        ordering = ('path_prefix',)

    def __str__(self):
        level_label = dict(self.LEVEL_CHOICES).get(self.level, self.level)
        return f'{self.name} ({self.path_prefix}) - {level_label}'

    def clean(self):
        """校验 level 与 path_prefix 的形状一致（不依赖 DB，纯字符串校验）"""
        super().clean()
        prefix = (self.path_prefix or '').strip()
        if not prefix.startswith('/api/'):
            raise ValidationError({'path_prefix': 'URL 前缀必须以 /api/ 开头'})
        segments = [seg for seg in prefix.strip('/').split('/') if seg]  # ['api', ...]
        depth = len(segments) - 1  # 去掉前导 'api'
        trailing_slash = prefix.endswith('/')
        if depth < 1:
            raise ValidationError({'path_prefix': 'URL 前缀至少要到服务级，如 /api/movies/'})
        if self.level == 'service' and (depth != 1 or not trailing_slash):
            raise ValidationError({'path_prefix': '服务级前缀必须是 /api/xxx/ 形式'})
        if self.level == 'channel' and depth != 2:
            raise ValidationError({'path_prefix': '线路级前缀必须是 /api/xxx/yyy（可带结尾斜杠）形式'})
        if self.level == 'endpoint' and (depth < 3 or trailing_slash):
            raise ValidationError({'path_prefix': '端点级前缀必须是 /api/xxx/yyy/zzz 形式（不带结尾斜杠）'})
