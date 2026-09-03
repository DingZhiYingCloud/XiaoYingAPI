"""通用邮件模板模型

用于后台自定义各类验证/通知邮件的 HTML 内容，按 type 区分用途：
    email_verify - 邮箱验证邮件（支持变量: {{username}} {{code}} {{link}} {{expire_minutes}}）

模板记录不存在时，代码内置默认高级 HTML 模板兜底；在后台创建/编辑记录后即覆盖默认。
"""
from django.db import models

from API.common.base import BaseModel


class EmailTemplate(BaseModel):
    """邮件模板（标题 + HTML 正文，后台可编辑）"""
    type = models.CharField('模板类型', max_length=50, unique=True,
                            help_text='用途标识，如 email_verify 邮箱验证')
    subject = models.CharField('邮件标题', max_length=200,
                               help_text='邮件主题，可含变量，如 {{username}}')
    html_body = models.TextField('HTML正文',
                                 help_text='支持变量: {{username}} {{code}} {{link}} {{expire_minutes}}')
    description = models.CharField('说明', max_length=255, blank=True, default='',
                                   help_text='模板用途说明，便于后台识别')

    class Meta:
        db_table = 'email_template'
        verbose_name = '邮件模板'
        verbose_name_plural = '邮件模板'
        ordering = ['type']

    def __str__(self):
        return f'{self.type} - {self.subject}'
