"""API 服务策略模型（服务 → 线路 → 端点 三级，逐级继承）

三级粒度：
- 服务级  path_prefix 形如 ``/api/movies/``
- 线路级  path_prefix 形如 ``/api/movies/movie_555/``
- 端点级  path_prefix 形如 ``/api/movies/movie_555/list``（精确到单个接口路径）

一条策略可覆盖**同一服务下的多条线路**：``path_prefix`` 存第一条（主前缀），
其余线路存 ``extra_prefixes``，两者合起来由 ``all_prefixes`` 给出。
该能力仅作用于线路级（服务级 / 端点级恒为单前缀）。

每级的配置项都可单独设「跟随上级」（inherit），未设置则向上一级继承，
最终兜底：
- status       -> normal（正常）
- auth_mode    -> auth（需要签名，全局 fail-closed）
- docs_visible -> visible（展示在官网文档中心）
- audience     -> normal（对外正常可用）

生效顺序：请求路径按 path_prefix 命中「全部」策略，按前缀长度降序（最具体在前），
逐字段取第一个非 inherit 的值。认证判定的唯一口径是
``API/common/middleware.py`` 的 ``requires_auth()`` / ``resolve_service_policy()``。

注意：``auth_mode=open`` 时额度不参与判定 —— 开放接口不校验签名、拿不到调用项目。

**调用单价不在这里**：单价由独立的 ``ApiPricePolicy``（见 ``API/models/Credit/price.py``，
控制台「线路价格」页）管理，与本策略表解耦；额度判定与扣费口径见
``API/common/credit_guard.py``。
"""
from django.core.exceptions import ValidationError
from django.db import models

from API.common.base import BaseModel


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
    extra_prefixes = models.JSONField('附加线路前缀', default=list, blank=True,
                                      help_text='线路级多选时的其余线路前缀（须与主前缀同属一个服务）；'
                                                '与主前缀共同构成本策略覆盖的全部线路')
    status = models.CharField('服务状态', max_length=12, choices=STATUS_CHOICES, default='inherit',
                              help_text='inherit=跟随上级；正常 / 开发中 / 维护中 / 已下线')
    auth_mode = models.CharField('认证模式', max_length=10, choices=AUTH_MODE_CHOICES, default='inherit',
                                 help_text='inherit=跟随上级；auth=需要签名；open=开放（无需签名）')
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

    @property
    def all_prefixes(self):
        """本策略覆盖的全部 URL 前缀（主前缀在前）"""
        return [self.path_prefix, *(self.extra_prefixes or [])]

    def clean(self):
        """校验 level 与全部前缀的形状一致（不依赖 DB，纯字符串校验）

        一条策略可覆盖同一服务下的多条线路，故主前缀与附加前缀各自都要满足
        该层级的前缀形状；多线路还必须同属一个服务。
        """
        super().clean()
        prefixes = [p.strip() for p in self.all_prefixes if (p or '').strip()]
        if not prefixes:
            raise ValidationError({'path_prefix': 'URL 前缀不能为空'})
        if len(set(prefixes)) != len(prefixes):
            raise ValidationError({'path_prefix': 'URL 前缀不能重复'})
        services = set()
        for prefix in prefixes:
            if not prefix.startswith('/api/'):
                raise ValidationError({'path_prefix': 'URL 前缀必须以 /api/ 开头'})
            segments = [seg for seg in prefix.strip('/').split('/') if seg]  # ['api', ...]
            depth = len(segments) - 1  # 去掉前导 'api'
            trailing_slash = prefix.endswith('/')
            if depth < 1:
                raise ValidationError({'path_prefix': 'URL 前缀至少要到服务级，如 /api/movies/'})
            if self.level == 'service' and (depth != 1 or not trailing_slash):
                raise ValidationError({'path_prefix': '服务级前缀必须是 /api/xxx/ 形式'})
            if self.level == 'channel':
                if depth != 2:
                    raise ValidationError({'path_prefix': '线路级前缀必须是 /api/xxx/yyy（可带结尾斜杠）形式'})
                services.add('/' + '/'.join(segments[:2]) + '/')
            if self.level == 'endpoint' and (depth < 3 or trailing_slash):
                raise ValidationError({'path_prefix': '端点级前缀必须是 /api/xxx/yyy/zzz 形式（不带结尾斜杠）'})
        if len(services) > 1:
            raise ValidationError({'path_prefix': '一条策略只能覆盖同一个服务下的线路'})
