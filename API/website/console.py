"""官网“超级管理员”控制台视图

- projects_view：接入项目（UserApp）增删改查；
- services_api：文档侧栏“服务设置”弹窗后端（服务对外状态等，JSON API）。

鉴权：仅 Django is_superuser 可访问（见 admin_auth.py），
未登录/非超管会被自动重定向到统一登录；普通用户不可见/不可访问。
说明：接入项目的 APPID/APPSECRET 由系统自动生成；创建后仅此页一次性展示新密钥。
"""
import uuid

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from API.common import StatusCode
from API.common import api_stats_query as stats_query
from API.common.middleware import requires_auth
from API.models import ApiCategory, ServiceStatus, UserApp
from API.models.Statistics.api_call_stat import NO_APP

from .admin_auth import superadmin_required
from .service_status import STATUS_KEYS, status_def
from .services import SERVICES


@superadmin_required
def projects_view(request):
    """接入项目列表 + 搜索 + 增删改（action 区分）"""
    if request.method == 'POST':
        return _handle_project_action(request)
    return _render_projects(request)


def _project_or_404(raw_id):
    try:
        return get_object_or_404(UserApp, pk=uuid.UUID(str(raw_id)))
    except (ValueError, TypeError):
        return None


def _handle_project_action(request):
    action = (request.POST.get('action') or '').strip()
    if action == 'create':
        name = (request.POST.get('name') or '').strip()
        if not name:
            messages.error(request, _('请填写应用名称'))
            return redirect('website:console_projects')
        try:
            app = UserApp.objects.create(name=name)
        except IntegrityError:
            messages.error(request, _('应用名称已存在，请更换'))
            return redirect('website:console_projects')
        messages.success(request, _('项目创建成功，请复制并妥善保存下方的 APPID 与 APPSECRET（仅此一次展示）'))
        return redirect(f"{reverse('website:console_projects')}?created={app.pk}")

    if action in ('edit', 'delete'):
        app = _project_or_404(request.POST.get('id'))
        if app is None:
            messages.error(request, _('项目不存在'))
            return redirect('website:console_projects')
        if action == 'delete':
            app.delete()
            messages.success(request, _('项目「%(name)s」已删除，其全部 Token 已同步失效') % {'name': app.name})
            return redirect('website:console_projects')
        # edit
        name = (request.POST.get('name') or '').strip()
        try:
            expire = int(request.POST.get('token_expire_days') or '')
            if expire <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, _('Token 有效天数必须为正整数'))
            return redirect('website:console_projects')
        status = (request.POST.get('status') or '') == 'on'
        if not name:
            messages.error(request, _('请填写应用名称'))
            return redirect('website:console_projects')
        if UserApp.objects.filter(name=name).exclude(pk=app.pk).exists():
            messages.error(request, _('应用名称已存在，请更换'))
            return redirect('website:console_projects')
        app.name = name
        app.token_expire_days = expire
        app.status = status
        try:
            app.save()  # save() 会强制保留 app_id/app_secret 原值
        except IntegrityError:
            messages.error(request, _('应用名称已存在，请更换'))
            return redirect('website:console_projects')
        messages.success(request, _('项目「%(name)s」已更新') % {'name': app.name})
        return redirect('website:console_projects')

    messages.error(request, _('不支持的操作'))
    return redirect('website:console_projects')


def _render_projects(request):
    keyword = (request.GET.get('q') or '').strip()
    apps = UserApp.objects.all()
    if keyword:
        apps = apps.filter(Q(name__icontains=keyword) | Q(app_id__icontains=keyword))
    apps = apps.order_by('-create_time')

    created = None
    created_id = request.GET.get('created') or ''
    if created_id:
        app = _project_or_404(created_id)
        if app:
            created = {
                'app_id': app.app_id,
                'app_secret': app.app_secret,
            }
    return render(request, 'console/projects.html', {
        'apps': apps,
        'keyword': keyword,
        'created': created,
    })


# ==================== API 服务分类（认证模式）管理 ====================

def _mode_labels():
    """认证模式：值 -> 已翻译文案

    模型里的 AUTH_MODE_CHOICES 是中文常量，展示前统一翻译（每次调用实时取词，
    避免在模块级固化译文）。
    """
    return {value: _(label) for value, label in ApiCategory.AUTH_MODE_CHOICES}


@superadmin_required
def categories_view(request):
    """超管：API 服务分类认证模式管理

    GET  ：按前缀顺序渲染整棵分类树（每条含「本节点模式」与真实「生效结果」）
    POST ：path_prefix + auth_mode → 保存并回跳

    说明：分类树本身由 `manage.py rebuild_category_tree` 按 `API/apis/` 目录生成，
    本页只手工调整认证模式（inherit/auth/open），重建命令不会覆盖该字段。
    """
    if request.method == 'POST':
        return _handle_category_action(request)
    return _render_categories(request)


def _handle_category_action(request):
    prefix = (request.POST.get('path_prefix') or '').strip()
    mode = (request.POST.get('auth_mode') or '').strip()
    labels = _mode_labels()
    node = ApiCategory.objects.filter(path_prefix=prefix).first()
    if node is None:
        messages.error(request, _('分类不存在'))
        return redirect('website:console_categories')
    if mode not in labels:
        messages.error(request, _('非法的认证模式'))
        return redirect('website:console_categories')
    node.auth_mode = mode
    # 保存后由 API/apps.py 的 post_save 信号自动使分类树缓存失效，改动对接口鉴权立即生效
    node.save(update_fields=['auth_mode'])
    messages.success(request, _('已把「%(path)s」的认证模式更新为「%(mode)s」')
                     % {'path': prefix, 'mode': labels[mode]})
    return redirect('website:console_categories')


def _render_categories(request):
    """渲染分类树：展示本节点模式 + 真实生效结果

    「生效结果」直接复用认证中间件的 requires_auth()，保证页面显示与接口实际鉴权一致。
    """
    nodes = []
    for node in ApiCategory.objects.all():  # Meta.ordering = path_prefix，天然按树顺序排列
        segments = [seg for seg in node.path_prefix.strip('/').split('/') if seg]
        nodes.append({
            'path_prefix': node.path_prefix,
            'name': node.name,
            'auth_mode': node.auth_mode,
            'enabled': node.status,
            'depth': max(0, len(segments) - 1),  # /api/ 为 0 级，服务为 1 级，子路径递增
            'effective_auth': requires_auth(node.path_prefix),
        })
    return render(request, 'console/categories.html', {
        'nodes': nodes,
        'mode_choices': list(_mode_labels().items()),
    })


# ==================== API 调用统计看板 ====================

# 看板可选时间范围（天）与默认值
STATS_RANGES = (7, 30)
STATS_DEFAULT_RANGE = 7


@superadmin_required
def stats_view(request):
    """超管：API 调用统计看板（?days=7|30 切换时间范围）

    数据口径见 API/common/api_stats.py（写入）与 API/common/api_stats_query.py（查询）；
    本视图只取数 + 展示，图表由本地托管的 Chart.js 绘制。
    """
    try:
        days = int(request.GET.get('days') or STATS_DEFAULT_RANGE)
    except (TypeError, ValueError):
        days = STATS_DEFAULT_RANGE
    if days not in STATS_RANGES:
        days = STATS_DEFAULT_RANGE

    # 服务排行：补上服务中文名（与官网服务清单同源）
    service_names = {svc['url_prefix']: _(svc['name']) for svc in SERVICES}
    services = stats_query.service_ranking(days)
    for row in services:
        row['name'] = service_names.get(row['key'], row['key'])

    # 项目排行：补上项目名；无项目的记为「开放接口 / 未认证」
    apps = stats_query.app_ranking(days, limit=20)
    app_names = dict(UserApp.objects.filter(
        app_id__in=[row['key'] for row in apps]).values_list('app_id', 'name'))
    for row in apps:
        if row['key'] == NO_APP:
            row['name'] = _('开放接口 / 未认证')
        else:
            row['name'] = app_names.get(row['key'], '')

    # 状态码文案按当前语言翻译
    status_codes = stats_query.status_code_distribution(days)
    for row in status_codes:
        row['label'] = _(StatusCode.get_message(row['key']))

    return render(request, 'console/stats.html', {
        'days': days,
        'range_choices': STATS_RANGES,
        'today': stats_query.overview(1),
        'overview': stats_query.overview(days),
        'trend': stats_query.daily_trend(days),
        'services': services,
        'endpoints': stats_query.endpoint_ranking(days, limit=20),
        'apps': apps,
        'status_codes': status_codes,
    })


# ==================== 服务设置弹窗 API ====================

def _resp(code=10000, msg='ok', data=None):
    """统一 JSON 结构：{code, msg, data}；code=10000 表示成功。"""
    return JsonResponse({'code': code, 'msg': msg, 'data': data})


def _find_service(prefix):
    return next((svc for svc in SERVICES if svc['url_prefix'] == prefix), None)


def _registered_prefixes():
    from .docs import all_docs as _all_docs
    return {doc.prefix for doc in _all_docs()}


def _status_payload(prefix):
    """构造某服务“状态”设置分组的数据（含可选项/当前/默认）。"""
    manual = {r.url_prefix: r.status for r in ServiceStatus.objects.only('url_prefix', 'status')}
    default_key = 'open' if prefix in _registered_prefixes() else 'building'
    current = manual.get(prefix, default_key)
    return {
        'current': current,
        'current_label': status_def(current)['label'],
        'current_badge': status_def(current)['badge'],
        'manual': prefix in manual,
        'default': default_key,
        'default_label': status_def(default_key)['label'],
        'options': [{'key': key, **status_def(key)} for key in STATUS_KEYS],
    }


@superadmin_required
def services_api(request):
    """文档侧栏“服务设置”弹窗后端（JSON）。

    GET  ?url_prefix=...  → 返回该服务现有全部“设置分组”（当前仅 status）；
    POST action=set_status|reset_status + url_prefix → 写入并回传最新分组数据。

    扩展点（地基）：每新增一类设置，
    后端在 GET 的 sections 里追加一个分组对象、在 POST 里增加对应 action；
    前端在 service_settings.js 的 SECTIONS 注册表里登记同名渲染器即可。
    """
    if request.method == 'POST':
        return _services_api_action(request)
    return _services_api_detail(request)


def _services_api_detail(request):
    prefix = (request.GET.get('url_prefix') or '').strip()
    svc = _find_service(prefix)
    if svc is None:
        return _resp(code=400, msg=_('未知的服务'))
    return _resp(data={
        'service': {'name': _(svc['name']), 'url_prefix': prefix},
        'sections': [
            {
                'id': 'status',
                'icon': 'activity',
                'title': _('API 服务状态'),
                'desc': _('自定义该服务的对外状态（开放/测试中/维护中/建设中/已下线），同步官网首页与文档中心。'),
                'status': _status_payload(prefix),
            },
        ],
    })


def _services_api_action(request):
    prefix = (request.POST.get('url_prefix') or '').strip()
    if _find_service(prefix) is None:
        return _resp(code=400, msg=_('未知的服务'))

    action = (request.POST.get('action') or '').strip()
    if action == 'set_status':
        value = (request.POST.get('status') or '').strip()
        if value not in STATUS_KEYS:
            return _resp(code=400, msg=_('非法的状态值'))
        default_key = 'open' if prefix in _registered_prefixes() else 'building'
        if value == default_key:
            ServiceStatus.objects.filter(url_prefix=prefix).delete()
            msg = _('已恢复默认状态（%(label)s）') % {'label': status_def(value)['label']}
        else:
            ServiceStatus.objects.update_or_create(url_prefix=prefix, defaults={'status': value})
            msg = _('已更新为「%(label)s」') % {'label': status_def(value)['label']}
        return _resp(msg=msg, data={'status': _status_payload(prefix)})

    if action == 'reset_status':
        ServiceStatus.objects.filter(url_prefix=prefix).delete()
        payload = _status_payload(prefix)
        return _resp(msg=_('已恢复默认（%(label)s）') % {'label': payload['current_label']},
                     data={'status': payload})

    return _resp(code=400, msg=_('不支持的操作'))
