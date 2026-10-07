"""消息推送记录模型

记录每一次「消息推送服务」的推送尝试与结果，供控制台「推送日志」页查看与排错：
    成功（ok=True，上游 code=0） / 失败（ok=False，含上游拒绝与网络异常）

设计意图：
    - 推送是**真实外部写操作**，调用方与管理员都需要能回看「发了什么、成没成、为什么失败」；
    - SendKey 属敏感凭据，由控制台「账号管理」托管（platform=serverchan），**本表不存 SendKey**，
      也不存任何凭据，仅留消息内容与结果码，避免凭据随日志扩散。
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class PushLog(BaseModel):
    """一次消息推送的记录"""

    id = models.UUIDField('记录ID', primary_key=True, default=uuid.uuid4, editable=False)

    channel = models.CharField('推送渠道', max_length=32, default='serverchan', db_index=True,
                               help_text='线路标识（如 serverchan = Server酱）')
    app_id = models.CharField('调用项目', max_length=64, blank=True, db_index=True,
                              help_text='发起调用的接入项目 APPID（未认证时为空）')
    title = models.CharField('消息标题', max_length=255)
    content = models.TextField('消息正文', blank=True)
    recipients = models.CharField('收件人', max_length=1000, blank=True,
                                  help_text='邮件收件人（多个用逗号分隔）；Server酱 推送等无收件人的渠道为空')

    ok = models.BooleanField('是否成功', default=False, db_index=True,
                             help_text='上游返回 code=0 视为成功')
    code = models.IntegerField('上游返回码', null=True, blank=True,
                               help_text='上游接口返回的 code；网络异常等未取到时为空')
    message = models.CharField('结果说明', max_length=500, blank=True)
    pushid = models.CharField('推送ID', max_length=64, blank=True,
                              help_text='上游返回的 pushid（成功时用于在 Server酱 后台定位这条消息）')

    class Meta:
        db_table = 'push_log'
        verbose_name = '推送日志'
        verbose_name_plural = '推送日志'
        ordering = ['-create_time']

    def __str__(self):
        return f'[{self.channel}] {self.title} · {"成功" if self.ok else "失败"}'
