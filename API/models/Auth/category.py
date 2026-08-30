"""API 服务分类认证模型（分类树）

以「分类树」替代原先的 ApiAuthPolicy 逐条策略配置：
- 每个分类节点对应后端 API/apis/ 下的一个服务目录，层级与 Apifox 文件夹一致
- 认证模式三态：inherit=跟随上级、auth=需要用户中心认证、open=开放（无需认证）
- 生效规则：请求路径按「最长前缀」匹配到分类节点后，沿父链向上取第一个非 inherit 的配置；
  整条链全为 inherit 时默认开放（不要求认证）

覆盖能力：父级设为 auth 后，可单独把某个子级设为 open，实现「父级要求认证、子级单独开放」。
"""
from django.core.exceptions import ValidationError
from django.db import models

from API.common.base import BaseModel


class ApiCategory(BaseModel):
    """API 服务分类节点（自关联树形结构）"""

    AUTH_MODE_CHOICES = [
        ('inherit', '跟随上级'),
        ('auth', '需要认证'),
        ('open', '开放'),
    ]

    name = models.CharField('分类名称', max_length=100)
    path_prefix = models.CharField('URL前缀', max_length=200, unique=True,
                                   help_text='如 /api/user_center/ 、 /api/user_center/users/，请求路径按最长前缀匹配')
    parent = models.ForeignKey('self', verbose_name='上级分类', null=True, blank=True,
                               on_delete=models.CASCADE, related_name='children')
    auth_mode = models.CharField('认证模式', max_length=10, choices=AUTH_MODE_CHOICES, default='inherit',
                                 help_text='inherit=跟随上级；auth=需要用户中心认证；open=开放（无需认证）')
    status = models.BooleanField('启用', default=True,
                                 help_text='停用后该分类不参与匹配（恢复默认开放）')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        verbose_name = 'API服务分类'
        verbose_name_plural = 'API服务分类'
        ordering = ('path_prefix',)

    def __str__(self):
        mode_label = dict(self.AUTH_MODE_CHOICES).get(self.auth_mode, self.auth_mode)
        return f'{self.name} ({self.path_prefix}) - {mode_label}'

    def clean(self):
        """防止把自身或其后代设为上级（成环会破坏继承链）"""
        super().clean()
        if self.parent_id:
            node = self.parent
            seen = set()
            while node is not None and node.id not in seen:
                if node.id == self.id:
                    raise ValidationError('上级分类不能是自身或其子级，否则会形成循环依赖')
                seen.add(node.id)
                node = node.parent
