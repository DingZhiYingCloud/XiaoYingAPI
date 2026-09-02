"""认证方式配置模型

后台可开关每种验证方式（注册 / 登录 / 验证一体控制），后续新增验证方式
（如微信/QQ/短信等）只需在后台新增一行记录，无需改代码。
"""
from django.db import models

from API.common.base import BaseModel


class AuthMethod(BaseModel):
    """认证方式配置（后台开关）

    每种验证方式一行，enabled 控制该方式的 注册 / 登录 / 验证 是否可用：
        email - 邮箱（注册发验证邮件，登录需邮箱已验证）
        phone - 手机号（注册发短信验证码，登录需手机号已验证）
    全部禁用时，降级为「用户名 + 密码」注册/登录（该方式永远可用）。
    """
    type = models.CharField('方式类型', max_length=20, unique=True, db_index=True,
                            help_text='类型标识（email / phone / 后续扩展），与代码逻辑对应')
    name = models.CharField('显示名称', max_length=50,
                            help_text='后台展示名称（如 邮箱 / 手机号）')
    enabled = models.BooleanField('启用', default=True,
                                  help_text='启用后该方式的注册 / 登录 / 验证均可用，关闭即整体停用')
    description = models.CharField('说明', max_length=255, blank=True, default='')

    class Meta:
        db_table = 'auth_method'
        verbose_name = '认证方式配置'
        verbose_name_plural = '认证方式配置'
        ordering = ['type']

    def __str__(self):
        return f'{self.name}({self.type}) - {"启用" if self.enabled else "停用"}'
