"""AI 服务 · 厂商 / 模型 / 系统提示词注册表

AI 服务对外只暴露「一个对话端点 + 一个模型清单端点」，调用方通过请求参数 `model`
选择模型；厂商、上游地址、API Key、系统提示词、采样参数全部由这里的三张表驱动，因此：

    接入一个新模型  =  后台加一条记录（或一次性数据迁移）
    接入一个新厂商  =  后台加一条厂商记录 + 该厂商下的模型记录
    换提示词 / 调温度  =  后台改一条记录，不改代码、不重启

为什么三张表写在同一文件：`AiModel` 对 `AiProvider` 有外键、对 `AiSystemPrompt` 有外键，
三者属于《数据库模型创建规则》第三章判定的「直接外键关联 + 同一聚合根」。

为什么 API Key 存库而不是 .env：后台可自助维护、换 Key 不用改配置重启；为避免明文落盘，
`api_key` 走 `EncryptedSecretField`（AES-256-GCM，密钥由 SECRET_KEY 派生，见
API/common/credential_crypto.py），后台只展示 `key_hint` 掩码，永不回显原文。

注意：加密密钥派生自 SECRET_KEY —— **更换 SECRET_KEY 会导致已入库的 Key 全部无法解密**，
部署手册里必须提示备份 SECRET_KEY（与 APPSECRET 同一条约束）。

上游协议：当前接入的厂商（DeepSeek / 月之暗面 / 火山方舟 / 阿里云百炼）都提供
**OpenAI 兼容**的 `/chat/completions`，所以一套客户端即可覆盖；`base_url` 填到版本段为止
（如 `https://api.deepseek.com`、`https://api.moonshot.cn/v1`），本服务在其后拼
`/chat/completions`。
"""
import json
import re

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import EncryptedSecretField


class AiProvider(BaseModel):
    """AI 厂商 / 平台：一个厂商对应一个上游地址与一把平台 Key

    `code` 是对内的厂商标识（也用于日志与排错），**不对外暴露**（模型清单端点只返回
    模型自身信息），避免把「我们用的哪家上游」直接写给调用方。
    """

    code = models.SlugField('厂商标识', max_length=30, unique=True,
                            help_text='英文小写标识，如 deepseek / moonshot / ark / dashscope；仅内部使用')
    name = models.CharField('厂商名称', max_length=50,
                            help_text='后台与文档展示用，如「深度求索 DeepSeek」')
    base_url = models.CharField('上游根地址', max_length=200,
                                help_text='填到版本段为止（如 https://api.deepseek.com 或 '
                                          'https://api.moonshot.cn/v1），本服务会在其后拼 /chat/completions')
    api_key = EncryptedSecretField('API Key', max_length=255, blank=True,
                                   help_text='平台密钥；落库 AES 加密，页面只显示掩码')
    key_hint = models.CharField('Key 掩码', max_length=32, blank=True,
                                help_text='保存时依据 Key 自动生成（如 sk-…4fe2），仅供后台辨认')
    enabled = models.BooleanField('启用', default=True, help_text='关闭后该厂商下所有模型不可用')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'ai_provider'
        verbose_name = 'AI 厂商'
        verbose_name_plural = 'AI 厂商'
        ordering = ('sort', 'code')

    def __str__(self):
        return f'{self.name}（{self.code}）'

    @property
    def chat_url(self):
        """OpenAI 兼容的对话端点地址（base_url 去掉尾斜杠后拼 /chat/completions）"""
        return f'{(self.base_url or "").strip().rstrip("/")}/chat/completions'

    @property
    def has_key(self):
        """是否已配置平台 Key"""
        return bool((self.api_key or '').strip())

    @staticmethod
    def mask_key(plain):
        """由明文 Key 生成掩码：保留前 3 位与后 4 位，中间省略（便于辨认是哪把 Key）"""
        plain = (plain or '').strip()
        if not plain:
            return ''
        if len(plain) <= 8:
            return f'{plain[:2]}…'
        return f'{plain[:3]}…{plain[-4:]}'

    def set_api_key(self, plain):
        """设置平台 Key 并同步掩码（传空字符串表示清除）"""
        plain = (plain or '').strip()
        self.api_key = plain
        self.key_hint = self.mask_key(plain)


class AiSystemPrompt(BaseModel):
    """系统提示词（提示词库，超管在后台维护）

    只在服务端生效，**不出现在任何对外响应里**：调用方自带 `system_prompt` 时以调用方为准，
    没带时按模型的 `prompt_mode` 到这里取。

    `is_global` 即「全局共享」：全库只保留一条（后台勾选新的会自动取消旧的），
    所有 `prompt_mode='inherit'` 的模型都用它。停用的提示词视同不存在。
    """

    name = models.CharField('提示词名称', max_length=50, help_text='后台辨认用，如「通用助手」「严格 JSON 输出」')
    content = models.TextField('提示词正文', help_text='纯文本，作为 system 消息发给上游')
    is_global = models.BooleanField('全局共享', default=False,
                                    help_text='勾选后所有「跟随全局」的模型都用它；全局只保留一条')
    enabled = models.BooleanField('启用', default=True,
                                  help_text='停用后视同不存在：指定它的模型会回落到全局共享那条')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'ai_system_prompt'
        verbose_name = 'AI 系统提示词'
        verbose_name_plural = 'AI 系统提示词'
        ordering = ('sort', 'name')

    def __str__(self):
        return self.name


class AiModel(BaseModel):
    """AI 模型：挂在某个厂商下，是对外唯一暴露的「可选模型」

    `key` 即请求参数 `model` 的取值；`upstream_name` 是真正发给上游的模型名，两者分开
    便于「对外名不变、上游换版本」（如把 upstream_name 从 kimi-k2 改为 kimi-k2-0905）。

    系统提示词与采样参数都在这里配：**调用方不能自定义**（请求里传 temperature /
    max_tokens / stop 会被拒绝），需要调整时由超管在后台改这一条记录。
    """

    class PromptMode(models.TextChoices):
        """系统提示词的三态选择"""

        INHERIT = 'inherit', '跟随全局共享'
        NONE = 'none', '不使用系统提示词'
        CUSTOM = 'custom', '指定提示词'

    provider = models.ForeignKey(AiProvider, verbose_name='所属厂商',
                                 on_delete=models.CASCADE, related_name='models')
    key = models.SlugField('模型标识', max_length=60, unique=True,
                           help_text='对外唯一标识，也是请求参数 model 的取值；建议与上游模型名一致')
    upstream_name = models.CharField('上游模型名', max_length=100, blank=True,
                                     help_text='真正发给上游的模型名；留空则与「模型标识」相同')
    name = models.CharField('模型名称', max_length=50, help_text='后台与文档展示用')
    supports_vision = models.BooleanField('支持视觉（看图）', default=False,
                                          help_text='勾选后才允许请求携带 images；未勾选传图片会返回参数值非法')
    max_images = models.PositiveSmallIntegerField('最多图片数', default=2,
                                                  help_text='仅对支持视觉的模型生效；请求携带的 images 超过此数会返回参数值非法')
    context_window = models.IntegerField('上下文长度', null=True, blank=True,
                                         help_text='仅用于展示，可留空')
    prompt_mode = models.CharField('系统提示词', max_length=10,
                                   choices=PromptMode.choices, default=PromptMode.INHERIT,
                                   help_text='调用方自带 system_prompt 时以调用方为准，本项只在调用方没带时生效')
    system_prompt = models.ForeignKey(AiSystemPrompt, verbose_name='指定提示词',
                                      null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='bound_models',
                                      help_text='仅当系统提示词选择「指定提示词」时使用')
    temperature = models.FloatField('采样温度', null=True, blank=True,
                                    help_text='留空=不下发该参数，由上游默认值决定')
    max_tokens = models.IntegerField('最大回复长度', null=True, blank=True,
                                     help_text='单次回复的 token 上限；留空=不下发该参数')
    stop = models.CharField('停止词', max_length=255, blank=True,
                            help_text='JSON 数组（如 ["END","STOP"]）或纯文本（逗号/换行分隔）；留空=不下发')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前（文档下拉顺序）')
    enabled = models.BooleanField('上架', default=True, help_text='下架后不在模型清单与文档下拉中出现')
    is_default = models.BooleanField('默认模型', default=False,
                                     help_text='请求不传 model 时使用；全局应保持只有一个')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'ai_model'
        verbose_name = 'AI 模型'
        verbose_name_plural = 'AI 模型'
        ordering = ('sort', 'key')

    def __str__(self):
        return f'{self.name}（{self.key}）'

    @property
    def request_name(self):
        """发给上游的模型名（未单独配置时取模型标识）"""
        return (self.upstream_name or self.key or '').strip()

    @property
    def usable(self):
        """是否可用于调用（自身已上架、厂商已启用且配了 Key）"""
        return bool(self.enabled and self.provider.enabled and self.provider.has_key)


def parse_stop(raw):
    """把后台填的停止词解析成列表（无有效内容返回 None）

    兼容三种写法：JSON 数组（`["END","STOP"]`）、JSON 字符串（`"END"`）、
    纯文本（逗号 / 换行分隔）。解析不出列表时按纯文本整体拆词，不抛异常——
    这一项由超管在后台维护，容错比严格更有价值。
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        items = [str(s).strip() for s in parsed if str(s).strip()]
        return items or None
    if isinstance(parsed, str):
        return [parsed] if parsed.strip() else None
    parts = [s.strip() for s in re.split(r'[\n,，]', raw) if s.strip()]
    return parts or None
