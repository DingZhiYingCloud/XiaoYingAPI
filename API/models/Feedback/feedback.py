"""问题反馈中心 · 反馈主表 / 类型 / 回复 / 附件 / 审核留痕

统一问题反馈调度中心：所有接入项目（UserApp）共用这一套反馈能力，数据按项目隔离
（见《API 开发规范》与 README 的「问题反馈中心」章节）。子项目**零代码接入**——
在页面上放一个指向 `/feedback/<app_id>/` 的链接或 iframe 即可。

聚合关系（判定依据见《数据库模型创建规则》第三章「同文件聚合」）：

    FeedbackType ──< Feedback ──< FeedbackReply ──< FeedbackReplyAttachment
                            ├──< FeedbackAttachment
                            └──< FeedbackAuditLog

`FeedbackType` 是被 `Feedback` 直接外键引用的类型字典；附件、回复、审核留痕离开反馈
都无意义，故这六张表同写本文件。

状态口径（两个维度分开存储，后台可分别筛选，互不覆盖）：

    status    —— 业务状态：待审核 →（AI 通过）待处理 →（管理员回复）已回复
                 另有终态：AI驳回 / 已关闭
    ai_status —— AI 审核状态：未开启审核 / 待审核 / 审核中 / 审核通过 / 审核驳回 / 审核失败

两者的联动规则（由 `API/apis/feedback/ai.py` 与提交入口共同维护）：

    - 后台关闭 AI 审核，或平台尚未配置可用 AI 模型 → 提交即 `ai_status=skipped`、`status=processing`
    - 开启审核 → 提交时 `ai_status=pending`、`status=pending`（等后台审核线程慢慢审）
    - 审核通过 → `ai_status=passed`、`status=processing`
    - 审核驳回 → `ai_status=rejected`、`status=rejected`，并把驳回正文落成一条
      `author_role='ai'` 的回复（可带 AI 生成的「驳回说明图」）
    - 审核调用失败 → `ai_status=failed`、`status` 保持 `pending`，后台可见并可手动重新送审

游客与登录用户：`user` 为空即游客（匿名）提交。公开区只展示**游客提交且已通过审核**
的反馈，登录用户提交的内容不进公开区。
"""
import uuid

from django.conf import settings
from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import UserApp
from API.models.Users.user import User


class FeedbackType(BaseModel):
    """反馈类型字典（全局一套，超管在后台维护）

    预置：功能建议 / 功能升级 / 使用问题 / BUG 反馈 / 其他。用户提交时必选其一；
    「其他」即需求里说的「不知道什么类型的通用类型」。
    类型被删除后，历史反馈的类型字段置空并展示为「未分类」，数据不丢。
    """

    code = models.SlugField('类型标识', max_length=30, unique=True,
                            help_text='英文小写标识，如 suggestion / upgrade / issue / bug / other；仅内部使用')
    name = models.CharField('类型名称', max_length=30, help_text='提交页与后台展示用，如「功能建议」')
    desc = models.CharField('类型说明', max_length=100, blank=True,
                            help_text='提交页类型选项下的一句话说明，可留空')
    icon = models.CharField('图标', max_length=30, blank=True,
                            help_text='lucide 图标名（如 lightbulb / bug），留空则只显示文字')
    is_default = models.BooleanField('默认选中', default=False,
                                     help_text='提交页打开时默认选中的类型；全局只应保留一个')
    enabled = models.BooleanField('启用', default=True, help_text='停用后不在提交页出现，历史反馈不受影响')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前（提交页选项顺序）')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'feedback_type'
        verbose_name = '反馈类型'
        verbose_name_plural = '反馈类型'
        ordering = ('sort', 'code')

    def __str__(self):
        return self.name


class Feedback(BaseModel):
    """反馈主表：一条反馈 = 一个问题"""

    class Status(models.TextChoices):
        """业务状态"""
        PENDING = 'pending', '待审核'
        PROCESSING = 'processing', '待处理'
        REPLIED = 'replied', '已回复'
        REJECTED = 'rejected', 'AI驳回'
        CLOSED = 'closed', '已关闭'

    class AiStatus(models.TextChoices):
        """AI 审核状态"""
        SKIPPED = 'skipped', '未开启审核'
        PENDING = 'pending', '待审核'
        RUNNING = 'running', '审核中'
        PASSED = 'passed', '审核通过'
        REJECTED = 'rejected', '审核驳回'
        FAILED = 'failed', '审核失败'

    # 公开区可见的业务状态（待审核 / AI驳回 都不进公开区，避免违规内容先被公开出去）
    PUBLIC_STATUSES = (Status.PROCESSING, Status.REPLIED, Status.CLOSED)

    TITLE_LEN = 60
    """列表标题的最大长度：不单独让用户填标题，取正文折叠空白后截断"""

    id = models.UUIDField('反馈ID', primary_key=True, default=uuid.uuid4, editable=False)
    app = models.ForeignKey(
        UserApp, on_delete=models.CASCADE, related_name='feedbacks', verbose_name='所属项目',
        help_text='租户维度：反馈数据按项目隔离，子项目之间互不可见',
    )
    type = models.ForeignKey(
        FeedbackType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='feedbacks', verbose_name='反馈类型',
        help_text='用户提交时选择的类型；类型被删除后历史反馈展示为「未分类」',
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='feedbacks', verbose_name='提交用户',
        help_text='登录用户提交时记录；游客（匿名）提交时为空',
    )
    contact_email = models.EmailField(
        '联系邮箱', blank=True,
        help_text='选填：游客或用户填了邮箱，管理员回复后会收到一封通知邮件',
    )
    content = models.TextField('反馈内容', help_text='用户填写的正文（纯文本）')

    status = models.CharField('业务状态', max_length=20, choices=Status.choices,
                              default=Status.PENDING, help_text='待审核 / 待处理 / 已回复 / AI驳回 / 已关闭')
    ai_status = models.CharField('AI 审核状态', max_length=20, choices=AiStatus.choices,
                                 default=AiStatus.SKIPPED,
                                 help_text='未开启审核 / 待审核 / 审核中 / 审核通过 / 审核驳回 / 审核失败')
    ai_checked_time = models.DateTimeField('AI 审核时间', null=True, blank=True)
    ai_model_key = models.CharField('审核模型', max_length=60, blank=True,
                                    help_text='本条用的审核模型标识（留痕，模型可能被改名或删除）')

    public_hidden = models.BooleanField(
        '公开区隐藏', default=False,
        help_text='勾选后本条从公开区撤下（仅对游客提交的反馈有意义）',
    )
    admin_unread = models.BooleanField(
        '有新回复', default=False,
        help_text='用户或游客跟帖后置位，管理员查看详情即清除',
    )
    last_reply_time = models.DateTimeField('最后回复时间', null=True, blank=True,
                                           help_text='列表排序与「有新回复」提示用')

    ip = models.CharField('提交IP', max_length=45, blank=True, help_text='防滥用留痕')
    user_agent = models.CharField('提交UA', max_length=255, blank=True, help_text='防滥用留痕')

    class Meta:
        db_table = 'feedback'
        verbose_name = '反馈'
        verbose_name_plural = '反馈'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['app', 'status'], name='idx_fb_app_status'),
            models.Index(fields=['app', 'create_time'], name='idx_fb_app_time'),
            # 审核线程的取任务队列：按 ai_status 过滤、按提交时间先进先出
            models.Index(fields=['ai_status', 'create_time'], name='idx_fb_ai_queue'),
        ]

    def __str__(self):
        return f'{self.app.name} - {self.display_title}（{self.get_status_display()}）'

    @property
    def display_title(self) -> str:
        """列表标题：正文折叠空白后截断（用户不填标题，降低提交门槛）"""
        text = ' '.join((self.content or '').split())
        return text if len(text) <= self.TITLE_LEN else text[:self.TITLE_LEN] + '…'

    @property
    def is_guest(self) -> bool:
        """是否游客（匿名）提交"""
        return self.user_id is None

    @property
    def submitter_name(self) -> str:
        """提交者展示名（游客不显示任何身份信息）"""
        if self.user_id is None:
            return '匿名用户'
        return self.user.username or self.user.account

    @property
    def type_name(self) -> str:
        """类型展示名（类型被删除后为「未分类」）"""
        return self.type.name if self.type_id else '未分类'

    @property
    def in_public_area(self) -> bool:
        """本条是否出现在公开区（与 `public_queryset()` 口径保持一致）"""
        return self.is_guest and not self.public_hidden and self.status in self.PUBLIC_STATUSES

    @classmethod
    def public_queryset(cls):
        """公开区可见的反馈：游客提交 + 已过 AI 审核 + 未被管理员隐藏"""
        return cls.objects.filter(
            user__isnull=True, public_hidden=False, status__in=cls.PUBLIC_STATUSES,
        )

    @classmethod
    def pending_ai_queryset(cls):
        """待 AI 审核的队列（后台审核线程按提交时间先进先出取一条）"""
        return cls.objects.filter(ai_status=cls.AiStatus.PENDING).order_by('create_time')


class FeedbackReply(BaseModel):
    """反馈回复：登录用户跟帖 / 管理员回复 / AI 审核结论

    三类作者共用一张表，靠 `author_role` 区分：
    - `user`  —— 登录用户跟帖（**游客不支持跟帖**：没有身份无法确认本人）
    - `admin` —— 管理员在后台回复
    - `ai`    —— AI 审核驳回时自动落一条，正文是驳回理由，附件是 AI 生成的「驳回说明图」
    """

    class AuthorRole(models.TextChoices):
        USER = 'user', '用户'
        ADMIN = 'admin', '管理员'
        AI = 'ai', 'AI 审核'

    id = models.UUIDField('回复ID', primary_key=True, default=uuid.uuid4, editable=False)
    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name='replies', verbose_name='所属反馈',
        help_text='回复归属于某条反馈；删除反馈会级联删除其全部回复',
    )
    author_role = models.CharField('身份类型', max_length=10, choices=AuthorRole.choices,
                                   default=AuthorRole.USER, help_text='user=用户跟帖 / admin=管理员 / ai=AI 审核')
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='feedback_replies', verbose_name='跟帖用户',
        help_text='用户跟帖时记录；管理员与 AI 回复时为空',
    )
    admin_name = models.CharField('管理员账号', max_length=150, blank=True,
                                  help_text='超管回复时记录其登录账号，仅内部留痕、不对外展示')
    content = models.TextField('内容', help_text='回复正文（纯文本）')

    class Meta:
        db_table = 'feedback_reply'
        verbose_name = '反馈回复'
        verbose_name_plural = '反馈回复'
        ordering = ['create_time']
        indexes = [
            models.Index(fields=['feedback', 'create_time'], name='idx_freply_fb_time'),
        ]

    def __str__(self):
        return f'{self.feedback_id} - {self.get_author_role_display()}: {self.content[:20]}'

    @property
    def author_name(self) -> str:
        """作者展示名（对外：管理员统一显示为「官方回复」，AI 显示为「AI 审核」）"""
        if self.author_role == self.AuthorRole.ADMIN:
            return '官方回复'
        if self.author_role == self.AuthorRole.AI:
            return 'AI 审核'
        return self.user.username if self.user_id and self.user.username else '用户'


class AttachmentBase(BaseModel):
    """附件公共字段（抽象基类，不建表）

    图片与视频共用一套字段，靠 `kind` 区分；`path` 存**相对 MEDIA_ROOT 的路径**，
    对外地址由 `url` 属性拼出（与文件上传服务返回的 `/media/...` 口径一致）。
    """

    class Kind(models.TextChoices):
        IMAGE = 'image', '图片'
        VIDEO = 'video', '视频'

    id = models.UUIDField('附件ID', primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField('类型', max_length=10, choices=Kind.choices, default=Kind.IMAGE)
    path = models.CharField('文件路径', max_length=255,
                            help_text='相对 MEDIA_ROOT 的路径，如 uploads/feedback/20260930/xxx.png')
    original_name = models.CharField('原始文件名', max_length=150, blank=True)
    size = models.PositiveBigIntegerField('文件大小(字节)', default=0)
    ext = models.CharField('扩展名', max_length=10, blank=True, help_text='小写，不含点')
    sort = models.IntegerField('排序', default=0)

    class Meta:
        abstract = True
        ordering = ('sort', 'create_time')

    def __str__(self):
        return f'{self.get_kind_display()} {self.original_name or self.path}'

    @property
    def url(self) -> str:
        """对外可访问地址（站内相对路径，如 /media/uploads/feedback/...）"""
        return f'{settings.MEDIA_URL}{self.path}'

    @property
    def is_image(self) -> bool:
        return self.kind == self.Kind.IMAGE


class FeedbackAttachment(AttachmentBase):
    """反馈提交时携带的附件（图片 / 视频）"""

    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name='attachments', verbose_name='所属反馈',
    )

    class Meta(AttachmentBase.Meta):
        db_table = 'feedback_attachment'
        verbose_name = '反馈附件'
        verbose_name_plural = '反馈附件'


class FeedbackReplyAttachment(AttachmentBase):
    """回复携带的附件（管理员回复的配图/视频、AI 驳回说明图）"""

    reply = models.ForeignKey(
        FeedbackReply, on_delete=models.CASCADE, related_name='attachments', verbose_name='所属回复',
    )

    class Meta(AttachmentBase.Meta):
        db_table = 'feedback_reply_attachment'
        verbose_name = '反馈回复附件'
        verbose_name_plural = '反馈回复附件'


class FeedbackAuditLog(BaseModel):
    """AI 审核留痕（内部审计用，不在前台展示）

    两类场景共用：
    - `submit`：提交内容审核 —— 记录 AI 判定的通过 / 驳回与理由
    - `reply` ：管理员回复的语气审查 —— AI 有意见时留痕，管理员强制发送则置 `forced=True`

    保留这张表而不是只看反馈主表：主表的 `ai_status` 只存最新一次结论，
    而「AI 提醒过但管理员仍然发送」这类过程需要可追溯。
    """

    class Kind(models.TextChoices):
        SUBMIT = 'submit', '提交内容审核'
        REPLY = 'reply', '回复语气审查'

    class Verdict(models.TextChoices):
        PASS = 'pass', '通过'
        REJECT = 'reject', '驳回'
        WARN = 'warn', '仅提醒'
        ERROR = 'error', '调用失败'

    id = models.UUIDField('记录ID', primary_key=True, default=uuid.uuid4, editable=False)
    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name='audit_logs', verbose_name='所属反馈',
    )
    reply = models.ForeignKey(
        FeedbackReply, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs', verbose_name='关联回复',
        help_text='回复语气审查时指向被审查的那条回复；提交内容审核时为空',
    )
    kind = models.CharField('审核场景', max_length=10, choices=Kind.choices, default=Kind.SUBMIT)
    verdict = models.CharField('结论', max_length=10, choices=Verdict.choices)
    model_key = models.CharField('审核模型', max_length=60, blank=True)
    reason = models.TextField('AI 意见', blank=True, help_text='AI 给出的理由要点原文')
    forced = models.BooleanField('管理员强制发送', default=False,
                                 help_text='仅「回复语气审查」且 AI 有意见时可能为真')
    operator = models.CharField('操作人', max_length=150, blank=True, help_text='管理员账号；提交审核时为空')

    class Meta:
        db_table = 'feedback_audit_log'
        verbose_name = '反馈审核留痕'
        verbose_name_plural = '反馈审核留痕'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.get_kind_display()} - {self.get_verdict_display()}'
