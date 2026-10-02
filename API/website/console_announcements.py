"""超管控制台 - 接口公告（文档中心公告栏）

用途：超管在这里发布公告，挂到「服务 / 线路 / 端点」三级 API 对象上；
前台文档中心（`/docs/<slug>/`）在对应位置展示，渲染片段见
`API/templates/docs/_announcements.html`。一条线路 / 端点可挂多条，按 `sort` 平铺。

鉴权：仅 Django is_superuser（见 admin_auth.superadmin_required）。

路径口径：与「服务策略」完全一致 —— 由「服务 → 线路 → 端点」三级选择推导出
`(scope, path_prefix)`，直接复用 `console._derive_prefix()`；服务树的枚举与
`console._tree_lookup()` 复用同一份数据，避免前后台两套口径对不上。

多语言：公告是数据库动态内容，**不做翻译** —— 后台填什么语言，前台就原样展示什么语言。
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from API.models import Announcement

from .admin_auth import notify_success, superadmin_required
from .console import _derive_prefix, _tree_lookup
from .service_tree import service_tree

# 时间输入框（<input type="datetime-local">）取值格式，如 2026-09-30T09:00
_TIME_FORMAT = '%Y-%m-%dT%H:%M'


@superadmin_required
def announcements_view(request):
    """公告管理：GET 渲染列表；POST 处理 新建 / 编辑 / 启停 / 删除"""
    if request.method == 'POST':
        return _handle_post(request)
    return _render(request)


def _scope_labels():
    return {value: _(label) for value, label in Announcement.SCOPE_CHOICES}


def _level_labels():
    return {value: _(label) for value, label in Announcement.LEVEL_CHOICES}


def _to_input(value):
    """DateTimeField 值 -> datetime-local 输入框取值（当前时区，分钟精度）"""
    return timezone.localtime(value).strftime(_TIME_FORMAT) if value else ''


def _parse_time(raw):
    """datetime-local 取值 -> 带时区 datetime；空返回 None；格式非法抛 ValueError"""
    raw = (raw or '').strip()
    if not raw:
        return None
    value = parse_datetime(raw) or parse_datetime(f'{raw}:00')
    if value is None:
        raise ValueError(raw)
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _render(request):
    scope_labels, level_labels = _scope_labels(), _level_labels()
    lookup = _tree_lookup(service_tree())
    items = []
    for item in Announcement.objects.all():          # Meta.ordering = (sort, create_time)
        path_label, path_registered = lookup.get(item.path_prefix, ('', False))
        items.append({
            'id': str(item.pk),
            'title': item.title,
            'content': item.content,
            'level': item.level,
            'level_label': level_labels[item.level],
            'level_def': item.level_def,
            'scope': item.scope,
            'scope_label': scope_labels[item.scope],
            'path_prefix': item.path_prefix,
            'path_label': path_label,
            'path_registered': path_registered,
            'sort': item.sort,
            'enabled': item.enabled,
            'is_visible': item.is_visible,
            'start_input': _to_input(item.start_time),
            'end_input': _to_input(item.end_time),
            'remark': item.remark,
        })
    return render(request, 'console/announcements.html', {
        'items': items,
        'tree': service_tree(),
        'level_choices': list(level_labels.items()),
    })


def _item_or_none(raw_id):
    raw = str(raw_id or '').strip()
    return Announcement.objects.filter(pk=raw).first() if raw.isdigit() else None


def _form_data(request):
    """读取并校验公告表单，返回 (data, error)"""
    title = (request.POST.get('title') or '').strip()
    content = (request.POST.get('content') or '').strip()
    level = (request.POST.get('level') or '').strip()
    remark = (request.POST.get('remark') or '').strip()
    if not title:
        return None, _('请填写公告标题')
    if len(title) > 100:
        return None, _('公告标题不能超过 100 个字符')
    if not content:
        return None, _('请填写公告正文')
    if level not in _level_labels():
        return None, _('非法的公告级别')
    derived, error = _derive_prefix(request)
    if error:
        return None, error
    scope, prefix = derived

    raw_sort = (request.POST.get('sort') or '').strip()
    try:
        sort = int(raw_sort) if raw_sort else 0
    except ValueError:
        return None, _('排序必须为整数')
    try:
        start_time = _parse_time(request.POST.get('start_time'))
        end_time = _parse_time(request.POST.get('end_time'))
    except ValueError:
        return None, _('生效时间格式不正确（应形如 2026-09-30 09:00）')
    if start_time and end_time and start_time > end_time:
        return None, _('生效开始时间不能晚于结束时间')

    return {
        'title': title, 'content': content, 'level': level, 'scope': scope,
        'path_prefix': prefix, 'sort': sort, 'start_time': start_time,
        'end_time': end_time, 'remark': remark,
    }, None


def _handle_post(request):
    action = (request.POST.get('action') or '').strip()
    if action == 'create':
        data, error = _form_data(request)
        if error:
            messages.error(request, error)
        else:
            item = Announcement.objects.create(**data)
            notify_success(request, _('公告「%(title)s」已发布') % {'title': item.title})
        return redirect('website:console_announcements')

    item = _item_or_none(request.POST.get('id'))
    if item is None:
        messages.error(request, _('公告不存在'))
        return redirect('website:console_announcements')

    if action == 'edit':
        data, error = _form_data(request)
        if error:
            messages.error(request, error)
        else:
            for field, value in data.items():
                setattr(item, field, value)
            item.save()
            notify_success(request, _('公告「%(title)s」已保存') % {'title': item.title})
    elif action == 'toggle':
        item.enabled = not item.enabled
        item.save(update_fields=['enabled', 'updated_time'])
        notify_success(request, _('公告已启用') if item.enabled else _('公告已停用'))
    elif action == 'delete':
        item.delete()
        notify_success(request, _('已删除该公告'))
    else:
        messages.error(request, _('不支持的操作'))
    return redirect('website:console_announcements')
