"""消息推送设置（单例）

全库只有一行，存「消息推送服务」各线路的运行配置 —— 与 `OrderMigrationSetting` /
`QuotaSetting` / `SecuritySetting` 同一惯例：每个功能单独建表、字段即配置项，单行表读写直观。

当前只有 QQBot 线路（NapCat / OneBot 11 HTTP）需要配置，故先放三项：
HTTP 服务端地址、访问 token、发送超时。token 属敏感凭据，落库 AES 加密（S8 整改口径）。
"""
import secrets

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import EncryptedSecretField

# QQBot（NapCat）HTTP 服务端默认地址（仅作帮助文案示例，不参与取值）
QQBOT_DEFAULT_BASE = 'http://127.0.0.1:3000'
# 上游请求默认超时（秒）
DEFAULT_TIMEOUT = 15


def default_hook_secret() -> str:
    """事件回调密钥：随机生成，作为回调地址里的一段路径（新建时自动生成）"""
    return secrets.token_urlsafe(24)[:32]


class PushSetting(BaseModel):
    """消息推送设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    qqbot_api_base = models.CharField(
        'QQBot HTTP 地址', max_length=200, blank=True, default='',
        help_text=f'NapCat「网络配置」里 HTTP 服务端的地址，例如 {QQBOT_DEFAULT_BASE}；留空则该线路不可用')
    qqbot_token = EncryptedSecretField(
        'QQBot Token', max_length=500, blank=True,
        help_text='NapCat HTTP 服务端里配置的 token（请求头 Authorization: Bearer）；未配置 token 时留空')
    qqbot_timeout = models.PositiveSmallIntegerField(
        'QQBot 超时(秒)', default=DEFAULT_TIMEOUT,
        help_text='调用 NapCat HTTP 接口的超时时间，最小 1 秒')

    # ==================== QQBot 一键部署（NapCat）====================
    napcat_qq = models.CharField(
        '机器人 QQ 号', max_length=20, blank=True, default='',
        help_text='NapCat 要登录的 QQ 号（OneBot 的 self_id）；一键启动时用它快速登录（首次仍需扫码）')
    napcat_dir = models.CharField(
        'NapCat 安装目录', max_length=300, blank=True, default='',
        help_text='NapCat 的安装位置；留空则用项目下的 napcat/ 目录')
    deploy_state = models.CharField(
        '部署状态', max_length=16, blank=True, default='idle',
        help_text='idle 空闲 / running 进行中 / success 成功 / failed 失败（一键部署流水线的状态）')
    deploy_time = models.DateTimeField('部署时间', null=True, blank=True)
    deploy_logs = models.TextField(
        '部署日志', blank=True, default='',
        help_text='最近一次一键部署的日志（JSON 文本），供后台页实时/回看展示')

    # ==================== 事件上报（实时接收好友消息）====================
    hook_secret = models.CharField(
        '事件回调密钥', max_length=64, blank=True, default=default_hook_secret,
        help_text='回调地址 /hook/qqbot/<密钥>/ 里的一段随机串，防伪造；新建时自动生成')
    hook_base = models.CharField(
        '事件回调基址', max_length=200, blank=True, default='',
        help_text='NapCat 把事件 POST 回来的站点基址，如 https://api.example.com；'
                  '留空则点「一键启动」时自动取当前访问本页的域名')

    # ==================== AI 自动回复（好友私聊）====================
    # 人格键与提示词的对应关系在 API/apis/push/qqbot/ai_reply.py（提示词是给模型看的，不翻译）；
    # 这里只放键与后台下拉要显示的名字，两边靠同一个 TextChoices 保持不脱节。
    class Persona(models.TextChoices):
        SARCASTIC = 'sarcastic', '尖酸刻薄'
        GENTLE = 'gentle', '温柔善良聪明可爱'
        HUMOROUS = 'humorous', '幽默搞笑'

    ai_reply_enabled = models.BooleanField(
        'AI 自动回复', default=False,
        help_text='打开后，好友私聊消息会交给 AI 判断并自动回复；关闭则完全不影响现有功能')
    ai_persona = models.CharField(
        'AI 人格', max_length=16, choices=Persona.choices, default=Persona.GENTLE,
        help_text='自动回复使用的人格风格（三种内置人设，提示词在代码里维护）')

    class Meta:
        db_table = 'push_setting'
        verbose_name = '消息推送设置'
        verbose_name_plural = '消息推送设置'

    def __str__(self):
        return f'消息推送设置（QQBot：{self.qqbot_api_base or "未配置"}）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'PushSetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    def hook_callback_url(self) -> str:
        """好友消息事件回调地址；基址为空（尚未确定）时返回空串

        NapCat 的 HTTP 客户端会把 `message` 事件 POST 到这个地址，由
        `API/apis/push/qqbot/hook.py` 落库后再实时推给后台页。
        """
        base = (self.hook_base or '').strip().rstrip('/')
        if not base or not self.hook_secret:
            return ''
        return f'{base}/hook/qqbot/{self.hook_secret}/'
