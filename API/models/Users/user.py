"""用户中心数据模型

统一认证中心（UAC）：为所有接入项目提供统一的用户注册 / 登录 / 身份验证能力。
各项目不再各自维护密码，只保存用户中心返回的 user_id。

用户中心强耦合功能放在同一文件中：
    User              - 用户主表（账号系统分配、纯数字 6-12 位、全局唯一；
                        可选绑定邮箱/手机号作为登录凭证，绑定后需验证才能登录）
    UserToken         - 登录凭证表（Token 绑定「用户 + 项目」，不同项目的 Token 互不通用）
    UserVerifyRecord  - 验证记录表（统一表：邮箱/手机号等所有验证方式共用，
                        验证码或激活链接二选一激活，type 区分验证方式，后续新增方式零建表）

字段说明:
    User:
        id             - 用户唯一ID（UUID 主键）
        account        - 账号（系统随机分配，纯数字 6-12 位，全局唯一，用户不可自定义）
        username       - 用户名（用户自填，允许重复，仅作展示/昵称用途，不作为登录凭证）
        password       - 密码哈希（Django PBKDF2 加盐哈希，不存明文）
        email          - 邮箱（可选，全局唯一，作为邮箱登录凭证；绑定后需验证邮件）
        email_verified - 邮箱是否已验证（False 时不可用邮箱登录）
        phone          - 手机号（可选，全局唯一，作为手机号登录凭证；绑定后需短信验证）
        phone_verified - 手机号是否已验证（False 时不可用手机号登录）
        status         - 启用状态（True=正常，False=封禁）
        create_time / updated_time - 继承 BaseModel

    说明：邮箱/手机号等验证方式的启用与否由 AuthMethod 配置表控制（后台可开关），
    全部关闭时降级为「用户名 + 密码」注册/登录（永远可用）。

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

    UserVerifyRecord:
        id            - 验证ID（UUID 主键）
        user          - 关联 User（外键，可空：两步注册的意向记录在完成注册建号前无用户，建号后回填）
        scene         - 验证场景（register=两步注册意向 / login=登录验证码），区分验证码用途
        username      - 两步注册暂存的用户名（建号时使用）
        password_hash - 两步注册暂存的密码哈希（建号时使用）
        type          - 验证方式类型（email / phone / 后续扩展），与 AuthMethod.type 对应
        credential    - 验证凭证（邮箱地址或手机号，发起验证时填写，便于核对）
        code          - 验证码（本地生成并校验；手机号由阿里云生成后服务端接收落库）
        token         - 激活链接标识（仅邮箱 link/both 模式使用，手机号方式为空）
        expire_time / is_used - 过期时间 / 是否已使用（校验成功后置 True，一次性有效）
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
    email = models.EmailField('邮箱', max_length=254, unique=True, null=True, blank=True,
                              db_index=True,
                              help_text='邮箱登录凭证，全局唯一；注册时可选择绑定，绑定后需验证邮件才能登录')
    email_verified = models.BooleanField('邮箱已验证', default=False,
                                         help_text='绑定的邮箱是否已通过验证邮件确认，未验证不可用邮箱登录')
    phone = models.CharField('手机号', max_length=20, unique=True, null=True, blank=True,
                             db_index=True,
                             help_text='手机号登录凭证（中国大陆 11 位数字），全局唯一；注册时可选择绑定，绑定后需短信验证才能登录')
    phone_verified = models.BooleanField('手机号已验证', default=False,
                                         help_text='绑定的手机号是否已通过短信验证码确认，未验证不可用手机号登录')
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


class UserVerifyRecord(BaseModel):
    """验证记录（统一表：邮箱/手机号等所有验证方式共用）

    验证形式：
        code  - 验证码（邮箱/手机号均使用，本地生成并校验；手机号由阿里云生成后服务端接收落库）
        token - 激活链接标识（仅邮箱 link/both 模式使用，手机号方式为空）

    场景（scene）：
        register - 两步注册意向：注册时先发验证码暂存意向（不建号），
                   校验通过后才创建账号（complete_register），username/password_hash 为暂存值
        login    - 登录验证码：登录时先发验证码，校验通过后签发 Token
    """
    id = models.UUIDField('验证ID', primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='verify_records',
        verbose_name='关联用户',
        help_text='可空：两步注册意向在完成注册建号前无用户，建号后回填',
    )
    scene = models.CharField('验证场景', max_length=20, db_index=True, default='verify',
                             help_text='register=两步注册意向 / login=登录验证码，区分验证码用途')
    register_batch = models.CharField('注册批次', max_length=36, null=True, blank=True, db_index=True,
                                      help_text='两步注册：同一次注册请求（如同时绑定邮箱+手机号）共享批次，完成注册时合并为同一账号')
    username = models.CharField('暂存用户名', max_length=50, blank=True, default='',
                                help_text='两步注册暂存，完成注册建号时使用')
    password_hash = models.CharField('暂存密码哈希', max_length=128, blank=True, default='',
                                     help_text='两步注册暂存，完成注册建号时使用（不存明文）')
    type = models.CharField('验证方式', max_length=20, db_index=True,
                            help_text='验证方式类型（email / phone / 后续扩展），与 AuthMethod.type 对应')
    credential = models.CharField('验证凭证', max_length=254, db_index=True,
                                  help_text='发起验证时填写的邮箱地址或手机号，便于核对')
    code = models.CharField('验证码', max_length=8,
                            help_text='6 位数字验证码，验证形式为 code/both 时使用')
    token = models.CharField('激活链接Token', max_length=64, unique=True, null=True, blank=True,
                             db_index=True,
                             help_text='一次性激活链接标识，验证形式为 link/both 时使用，手机号方式为空')
    expire_time = models.DateTimeField('过期时间', db_index=True)
    is_used = models.BooleanField('是否已使用', default=False,
                                  help_text='校验成功后置 True，一次性有效')

    class Meta:
        db_table = 'user_verify_record'
        verbose_name = '验证记录'
        verbose_name_plural = '验证记录'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['type', 'credential'], name='idx_verify_type_credential'),
            models.Index(fields=['scene', 'type', 'credential'], name='idx_verify_scene_type_cred'),
        ]

    def __str__(self):
        return f'{self.user} -> {self.credential} ({self.type})'

    @property
    def is_valid(self) -> bool:
        """验证记录是否有效（未使用 + 未过期）"""
        if self.is_used:
            return False
        if self.expire_time and timezone.now() >= self.expire_time:
            return False
        return True
