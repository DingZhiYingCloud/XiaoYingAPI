"""超管控制台 - 邮件定时推送任务

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/email-tasks/   全部任务列表（可按项目 / 启用状态 / 关键词筛选）
    POST /console/email-tasks/   action = task_create / task_edit / task_toggle / task_delete

口径：
    · 这是 `/api/push/email_task/`（邮件定时推送服务）的**后台管理页**，操作的是同一张
      `EmailTask` 表：超管可查看**全部接入项目**的任务，并代其新增 / 编辑 / 启停 / 删除。
    · 与对外接口同一套限制（收件人最多 MAX_RECIPIENTS 个、间隔最大 MAX_INTERVAL_MINUTES），
      避免后台成为绕过限制的入口。
    · 「发送间隔」0 = 只发一次；>0 = 每 N 分钟重复。发送由站内常驻线程完成
      （见 `API/apis/push/email_task/utils.py`），本页只负责增删改与看状态。
    · 「归属项目」留空 = 内部任务（不归属任何接入项目，对外接口查不到）。
"""
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from API.apis.push.email_task.utils import MAX_INTERVAL_MINUTES, MAX_RECIPIENTS
from API.models import EmailTask, UserApp

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.push')

REDIRECT_URL = 'website:console_email_tasks'

# 列表分页
PAGE_SIZE = 20
# 首次发送时间允许的写法（不带时区，按 settings.TIME_ZONE 解释）
_DT_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M')


@superadmin_required
def email_tasks_view(request):
    """邮件定时推送任务：展示 + 新增 / 编辑 / 启停 / 删除"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action in ('task_create', 'task_edit'):
            return _save(request, editing=action == 'task_edit')
        if action == 'task_toggle':
            return _toggle(request)
        if action == 'task_delete':
            return _delete(request)
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)
    return _render(request)


def _render(request):
    """列表：按项目 / 启用状态 / 关键词筛选后分页"""
    keyword = (request.GET.get('q') or '').strip()
    enabled_filter = (request.GET.get('enabled') or '').strip()
    app_filter = (request.GET.get('app_id') or '').strip()

    qs = EmailTask.objects.all()
    if keyword:
        qs = qs.filter(Q(subject__icontains=keyword) | Q(recipients__icontains=keyword)
                       | Q(app_id__icontains=keyword))
    if enabled_filter in ('1', '0'):
        qs = qs.filter(enabled=enabled_filter == '1')
    if app_filter:
        qs = qs.filter(app_id=app_filter)

    apps = list(UserApp.objects.order_by('name'))
    app_names = {app.app_id: app.name for app in apps}

    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    rows = []
    for task in page.object_list:
        # 模板据此展示「归属项目」列；为空表示内部任务
        task.app_name = app_names.get(task.app_id, '')
        rows.append(task)

    return render(request, 'console/email_tasks.html', {
        'page_obj': page,
        'paginator': paginator,
        'total': paginator.count,
        'rows': rows,
        'apps': apps,
        'keyword': keyword,
        'enabled_filter': enabled_filter,
        'app_filter': app_filter,
        'page_prefix': _page_prefix(request),
        'max_recipients': MAX_RECIPIENTS,
    })


def _page_prefix(request):
    """分页链接前缀：当前筛选参数 + 结尾 '&'（无参数时为空串），供 ?{{ page_prefix }}page=N"""
    params = request.GET.copy()
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{encoded}&' if encoded else ''


def _task_or_none(raw_id):
    """按主键取任务（缺失 / 非法 UUID 一律 None，不抛 500）"""
    raw = (raw_id or '').strip()
    if not raw:
        return None
    try:
        return EmailTask.objects.filter(pk=raw).first()
    except (ValidationError, ValueError):
        return None


def _parse_recipients(raw):
    """解析收件人（逗号 / 换行分隔，去重 + 校验邮箱 + 数量上限）

    :return: (list, None) 或 (None, 错误提示)
    """
    addresses = [a.strip() for a in (raw or '').replace('\n', ',').split(',') if a.strip()]
    addresses = list(dict.fromkeys(addresses))
    if not addresses:
        return None, _('收件人邮箱不能为空')
    if len(addresses) > MAX_RECIPIENTS:
        return None, _('收件人最多 %(n)s 个') % {'n': MAX_RECIPIENTS}
    invalid = []
    for addr in addresses:
        try:
            validate_email(addr)
        except ValidationError:
            invalid.append(addr)
    if invalid:
        return None, _('邮箱格式错误：%(list)s') % {'list': '、'.join(invalid)}
    return addresses, None


def _parse_interval(raw):
    """解析发送间隔（分钟）：空 = 0（只发一次）

    :return: (int, None) 或 (None, 错误提示)
    """
    text = (raw or '').strip()
    if not text:
        return 0, None
    if not text.isdigit():
        return None, _('发送间隔必须为非负整数（分钟）')
    value = int(text)
    if value > MAX_INTERVAL_MINUTES:
        return None, _('发送间隔最大 %(n)s 分钟') % {'n': MAX_INTERVAL_MINUTES}
    return value, None


def _parse_dt(raw):
    """解析首次发送时间（选填）；为空返回 (None, None)"""
    text = (raw or '').strip()
    if not text:
        return None, None
    for fmt in _DT_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt, None
    return None, _('首次发送时间格式应为 2026-10-09 15:30 或 2026-10-09 15:30:00')


def _save(request, editing):
    """新增或编辑任务

    编辑时：修改间隔会按「当前时间 + 新间隔」重排下一次发送；重新启用一个已结束的
    一次性任务会立即重新进入调度（口径与对外接口一致）。
    """
    task = None
    if editing:
        task = _task_or_none(request.POST.get('id'))
        if task is None:
            messages.error(request, _('任务不存在'))
            return redirect(REDIRECT_URL)

    app_id = (request.POST.get('app_id') or '').strip()
    if app_id and not UserApp.objects.filter(app_id=app_id).exists():
        messages.error(request, _('归属项目不存在'))
        return redirect(REDIRECT_URL)

    recipients, error = _parse_recipients(request.POST.get('recipients'))
    if error:
        messages.error(request, error)
        return redirect(REDIRECT_URL)

    subject = (request.POST.get('subject') or '').strip()
    if not subject:
        messages.error(request, _('邮件标题不能为空'))
        return redirect(REDIRECT_URL)
    if len(subject) > 255:
        messages.error(request, _('邮件标题最长 255 个字符'))
        return redirect(REDIRECT_URL)

    body = request.POST.get('body') or ''
    if not body.strip():
        messages.error(request, _('邮件正文不能为空'))
        return redirect(REDIRECT_URL)

    interval_minutes, error = _parse_interval(request.POST.get('interval_minutes'))
    if error:
        messages.error(request, error)
        return redirect(REDIRECT_URL)

    first_send_at, error = _parse_dt(request.POST.get('first_send_at'))
    if error:
        messages.error(request, error)
        return redirect(REDIRECT_URL)

    enabled = request.POST.get('enabled') == 'on'
    now = timezone.now()

    if task is None:
        EmailTask.objects.create(
            app_id=app_id, recipients=','.join(recipients), subject=subject, body=body,
            interval_minutes=interval_minutes, enabled=enabled,
            next_run_at=first_send_at or now,
        )
        notify_success(request, _('已新增任务「%(s)s」') % {'s': subject})
        return redirect(REDIRECT_URL)

    interval_changed = interval_minutes != task.interval_minutes
    task.app_id = app_id
    task.recipients = ','.join(recipients)
    task.subject = subject
    task.body = body
    task.interval_minutes = interval_minutes
    task.enabled = enabled
    if first_send_at:
        task.next_run_at = first_send_at
    elif interval_changed:
        task.next_run_at = (now + timedelta(minutes=interval_minutes)
                            if interval_minutes > 0 else now)
    if enabled and task.next_run_at is None:
        task.next_run_at = now
    task.save()
    notify_success(request, _('已保存任务「%(s)s」') % {'s': subject})
    return redirect(REDIRECT_URL)


def _toggle(request):
    """启用 / 停用任务（重新启用已结束的一次性任务会立即重新进入调度）"""
    task = _task_or_none(request.POST.get('id'))
    if task is None:
        messages.error(request, _('任务不存在'))
        return redirect(REDIRECT_URL)
    task.enabled = not task.enabled
    if task.enabled and task.next_run_at is None:
        task.next_run_at = timezone.now()
    task.save(update_fields=['enabled', 'next_run_at', 'updated_time'])
    if task.enabled:
        notify_success(request, _('已启用任务「%(s)s」') % {'s': task.subject})
    else:
        notify_success(request, _('已停用任务「%(s)s」') % {'s': task.subject})
    return redirect(REDIRECT_URL)


def _delete(request):
    """删除任务"""
    task = _task_or_none(request.POST.get('id'))
    if task is None:
        messages.error(request, _('任务不存在'))
        return redirect(REDIRECT_URL)
    subject = task.subject
    task.delete()
    logger.info('邮件定时任务已删除 subject=%s operator=%s', subject, request.user.get_username())
    notify_success(request, _('已删除任务「%(s)s」') % {'s': subject})
    return redirect(REDIRECT_URL)
