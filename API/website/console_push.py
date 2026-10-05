"""超管控制台 · 推送日志

`/console/push-logs/`：查看「消息推送服务」的每次推送尝试（谁发的 / 标题 / 渠道 / 成败 / 上游码 / 推送ID）。

鉴权：仅 Django is_superuser（见 admin_auth.py）。

数据由 `API/apis/push/serverchan/utils.py` 在每次推送后写入（成功 / 失败均记），
本页只读；SendKey 不在本表、也不在页面展示（凭据只在控制台「账号管理」维护）。

筛选口径（三者可叠加）：
    · 结果：全部 / 成功 / 失败；
    · 项目：出过推送的项目（按 app_id 筛选，选项显示项目名；项目删掉后仍能按其 app_id 筛出历史）；
    · 关键词：只搜**标题与正文内容**；选了项目时即在该项目的推送里搜。
「项目」列把 app_id 翻成项目名（复用统计页的 `_app_names` / `_app_label`；项目已删除时显示「已删除项目」），
悬停仍可看到原始 app_id。
筛选与分页与其它控制台列表页同一套骨架（复用 `console_users._page_prefix` 与 `_pagination.html`）。
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from API.models import PushLog

from .admin_auth import superadmin_required
from .console import _app_label, _app_names
from .console_users import _page_prefix

PAGE_SIZE = 50

#: 渠道标识 -> 展示名（新增推送线路时在此补一行）
CHANNEL_LABELS = {
    'serverchan': 'Server酱',
}

#: 结果筛选档位
RESULT_FILTERS = ('all', 'ok', 'fail')


def _project_keys():
    """出过推送的项目 app_id（去重、排除空值），用于构建「项目」筛选下拉

    先 order_by() 清掉模型默认排序（`-create_time`）——否则默认排序字段会被带进
    SELECT，`distinct()` 就去重不掉。
    """
    return list(PushLog.objects.exclude(app_id='').order_by()
                .values_list('app_id', flat=True).distinct())


@superadmin_required
def push_logs_view(request):
    """推送日志列表（只读，支持结果 / 项目筛选 + 标题与正文关键词搜索）"""
    keyword = (request.GET.get('q') or '').strip()
    result = (request.GET.get('result') or 'all').strip()
    if result not in RESULT_FILTERS:
        result = 'all'

    app_keys = _project_keys()
    # 只接受出现过的项目值，避免手改 URL 得到一片空白
    project = (request.GET.get('project') or '').strip()
    project = project if project in app_keys else ''

    logs = PushLog.objects.all()
    if result == 'ok':
        logs = logs.filter(ok=True)
    elif result == 'fail':
        logs = logs.filter(ok=False)
    if project:
        logs = logs.filter(app_id=project)
    if keyword:
        # 只搜标题与正文；选了项目即在该项目的推送里搜
        logs = logs.filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))

    paginator = Paginator(logs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    app_names = _app_names(app_keys)
    for log in page.object_list:
        log.channel_label = CHANNEL_LABELS.get(log.channel, log.channel)
        log.app_label = _app_label(log.app_id, app_names) if log.app_id else ''

    return render(request, 'console/push_logs.html', {
        'page_obj': page,
        'paginator': paginator,
        'total': paginator.count,
        'keyword': keyword,
        'result_filter': result,
        'project_filter': project,
        'app_options': sorted(
            ({'value': key, 'label': _app_label(key, app_names, for_option=True)}
             for key in app_keys),
            key=lambda item: item['label']),
        'page_prefix': _page_prefix(request),
    })
