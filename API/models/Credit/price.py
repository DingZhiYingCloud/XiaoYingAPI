"""API 调用单价（服务 / 线路 / 端点三级，逐级继承）

**与「服务策略」(`ApiServicePolicy`) 完全解耦**：
- 服务策略回答「这个接口能不能调」（状态 / 认证模式 / 文档可见性 / 使用范围）；
- 本表回答「调一次扣多少点」。

三级粒度（与 `service_tree` 的真实路由口径一致）：
- 服务级  path_prefix 形如 ``/api/movies/``
- 线路级  path_prefix 形如 ``/api/movies/movie_555/``
- 端点级  path_prefix 形如 ``/api/movies/movie_555/list``

**行存在 = 显式设价**：控制台「线路价格」页把服务树全量列出，只给填了价的节点建一行；
留空的节点没有行，价格向上一级取，最终兜底 `DEFAULT_PRICE`。因此本表的 `price`
不允许为空（空值用「删掉这一行」表达）。

生效价 = 命中路径的最长前缀行（端点级覆写线路级 / 服务级），都没命中则 `DEFAULT_PRICE`。
解析口径见 ``API/common/credit_guard.py`` 的 ``resolve_price()`` / ``resolve_price_detail()``。
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from API.common.base import BaseModel

# 未配置任何单价时的兜底价（点/次）：保证「有额度才能调一切服务」的口径自洽，
# 不会出现「没配价格的接口零额度也能白调」的缺口。
DEFAULT_PRICE = Decimal('1')


class ApiPricePolicy(BaseModel):
    """API 调用单价（服务 / 线路 / 端点三级，逐级继承）"""

    LEVEL_CHOICES = [
        ('service', '服务'),
        ('channel', '线路'),
        ('endpoint', '端点'),
    ]

    level = models.CharField('层级', max_length=10, choices=LEVEL_CHOICES, default='service',
                             help_text='服务=整个服务；线路=服务下的某条线路；端点=精确到单个接口路径')
    path_prefix = models.CharField('URL前缀', max_length=200, unique=True,
                                   help_text='服务级如 /api/movies/ ；线路级如 /api/movies/movie_555/ ；'
                                             '端点级如 /api/movies/movie_555/list')
    price = models.DecimalField('单价（点/次）', max_digits=12, decimal_places=4,
                                help_text='调用成功一次扣的点数；0 表示该节点免费')

    class Meta:
        db_table = 'api_price_policy'
        verbose_name = 'API 调用单价'
        verbose_name_plural = 'API 调用单价'
        ordering = ('path_prefix',)

    def __str__(self):
        level_label = dict(self.LEVEL_CHOICES).get(self.level, self.level)
        return f'{self.path_prefix} - {self.price} 点/次（{level_label}）'

    def clean(self):
        """校验 level 与 path_prefix 的形状一致（不依赖 DB，纯字符串校验）

        口径与 `ApiServicePolicy.clean()` 的服务/线路/端点形状校验一致。
        """
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
        if self.price is not None and self.price < 0:
            raise ValidationError({'price': '单价不能为负数'})
