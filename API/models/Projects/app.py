"""接入项目管理模型

用户中心接入方管理：任何项目想接入用户中心（注册 / 登录 / 验证用户），
必须先在小影 API 中注册成为接入项目，获得独立的 APPID + APPSECRET。
未注册的项目无法调用用户中心接口。

字段说明:
    UserApp:
        id               - 项目唯一ID（UUID 主键）
        name             - 应用名称（唯一，不可重复）
        owner            - 项目归属的注册用户（外键，可空）；留空 = 平台自有项目，只有超管能管
        app_id           - APPID（公开标识，唯一，系统自动生成，前缀 app_，
                            创建后固定不可修改）
        app_secret       - APPSECRET（签名密钥，系统自动生成，前缀 sk_，
                            创建后固定不可修改，仅项目方与用户中心知道）
        token_expire_days- Token 默认有效期天数（后台可配置，每个项目可不同）
        balance          - 当前可用额度（点数，Decimal）。新建默认 0 = 什么都调不了
                            （开放接口除外）；由超管在控制台手动充值增加，
                            调用成功后按服务单价扣减（见 API/common/credit_guard.py）
        status           - 启用状态（True=正常，False=停止该项目的接入权限）
        create_time / updated_time - 继承 BaseModel

额度口径（见 API/common/credit_guard.py）：**有余额才能调接口**，扣费只在调用成功
（业务码 10000）时发生 —— 中间件在放行前判「余额 ≥ 本次单价」，实际扣减在调用统计
批量落库时进行（进程内缓冲，满 200 条或每 5 秒一次）。因此判定略滞后于真实用量，
允许余额短暂为负（表示欠费，下次充值自动抵扣）。

自动生成规则:
    - 创建项目时无需手动填写 app_id / app_secret，系统自动生成并保证全局唯一
    - app_id 格式: app_ + 28 位随机 hex（共 32 字符，公开标识）
    - app_secret 格式: sk_ + 60 位随机 hex（共 63 字符，机密密钥）
    - 创建后固定不可修改：更新时强制保留原值，防止误改导致已接入子项目全部失效
"""
import secrets
import uuid

from django.db import IntegrityError, models

from API.common.base import BaseModel
from API.common.credential_crypto import decrypt_credential, encrypt_credential


class EncryptedSecretField(models.CharField):
    """落库自动 AES 加密的 CharField（S-06 整改）

    Python 侧（含 admin 表单、业务代码）读写的都是明文；
    Django 写库时自动加密、读库时自动解密。DB dump / 备份文件中仅见 enc:v1: 密文。
    注：SQLite 不校验列长度，密文长度可自由存放；若未来迁移 MySQL 需调整列宽。
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or (isinstance(value, str) and value.startswith('enc:v1:')):
            return value
        return encrypt_credential(value)

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return decrypt_credential(value)


class UserApp(BaseModel):
    """接入项目"""
    id = models.UUIDField('项目ID', primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('应用名称', max_length=100, unique=True,
                            help_text='应用名称全局唯一，不可重复')
    owner = models.ForeignKey(
        'API.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='owned_apps', db_index=True, verbose_name='归属用户',
        help_text='项目归属的注册用户，可在前台「我的项目」自助管理；'
                  '留空表示平台自有项目，只有超管能管',
    )
    app_id = models.CharField('APPID', max_length=32, unique=True, db_index=True, blank=True,
                              help_text='公开标识，系统自动生成（app_ 前缀），创建后固定')
    app_secret = EncryptedSecretField('APPSECRET', max_length=200, blank=True,
                                      help_text='签名密钥，系统自动生成（sk_ 前缀），HMAC-SHA256 签名用，创建后固定；落库 AES 加密存储（S-06）')
    token_expire_days = models.PositiveIntegerField('Token有效天数', default=7,
                                                    help_text='该项目的登录 Token 默认有效期（天），后台可修改')
    balance = models.DecimalField(
        '可用额度', max_digits=16, decimal_places=2, default=0,
        help_text='点数余额：新建默认 0（什么都调不了），超管在控制台充值后增加，'
                  '调用成功按服务单价扣减；允许为负（欠费，下次充值抵扣）',
    )
    status = models.BooleanField('启用状态', default=True, db_index=True,
                                 help_text='True=正常，False=停止该项目接入权限')

    # 自动生成格式常量
    APP_ID_PREFIX = 'app_'
    APP_SECRET_PREFIX = 'sk_'
    # 唯一冲突自动重试次数（极低概率，防御并发创建）
    GENERATE_RETRY_TIMES = 5

    @classmethod
    def _generate_app_id(cls) -> str:
        """生成 APPID：app_ + 28 位随机 hex（共 32 字符）"""
        return f'{cls.APP_ID_PREFIX}{secrets.token_hex(14)}'

    @classmethod
    def _generate_app_secret(cls) -> str:
        """生成 APPSECRET：sk_ + 60 位随机 hex（共 63 字符）"""
        return f'{cls.APP_SECRET_PREFIX}{secrets.token_hex(30)}'

    def save(self, *args, **kwargs):
        """创建时自动生成 APPID/APPSECRET；更新时固定原值不可修改"""
        creating = self._state.adding
        if creating and not (self.app_id and self.app_secret):
            # 创建且未提供密钥：自动生成（处理并发唯一冲突重试）
            for _ in range(self.GENERATE_RETRY_TIMES):
                self.app_id = self._generate_app_id()
                self.app_secret = self._generate_app_secret()
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    continue
            raise IntegrityError('APPID 生成冲突，自动重试失败，请重试')
        if not creating and self.pk:
            # 更新时强制保留原值，禁止手动修改已发放的密钥
            old = UserApp.objects.filter(pk=self.pk).values_list('app_id', 'app_secret').first()
            if old:
                self.app_id, self.app_secret = old
        super().save(*args, **kwargs)

    def reset_secret(self) -> str:
        """重置 APPSECRET 并返回新密钥

        走 `queryset.update()` 绕开 save() 里「更新时强制保留原值」的保护 —— 那层保护是防
        「误改导致已接入子项目全失效」，而重置密钥是**有意为之**的显式操作（旧密钥立即失效，
        调用方必须换新密钥）。密文由 EncryptedSecretField 在写库时自动加密。
        """
        self.app_secret = self._generate_app_secret()
        UserApp.objects.filter(pk=self.pk).update(app_secret=self.app_secret)
        return self.app_secret

    class Meta:
        db_table = 'user_app'
        verbose_name = '接入项目'
        verbose_name_plural = '接入项目'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.name} ({self.app_id})'
