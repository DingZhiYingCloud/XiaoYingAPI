"""问题反馈中心 · 反馈页一次性登录票据

子项目把「用户已登录」这个事实传递给我们托管的反馈页，用的是**票据**而不是直接用
UAC Token —— 因为反馈页地址会出现在浏览器历史、Referer 与服务器访问日志里：

    1. 子项目前端拿用户的 UAC Token 调 `POST /api/feedback/ticket`（免签名，token 本身即凭证）
    2. 我们签发一张**一次性、5 分钟过期**的票据，返回给子项目前端
    3. 子项目把票据拼进反馈页地址：`/feedback/<app_id>/?ticket=xxx`（链接或 iframe src）
    4. 反馈页消费票据（标记已用）→ 建立站点会话 → 303 重定向到不带票据的干净地址

好处：UAC Token 不落 URL / 历史 / 日志；票据用完即废、过期即废，即便被记录也无法重放。
票据本身不落库明文之外的额外保护也不必要——它 5 分钟过期且只能用一次。
"""
import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

from API.common.base import BaseModel
from API.models.Projects.app import UserApp
from API.models.Users.user import User

TICKET_TTL_SECONDS = 300
"""票据有效期（秒）：够子项目把地址交给浏览器，又不至于长期可用"""

TICKET_CLEAN_KEEP_SECONDS = 86400
"""过期票据的保留时长（秒）：签发新票据时顺手清理更早的过期记录，避免表无限增长"""


class FeedbackTicket(BaseModel):
    """反馈页一次性登录票据（见模块顶部流程说明）"""

    id = models.UUIDField('票据ID', primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField('票据', max_length=64, unique=True, db_index=True)
    app = models.ForeignKey(
        UserApp, on_delete=models.CASCADE, related_name='feedback_tickets', verbose_name='所属项目',
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='feedback_tickets', verbose_name='对应用户',
    )
    expire_time = models.DateTimeField('过期时间', db_index=True)
    used = models.BooleanField('已使用', default=False, help_text='消费后置位；票据只能用一次')
    used_time = models.DateTimeField('使用时间', null=True, blank=True)
    ip = models.CharField('签发IP', max_length=45, blank=True)

    class Meta:
        db_table = 'feedback_ticket'
        verbose_name = '反馈页票据'
        verbose_name_plural = '反馈页票据'
        ordering = ['-create_time']

    def __str__(self):
        return f'{self.app.app_id} - {self.user_id} ({self.token[:8]}…)'

    @property
    def is_valid(self) -> bool:
        """未使用且未过期"""
        return not self.used and timezone.now() < self.expire_time

    @classmethod
    def issue(cls, app, user, ip: str = '') -> 'FeedbackTicket':
        """签发一张新票据（顺手清理久远的过期记录）"""
        cls.objects.filter(
            expire_time__lt=timezone.now() - timedelta(seconds=TICKET_CLEAN_KEEP_SECONDS)
        ).delete()
        return cls.objects.create(
            token=secrets.token_urlsafe(32),
            app=app,
            user=user,
            expire_time=timezone.now() + timedelta(seconds=TICKET_TTL_SECONDS),
            ip=ip or '',
        )

    def consume(self) -> bool:
        """消费票据并返回**是否抢到**（原子操作）

        用条件更新（`WHERE used=False AND expire_time>now`）一次性完成「校验 + 标记已用」，
        而不是先读 `is_valid` 再写 —— 后者是「读-改-写」，并发下多个请求会同时读到
        `used=False`，同一张票据就能建立多个会话，破坏「一次性」这条安全属性。
        """
        claimed = type(self).objects.filter(
            pk=self.pk, used=False, expire_time__gt=timezone.now(),
        ).update(used=True, used_time=timezone.now(), updated_time=timezone.now())
        if not claimed:
            return False
        self.used = True
        self.used_time = timezone.now()
        return True
