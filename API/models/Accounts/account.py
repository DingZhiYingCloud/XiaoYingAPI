"""通用平台账号模型（多平台账号 + 登录凭据托管）

存放「平台代管的第三方网站账号」：知乎、小红书、微博、百家号、今日头条…
一行一个账号，登录凭据（Cookie 等）AES 加密落库。

设计意图（为什么做成**一张通用表**而不是每个平台一张表）：
    各平台的账号字段高度一致（账号标识 / 密码 / 登录凭据 / 状态 / 校验时间），
    差异只在「怎么判断这份凭据还有效」—— 那部分由**可插拔的校验器**承担
    （见 `API/common/platform_accounts.py` 的注册表），因此不必为每个平台重复建表。
    新增一个平台 = ① 在下面 `Platform` 加一个枚举值 ② 写一个校验函数
    ③ 在校验器注册表里加一行。**不需要动本模型、不需要迁移。**

字段说明:
    PlatformAccount:
        id              - 账号唯一ID（UUID 主键）
        platform        - 平台标识（见 `Platform` 枚举）
        account         - 账号标识（用户名 / 手机号 / 邮箱 / 备注名；同一平台内唯一）
        password        - 登录密码（落库 AES 加密，可空；先作人工记录，将来若要恢复自动登录可直接取用）
        credential      - 登录凭据（Cookie 等，落库 AES 加密）—— **爬虫接口实际使用的就是它**
        status          - 凭据状态：unknown 未校验 / valid 有效 / expired 已过期（需重新登录）
        check_message   - 最近一次校验的说明（失败原因 / 校验到的用户名等）
        last_check_time - 最近一次校验时间
        last_login_time - 最近一次「人工登录后更新凭据」的时间
        remark          - 备注
        create_time / updated_time - 继承 BaseModel

注：password 与 credential 属敏感凭据，字段层自动加解密（S-06）；接口与后台页面均不回显明文。
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import EncryptedSecretField


class Platform(models.TextChoices):
    """平台标识（新增平台只加枚举值，不用改表结构）

    注：枚举里列出的是**已知平台**；但「能不能校验凭据」取决于
    `API/common/platform_accounts.py` 里有没有注册对应校验器 ——
    没注册的平台在后台会显示为「暂不支持校验」，仍可正常存账号与凭据。
    """

    ZHIHU = 'zhihu', '知乎'
    XIAOHONGSHU = 'xiaohongshu', '小红书'
    WEIBO = 'weibo', '微博'
    BAIJIAHAO = 'baijiahao', '百家号'
    TOUTIAO = 'toutiao', '今日头条'
    DLT = 'dlt', '代练通'
    DLWZ = 'dlwz', '代练丸子'
    SERVERCHAN = 'serverchan', 'Server酱'
    OTHER = 'other', '其他'


class AccountStatus(models.TextChoices):
    """凭据状态"""

    UNKNOWN = 'unknown', '未校验'
    VALID = 'valid', '有效'
    EXPIRED = 'expired', '已过期（需重新登录）'


class PlatformAccount(BaseModel):
    """第三方平台账号（含登录凭据托管）"""

    id = models.UUIDField('账号ID', primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField('平台', max_length=32, choices=Platform.choices,
                                default=Platform.ZHIHU, db_index=True)
    account = models.CharField('账号标识', max_length=128, db_index=True,
                               help_text='用户名 / 手机号 / 邮箱 / 备注名，同一平台内唯一')
    password = EncryptedSecretField('密码', max_length=500, blank=True,
                                    help_text='落库 AES 加密存储（S-06）；页面与接口均不回显明文')
    credential = EncryptedSecretField(
        '登录凭据', max_length=8000, blank=True,
        help_text='Cookie 等登录凭据（原样一整串），落库 AES 加密存储（S-06）；爬虫接口用的就是它')
    status = models.CharField('凭据状态', max_length=16, choices=AccountStatus.choices,
                              default=AccountStatus.UNKNOWN, db_index=True)
    check_message = models.CharField('最近校验结果', max_length=255, blank=True)
    last_check_time = models.DateTimeField('最近校验时间', null=True, blank=True)
    last_login_time = models.DateTimeField('最近登录时间', null=True, blank=True,
                                           help_text='最近一次「人工登录后更新凭据」的时间')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'platform_account'
        verbose_name = '平台账号'
        verbose_name_plural = '平台账号'
        ordering = ['platform', 'account']
        constraints = [
            models.UniqueConstraint(fields=['platform', 'account'],
                                    name='uniq_platform_account'),
        ]

    def __str__(self):
        return f'{self.get_platform_display()} · {self.account}'

    @property
    def has_credential(self) -> bool:
        """是否已录入登录凭据（页面展示用，不解密）"""
        return bool(self.credential)
