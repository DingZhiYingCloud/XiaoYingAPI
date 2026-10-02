"""支付渠道配置

一个渠道一行，对应 `API/apis/pay/providers/` 里的一个 provider 实现：

    code                - 渠道标识（与 provider 注册表 key 一一对应，如 ezfp）
    name                - 后台展示名（如「易支付」）
    enabled             - 是否启用（关闭后不出现在下单可选渠道里）
    merchant_id         - 商户ID（易支付即 pid），参与签名
    private_key_enc     - 商户私钥（**密文**，AES-256-GCM，页面不回显）
    platform_public_key_enc - 平台公钥（**密文**，用于校验平台返回与异步通知的签名）
    gateway             - 网关地址（留空用 provider 的默认地址，便于切测试环境）
    enabled_methods     - 允许的支付方式（逗号分隔，如 alipay,wxpay；留空 = 该渠道全部可用）
    sort / remark       - 排序 / 备注

密钥为什么落库而不是放 .env：与 AI 厂商 Key 同一套方案（`API/common/credential_crypto.py`
的 AES-256-GCM，密钥由 SECRET_KEY 派生）。好处是后台可维护、多渠道各自一份、仓库里
不出现任何私钥；代价是 SECRET_KEY 不可变更（变更即密文无法解密，需重新填写）。
"""
from django.db import models

from API.common.base import BaseModel
from API.common.credential_crypto import decrypt_credential, encrypt_credential


class PayProvider(BaseModel):
    """支付渠道配置（一渠道一行）"""

    code = models.CharField('渠道标识', max_length=32, unique=True,
                            help_text='与 providers 注册表 key 一致，如 ezfp')
    name = models.CharField('渠道名称', max_length=64,
                            help_text='后台展示名，如「易支付」')
    enabled = models.BooleanField('启用', default=False, db_index=True)

    merchant_id = models.CharField('商户ID', max_length=64, blank=True, default='',
                                   help_text='易支付即 pid；参与签名，务必与商户后台一致')
    private_key_enc = models.TextField('商户私钥（密文）', blank=True, default='',
                                       help_text='后台填写明文，入库自动加密；页面不回显，留空表示不修改')
    platform_public_key_enc = models.TextField('平台公钥（密文）', blank=True, default='',
                                               help_text='用于校验平台返回与异步通知签名；同样加密落库')

    gateway = models.CharField('网关地址', max_length=200, blank=True, default='',
                               help_text='留空使用内置默认地址（如 https://www.ezfp.cn），便于切换测试环境')
    enabled_methods = models.CharField('允许的支付方式', max_length=200, blank=True, default='',
                                       help_text='逗号分隔，如 alipay,wxpay；留空表示该渠道全部支付方式可用')
    sort = models.PositiveIntegerField('排序', default=0, help_text='数字越小越靠前')
    remark = models.CharField('备注', max_length=200, blank=True, default='')

    class Meta:
        db_table = 'pay_provider'
        verbose_name = '支付渠道'
        verbose_name_plural = '支付渠道'
        ordering = ('sort', 'code')

    def __str__(self):
        return f'{self.name}（{self.code}，{"启用" if self.enabled else "停用"}）'

    # ---------- 密文读写（明文只在这里进出，页面与日志都不碰） ----------

    def set_private_key(self, plaintext: str):
        """写入商户私钥（明文 → 密文）；传空串表示清空"""
        self.private_key_enc = encrypt_credential(plaintext.strip()) if plaintext and plaintext.strip() else ''

    def set_platform_public_key(self, plaintext: str):
        """写入平台公钥（明文 → 密文）；传空串表示清空"""
        self.platform_public_key_enc = (
            encrypt_credential(plaintext.strip()) if plaintext and plaintext.strip() else ''
        )

    @property
    def private_key(self) -> str:
        """商户私钥明文（仅签名时在内存里用）"""
        return decrypt_credential(self.private_key_enc) if self.private_key_enc else ''

    @property
    def platform_public_key(self) -> str:
        """平台公钥明文（仅验签时在内存里用）"""
        return decrypt_credential(self.platform_public_key_enc) if self.platform_public_key_enc else ''

    @property
    def method_list(self) -> list:
        """允许的支付方式列表（空 = 不限制）"""
        return [m.strip() for m in (self.enabled_methods or '').split(',') if m.strip()]

    def method_allowed(self, pay_type: str) -> bool:
        allowed = self.method_list
        return not allowed or pay_type in allowed
