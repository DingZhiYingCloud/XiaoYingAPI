"""消息推送 push · 邮件定时推送线路 业务层

一条任务 = 一份「按间隔反复发 / 只发一次」的邮件计划（模型 `EmailTask`）。
本模块提供两类能力：

1. **CRUD**：创建 / 查询 / 列表 / 修改 / 删除 —— 均按 `app_id` 隔离，调用方只能操作自己的任务。
2. **调度**：常驻后台线程按固定间隔扫描到期任务并发送（`start_worker`，由 API/apps.py 拉起），
   多 worker 靠行级条件更新（CAS）抢占，保证同一任务同一时刻只发一次。

发信复用 `API.apis.push.email.utils.send_email`（每次发送落一条 PushLog）。
口径：
    - `interval_minutes=0` 只发一次；`>0` 每 N 分钟重复，直到停用或删除（无结束时间 / 次数上限）。
    - 停机跨多个周期后只**补发一次**（发送后按「当前时间 + 间隔」重排，绝不一次性轰炸）。
    - 发送失败**不重试**：只记录结果，重复任务等下一周期、一次性任务就此结束。
"""
import logging
import threading
import time
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.db.models import F
from django.utils import timezone

from API.apis.push.email.utils import send_email
from API.models import EmailTask

logger = logging.getLogger('api.push')

# 单个任务的收件人上限（防群发滥用）
MAX_RECIPIENTS = 20
# 发送间隔上限（分钟，一年）：过大的值会让 `now + timedelta(minutes=...)` 溢出
MAX_INTERVAL_MINUTES = 365 * 24 * 60
# 分页每页数量上限（《API开发规范》分页规范）
MAX_PAGE_SIZE = 100
# 调度线程轮询间隔（秒）：到点任务的发送精度即此值
WORKER_INTERVAL_SECONDS = 30
# 单轮最多处理的任务数，避免一次堆积过多时长时间占用线程
BATCH_SIZE = 200


def _fmt_dt(value):
    """时间字段统一输出为本地时区秒级字符串；空值输出 None"""
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M:%S') if value else None


def serialize(task):
    """任务对外 JSON 结构"""
    return {
        'id': str(task.id),
        'recipients': [r for r in (task.recipients or '').split(',') if r],
        'subject': task.subject,
        'body': task.body,
        'repeat': task.repeat,
        'interval_minutes': task.interval_minutes,
        'enabled': task.enabled,
        'next_run_at': _fmt_dt(task.next_run_at),
        'last_sent_at': _fmt_dt(task.last_sent_at),
        'sent_count': task.sent_count,
        'last_ok': task.last_ok,
        'last_message': task.last_message,
        'create_time': _fmt_dt(task.create_time),
        'updated_time': _fmt_dt(task.updated_time),
    }


# ==================== CRUD ====================

def create_task(app_id, recipients, subject, body, interval_minutes, first_send_at=None):
    """新建任务

    :param first_send_at: 首次发送时间；为空表示创建后立即进入调度（下一个轮询周期即发）
    """
    return EmailTask.objects.create(
        app_id=app_id or '',
        recipients=','.join(recipients),
        subject=subject,
        body=body,
        interval_minutes=interval_minutes,
        enabled=True,
        next_run_at=first_send_at or timezone.now(),
    )


def get_task(app_id, task_id):
    """按 ID 取本项目的任务

    :return: (True, task) 或 (False, 原因)；task_id 非法 / 不属于本项目都视为不存在
    """
    try:
        task = EmailTask.objects.filter(pk=task_id, app_id=app_id or '').first()
    except (ValidationError, ValueError):
        return False, '任务不存在'
    if task is None:
        return False, '任务不存在'
    return True, task


def list_tasks(app_id, page=1, page_size=20, enabled=None):
    """分页列出本项目的任务（enabled 为 None 时不筛选）"""
    qs = EmailTask.objects.filter(app_id=app_id or '')
    if enabled is not None:
        qs = qs.filter(enabled=enabled)
    total = qs.count()
    offset = (page - 1) * page_size
    items = [serialize(t) for t in qs[offset:offset + page_size]]
    return {
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'items': items,
    }


def update_task(task, *, recipients=None, subject=None, body=None,
                interval_minutes=None, enabled=None):
    """更新任务（只改显式传入的项）

    改间隔时按「当前时间」重排下一次发送，避免沿用旧节奏；重新启用一个已结束
    （`next_run_at` 为空）的一次性任务时，让它立即重新进入调度。
    """
    fields = []
    if recipients is not None:
        task.recipients = ','.join(recipients)
        fields.append('recipients')
    if subject is not None:
        task.subject = subject
        fields.append('subject')
    if body is not None:
        task.body = body
        fields.append('body')
    if interval_minutes is not None:
        task.interval_minutes = interval_minutes
        fields.append('interval_minutes')
        task.next_run_at = (timezone.now() + timedelta(minutes=interval_minutes)
                            if interval_minutes > 0 else timezone.now())
        fields.append('next_run_at')
    if enabled is not None:
        task.enabled = enabled
        fields.append('enabled')
        if enabled and task.next_run_at is None:
            task.next_run_at = timezone.now()
            fields.append('next_run_at')
    if fields:
        task.save(update_fields=list(dict.fromkeys(fields + ['updated_time'])))
    return task


def delete_tasks(app_id, task_ids):
    """删除本项目的指定任务，返回删除条数（ID 含非法值只跳过，不报错）"""
    try:
        deleted, _ = EmailTask.objects.filter(app_id=app_id or '', pk__in=task_ids).delete()
    except (ValidationError, ValueError):
        return 0
    return deleted


# ==================== 调度与发送 ====================

def run_due_tasks(limit=BATCH_SIZE):
    """扫描到期任务并逐条抢占发送，返回本次实际处理条数"""
    now = timezone.now()
    due = list(EmailTask.objects.filter(enabled=True, next_run_at__lte=now)
               .order_by('next_run_at')[:limit])
    processed = 0
    for task in due:
        try:
            if _claim_and_send(task, now):
                processed += 1
        except Exception:                       # noqa: BLE001 单条异常不应中断整轮
            logger.exception('邮件定时任务处理异常 [%s]', task.pk)
    return processed


def _claim_and_send(task, now):
    """CAS 抢占一条到期任务并发送；抢到返回 True

    多 worker 下每个进程都会扫到同一条任务，只有把 `next_run_at` 从「到期值」改掉的
    那一个进程负责发送，其余进程更新影响行数为 0、直接跳过 —— 与反馈中心 AI 审核、
    服务余量巡检同一口径，保证同一任务同一时刻只发一次。

    重复任务：抢占时把游标推进到「当前时间 + 间隔」（只补发一次，不累加欠的周期）。
    一次性任务：抢占即终止调度（enabled=False + 游标置空）。
    """
    if task.repeat:
        advance = now + timedelta(minutes=task.interval_minutes)
        claimed = EmailTask.objects.filter(
            pk=task.pk, enabled=True, next_run_at=task.next_run_at,
        ).update(next_run_at=advance, updated_time=now)
    else:
        claimed = EmailTask.objects.filter(
            pk=task.pk, enabled=True, next_run_at=task.next_run_at,
        ).update(enabled=False, next_run_at=None, updated_time=now)
    if not claimed:
        return False

    _deliver(task)
    return True


def _deliver(task):
    """发送一封邮件并回写结果（成功失败都记；失败不重试，等下一周期）"""
    recipients = [r for r in (task.recipients or '').split(',') if r]
    ok, message = send_email(task.subject, task.body, recipients, app_id=task.app_id)
    now = timezone.now()
    EmailTask.objects.filter(pk=task.pk).update(
        last_sent_at=now,
        sent_count=F('sent_count') + 1,
        last_ok=ok,
        last_message=(message or '')[:500],
        updated_time=now,
    )
    return ok


# ==================== 后台调度线程 ====================
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def start_worker():
    """启动后台调度线程（幂等；由 API/apps.py 在服务进程里调用一次）"""
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
    threading.Thread(target=_worker_loop, name='push-email-task', daemon=True).start()
    logger.info('邮件定时推送线程已启动（轮询间隔 %s 秒）', WORKER_INTERVAL_SECONDS)


def _worker_loop():
    """调度线程主循环：启动后先扫一轮，之后每隔 WORKER_INTERVAL_SECONDS 再扫"""
    while True:
        try:
            close_old_connections()
            run_due_tasks()
        except Exception:                       # noqa: BLE001 线程存活优先于单轮结果
            logger.exception('邮件定时推送线程异常')
        time.sleep(WORKER_INTERVAL_SECONDS)
