"""问题反馈中心数据模型

多租户问题反馈：每个接入项目（UserApp）一个租户，反馈数据按项目隔离，
子项目之间的反馈互不可见；同一子项目内所有用户可见（类似 GitHub Issues）。

    Feedback      - 反馈主表（一条反馈 = 一个问题）
    FeedbackReply - 追加评论（支持无限嵌套的评论树：parent 为空=一级评论，
                    非空=回复某条评论；同级按时间平铺，全部人可见）

字段说明:
    Feedback:
        id      - 反馈唯一ID（UUID 主键）
        app     - 关联接入项目 UserApp（租户维度，数据隔离依据）
        user    - 反馈提交者（UAC 用户，提交时经 Token 校验真实性）
        title   - 反馈标题（简短描述问题）
        content - 反馈详情（纯文本）
        status  - 处理状态（pending=待处理 / processing=处理中 / resolved=已解决 / closed=已关闭）

    FeedbackReply:
        id          - 追加唯一ID（UUID 主键）
        feedback    - 关联反馈（外键，追加归属于某条反馈）
        parent      - 父评论（自引用外键，可空）：空=一级评论；非空=回复某条评论，
                      支持任意深度嵌套；删除父评论会级联删除其全部子孙回复
        user        - 追加者（子项目用户，可空：站长回复时为空）
        author_role - 身份类型（user=子项目用户 / admin=站长）
        content     - 追加内容（纯文本）
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import UserApp
from API.models.Users.user import User


class Feedback(BaseModel):
    """问题反馈主表"""

    # 处理状态
    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('processing', '处理中'),
        ('resolved', '已解决'),
        ('closed', '已关闭'),
    ]

    id = models.UUIDField('反馈ID', primary_key=True, default=uuid.uuid4, editable=False)
    app = models.ForeignKey(
        UserApp,
        on_delete=models.CASCADE,
        related_name='feedbacks',
        verbose_name='所属项目',
        help_text='租户维度：反馈数据按项目隔离，子项目之间互不可见',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='feedbacks',
        verbose_name='反馈用户',
        help_text='反馈提交者（UAC 用户，提交时经 Token 校验真实性）',
    )
    title = models.CharField('标题', max_length=100, help_text='问题标题，简短描述')
    content = models.TextField('内容', help_text='问题详情（纯文本）')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending',
                              db_index=True, help_text='待处理/处理中/已解决/已关闭')

    class Meta:
        db_table = 'feedback'
        verbose_name = '问题反馈'
        verbose_name_plural = '问题反馈'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['app', 'status'], name='idx_feedback_app_status'),
            models.Index(fields=['app', 'create_time'], name='idx_feedback_app_time'),
        ]

    def __str__(self):
        return f'{self.app} - {self.title[:20]} ({self.get_status_display()})'

    @property
    def reply_count(self) -> int:
        """追加数量（含站长回复），供列表展示"""
        return self.replies.count()


class FeedbackReply(BaseModel):
    """反馈追加（一层评论流：同一反馈下全部人可见）"""

    # 身份类型：区分追加来源（子项目用户 / 站长）
    AUTHOR_ROLE_CHOICES = [
        ('user', '子项目用户'),
        ('admin', '站长'),
    ]

    id = models.UUIDField('追加ID', primary_key=True, default=uuid.uuid4, editable=False)
    feedback = models.ForeignKey(
        Feedback,
        on_delete=models.CASCADE,
        related_name='replies',
        verbose_name='所属反馈',
        help_text='追加归属于某条反馈',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父评论',
        help_text='为空=一级评论；非空=回复某条评论（支持任意深度嵌套，删除父评论级联删除子孙）',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='feedback_replies',
        verbose_name='追加用户',
        help_text='子项目用户追加者；站长回复时为空',
    )
    author_role = models.CharField('身份类型', max_length=10, choices=AUTHOR_ROLE_CHOICES,
                                   default='user', help_text='user=子项目用户 / admin=站长')
    content = models.TextField('内容', help_text='追加内容（纯文本）')

    class Meta:
        db_table = 'feedback_reply'
        verbose_name = '反馈追加'
        verbose_name_plural = '反馈追加'
        ordering = ['create_time']
        indexes = [
            models.Index(fields=['parent'], name='idx_freply_parent'),
        ]

    def __str__(self):
        return f'{self.feedback_id} - {self.get_author_role_display()}: {self.content[:20]}'
