"""邮件定时推送任务（push/email_task 线路）

一条记录 = 一个「按固定间隔反复发邮件」或「只发一次」的任务。由后台常驻线程
（见 API/apis/push/email_task/utils.py 的 start_worker）扫描到期任务并发送；
多 worker 靠行级条件更新（CAS）抢占，保证同一任务同一时刻只发一次。

设计要点：
    - `interval_minutes=0` 表示「只发一次」；`>0` 表示每 N 分钟重复，直到被停用或删除
      （不设结束时间与次数上限，避免两处真相）。
    - `repeat` 由 `interval_minutes` 推导，不单独存库，避免与间隔漂移。
    - `next_run_at` 是调度游标：`next_run_at <= now` 即到期发送；发送后按
      「当前时间 + 间隔」推进 —— 停机跨多个周期也只补发一次，绝不一次性轰炸。
"""
import uuid

from django.db import models

from API.common.base import BaseModel


class EmailTask(BaseModel):
    """邮件定时推送任务"""

    id = models.UUIDField('任务ID', primary_key=True, default=uuid.uuid4, editable=False)

    app_id = models.CharField(
        '归属项目', max_length=64, blank=True, db_index=True,
        help_text='创建该任务的接入项目 APPID；任务按此隔离，调用方只能操作自己的任务',
    )
    recipients = models.CharField('收件人', max_length=1000,
                                  help_text='收件人邮箱，多个用逗号分隔')
    subject = models.CharField('邮件标题', max_length=255)
    body = models.TextField('邮件正文')

    interval_minutes = models.PositiveIntegerField(
        '发送间隔(分钟)', default=0,
        help_text='0=只发送一次；大于 0=每隔该分钟数重复发送，直到手动停用或删除',
    )
    enabled = models.BooleanField(
        '启用', default=True,
        help_text='停用后不再调度（任务与历史记录保留）',
    )

    next_run_at = models.DateTimeField(
        '下次发送时间', null=True, blank=True,
        help_text='调度游标：到期即发送；为空表示不再调度（一次性任务发送后置空）',
    )
    last_sent_at = models.DateTimeField('上次发送时间', null=True, blank=True)
    sent_count = models.PositiveIntegerField('累计发送次数', default=0)
    last_ok = models.BooleanField(
        '上次是否成功', null=True, blank=True,
        help_text='从未发送时为空；发送失败只记录、不自动重试',
    )
    last_message = models.CharField('上次结果说明', max_length=500, blank=True, default='')

    class Meta:
        db_table = 'push_email_task'
        verbose_name = '邮件定时任务'
        verbose_name_plural = '邮件定时任务'
        ordering = ['-create_time']
        # 调度查询固定为 enabled=True AND next_run_at<=now，故建组合索引（前缀即 enabled）
        indexes = [models.Index(fields=['enabled', 'next_run_at'], name='push_email_task_due_idx')]

    @property
    def repeat(self):
        """是否重复发送（由间隔推导，不单独存库）"""
        return self.interval_minutes > 0

    def __str__(self):
        mode = f'每 {self.interval_minutes} 分钟' if self.repeat else '仅一次'
        return f'{self.subject} → {self.recipients}（{mode}）'
