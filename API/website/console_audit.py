"""超管控制台 · 操作日志

`/console/audit/`：查看超管在控制台做过的**写操作**（谁 / 何时 / 哪个功能 / 什么动作 / 结果 / 从哪来）。

数据由 `admin_auth.superadmin_required` 统一采集（口径见 `API/models/Security/audit.py`），
本页只读：**看日志这个动作本身不产生日志**（审计只看写操作）。

筛选与分页与其它控制台列表页同一套骨架（复用 `console_users._page_prefix` 与 `_pagination.html`）。
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from API.models import ConsoleAuditLog

from .admin_auth import superadmin_required
from .console_menu import MENU
from .console_users import _page_prefix

PAGE_SIZE = 50


def _menu_labels():
    """URL name -> 菜单里的中文功能名

    直接读侧边栏菜单声明：加一个新控制台页面时，这里自动就有名字，不必再维护第二份对照表。
    菜单没登记的名字（如详情页 `console_user_detail`）原样显示。
    """
    return {item['key']: item['name'] for group in MENU for item in group['items']}


@superadmin_required
def audit_view(request):
    """操作日志列表（只读页）"""
    keyword = (request.GET.get('q') or '').strip()
    operator = (request.GET.get('operator') or '').strip()
    view_name = (request.GET.get('view') or '').strip()

    labels = _menu_labels()
    logs = ConsoleAuditLog.objects.all()
    if operator:
        logs = logs.filter(operator=operator)
    if view_name:
        logs = logs.filter(view_name=view_name)
    if keyword:
        logs = logs.filter(Q(path__icontains=keyword) | Q(note__icontains=keyword)
                           | Q(action__icontains=keyword) | Q(target__icontains=keyword))

    paginator = Paginator(logs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    # 给每行补上「功能」的中文名（模板里不做查表）
    for log in page.object_list:
        log.view_label = labels.get(log.view_name) or log.view_name or ''

    return render(request, 'console/audit.html', {
        'page_obj': page,
        'paginator': paginator,
        'total': paginator.count,
        'keyword': keyword,
        'operator_filter': operator,
        'view_filter': view_name,
        'page_prefix': _page_prefix(request),
        # 下拉只列出现过的取值：日志多了以后仍然好用，也不会给出一堆空结果
        'operator_options': (ConsoleAuditLog.objects.exclude(operator='')
                             .values_list('operator', flat=True).distinct().order_by('operator')),
        'view_options': [{'value': name, 'label': labels.get(name) or name}
                         for name in (ConsoleAuditLog.objects.exclude(view_name='')
                                      .values_list('view_name', flat=True).distinct().order_by('view_name'))],
    })
