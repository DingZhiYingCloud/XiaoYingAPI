"""海角社区账号模型

存放「通过本服务注册成功」的海角社区账号，供后续使用（账号池 / 批量操作等）。

字段说明:
    HaijiaoAccount:
        id          - 账号唯一ID（UUID 主键）
        user_id     - 源站用户 ID（海角社区的用户唯一标识，唯一键，幂等 upsert 依据）
        username    - 用户名
        password    - 密码（落库 AES 加密，见 EncryptedSecretField）
        email       - 邮箱
        nickname    - 昵称（源站返回）
        token       - 最近一次登录凭证（落库 AES 加密；注册与「按 account_id 登录」后回写）
        remark      - 备注
        last_sign_in_date - 最近一次金币签到成功/确认的日期（每日签到提速用，跨天自然失效）
        create_time / updated_time - 继承 BaseModel

注：密码与 token 属敏感凭据，读取时字段层自动解密（S-06）；接口响应中不回传密码明文。
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import EncryptedSecretField


class HaijiaoAccount(BaseModel):
    """海角社区账号"""

    id = models.UUIDField('账号ID', primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField('源站用户ID', max_length=32, unique=True, db_index=True,
                               help_text='海角社区的用户 ID（注册 / 登录接口返回），全局唯一')
    username = models.CharField('用户名', max_length=64, db_index=True)
    password = EncryptedSecretField('密码', max_length=200,
                                    help_text='落库 AES 加密存储（S-06）；接口不回传明文')
    email = models.CharField('邮箱', max_length=128, blank=True, db_index=True)
    nickname = models.CharField('昵称', max_length=64, blank=True)
    token = EncryptedSecretField('登录Token', max_length=500, blank=True,
                                 help_text='最近一次登录凭证，落库 AES 加密存储（S-06）')
    remark = models.CharField('备注', max_length=255, blank=True)
    last_sign_in_date = models.DateField('最近签到日期', null=True, blank=True,
                                         help_text='每日金币签到的本地记录：等于当天即视为今日已签到，'
                                                   '批量签到时直接跳过源站请求；跨天自动失效')

    class Meta:
        db_table = 'haijiao_account'
        verbose_name = '海角社区账号'
        verbose_name_plural = '海角社区账号'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.username} ({self.user_id})'
