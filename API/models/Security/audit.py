"""控制台操作日志（超管写操作的审计留痕）

**只记写操作**（POST / PUT / PATCH / DELETE）：控制台的读操作（打开页面、搜索、翻页）量级大且
没有审计价值，记下来只会把真正的改动淹没。

采集点是 `API/website/admin_auth.py` 的 `superadmin_required` 装饰器 —— 它是**所有**控制台视图的
唯一入口，从这里统一记，不会出现「新加了个页面忘了埋点」的漏记。记录什么：

    谁（operator）· 什么时候（create_time）· 对哪个功能（view_name）· 做了什么动作（action）
    · 操作对象（target）· 结果（status_code）· 从哪来（ip / user_agent）

`note` 是**可读说明**：视图用 `notify_success()` 提示成功时顺带挂上（与操作者看到的那句提示同一句
话），不挂就只有上面那些机械信息 —— 机制保证「每个写操作都在册」，说明是尽力而为地更好读。

为什么要冗余存 operator 用户名：审计的意义是「事后还能查」，而超管账号本身可能被改名或删除；
只存外键的话删号即失去追溯线索，故同时存用户名与主键、且**不做外键**。
"""
from django.db import models

from API.common.base import BaseModel


class ConsoleAuditLog(BaseModel):
    """一条控制台写操作记录"""

    operator = models.CharField(
        '操作者', max_length=64, blank=True, default='',
        help_text='超管用户名（冗余保存：账号改名 / 删除后仍可追溯）',
    )
    operator_id = models.BigIntegerField(
        '操作者ID', null=True, blank=True,
        help_text='Django 超管账号主键（不做外键，避免删号牵连审计记录）',
    )
    method = models.CharField('请求方法', max_length=8)
    path = models.CharField('请求路径', max_length=255)
    view_name = models.CharField(
        '功能', max_length=120, blank=True, default='',
        help_text='解析出的 URL name，如 console_services',
    )
    action = models.CharField(
        '动作', max_length=64, blank=True, default='',
        help_text='表单里的 action 字段，如 create / edit / delete',
    )
    target = models.CharField(
        '操作对象', max_length=120, blank=True, default='',
        help_text='表单里的 id 等目标标识',
    )
    note = models.CharField(
        '说明', max_length=255, blank=True, default='',
        help_text='视图给出的可读说明（与操作者看到的成功提示同一句）；未提供时为空',
    )
    status_code = models.PositiveSmallIntegerField('响应状态码', null=True, blank=True)
    ip = models.CharField('来源 IP', max_length=45, blank=True, default='')
    user_agent = models.CharField('User-Agent', max_length=255, blank=True, default='')

    class Meta:
        db_table = 'console_audit_log'
        verbose_name = '控制台操作日志'
        verbose_name_plural = '控制台操作日志'
        ordering = ('-create_time',)
        indexes = [models.Index(fields=['-create_time'], name='console_audit_time_idx')]

    def __str__(self):
        return f'{self.operator} {self.method} {self.path}'
