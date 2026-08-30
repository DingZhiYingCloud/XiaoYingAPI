"""用户中心数据模型

统一认证中心（UAC）：为所有接入项目提供统一的用户注册 / 登录 / 身份验证能力。
各项目不再各自维护密码，只保存用户中心返回的 user_id。

用户中心强耦合功能放在同一文件中：
    User      - 用户主表（账号系统分配、纯数字 6-12 位、全局唯一）
    UserToken - 登录凭证表（Token 绑定「用户 + 项目」，不同项目的 Token 互不通用）

字段说明:
    User:
        id        - 用户唯一ID（UUID 主键）
        account   - 账号（系统随机分配，纯数字 6-12 位，全局唯一，用户不可自定义）
        username  - 用户名（用户自填，允许重复，仅作展示/昵称用途，不作为登录凭证）
        password  - 密码哈希（Django PBKDF2 加盐哈希，不存明文）
        status    - 启用状态（True=正常，False=封禁）
        create_time / updated_time - 继承 BaseModel

    UserToken:
        id              - Token 唯一ID（UUID 主键）
        user            - 关联 User（外键）
        app             - 关联接入项目 UserApp（外键，Token 绑定项目）
        token           - Token 值（唯一）
        expire_time     - 过期时间
        last_active_time- 最后活跃时间
        create_time / updated_time - 继承 BaseModel

    说明：Token 并存数量不在此处限制，由各接入项目自行控制
    （子项目根据自己的业务（如 VIP 配额）管理用户的登录态数量）。
"""
import uuid

from django.db import models
from django.utils import timezone

from API.common.base import BaseModel
from API.models.Projects.app import UserApp


class User(BaseModel):
    """用户主表"""
    id = models.UUIDField('用户ID', primary_key=True, default=uuid.uuid4, editable=False)
    account = models.CharField('账号', max_length=12, unique=True, db_index=True,
                               help_text='系统分配，纯数字 6-12 位，全局唯一，不可自定义')
    username = models.CharField('用户名', max_length=50, blank=True, default='',
                                help_text='用户自填，允许重复，仅作展示用途')
    password = models.CharField('密码哈希', max_length=128,
                                help_text='Django PBKDF2 加盐哈希，不存明文')
    status = models.BooleanField('启用状态', default=True, db_index=True,
                                 help_text='True=正常，False=封禁')

    class Meta:
        db_table = 'user'
        verbose_name = '用户'
        verbose_name_plural = '用户'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.account} ({self.username})'


class UserToken(BaseModel):
    """用户登录凭证（Token 绑定用户 + 接入项目）"""
    id = models.UUIDField('TokenID', primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tokens',
        verbose_name='关联用户',
    )
    app = models.ForeignKey(
        UserApp,
        on_delete=models.CASCADE,
        related_name='tokens',
        verbose_name='关联项目',
        help_text='Token 绑定项目，不同项目的 Token 互不通用',
    )
    token = models.CharField('Token', max_length=64, unique=True, db_index=True)
    expire_time = models.DateTimeField('过期时间', db_index=True)
    last_active_time = models.DateTimeField('最后活跃时间', null=True, blank=True)

    class Meta:
        db_table = 'user_token'
        verbose_name = '用户Token'
        verbose_name_plural = '用户Token'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.user} -> {self.app}'

    @property
    def is_valid(self) -> bool:
        """Token 是否有效（未过期 + 用户启用 + 项目启用）"""
        if self.expire_time and timezone.now() >= self.expire_time:
            return False
        if not self.user.status:
            return False
        if not self.app.status:
            return False
        return True
