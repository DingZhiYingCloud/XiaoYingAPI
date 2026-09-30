"""官网“超级管理员”控制台视图

- home_view：控制台首页（关键指标概览 + 模块入口，入口取自 console_menu 声明）；
- projects_view：接入项目（UserApp）增删改查；
- services_view：API 服务策略（服务 / 线路 / 端点三级继承、状态、认证模式、项目白名单）增删改查。

鉴权：仅 Django is_superuser 可访问（见 admin_auth.py），
未登录/非超管会被自动重定向到统一登录；普通用户不可见/不可访问。
说明：接入项目的 APPID/APPSECRET 由系统自动生成；创建后仅此页一次性展示新密钥。
"""
import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from API.common import StatusCode
from API.common import api_stats_query as stats_query
from API.common.api_stats import UNMATCHED_PATH, purge_app, service_of
from API.common.middleware import resolve_service_policy, requires_auth
from API.models import Announcement, ApiServicePolicy, Feedback, User, UserApp
from API.models.Statistics.api_call_stat import NO_APP

from .admin_auth import superadmin_required
from .service_status import status_def
from .service_tree import service_tree
from .services import SERVICES

# 控制台首页「近 N 天」调用概览的时间窗口（与调用统计看板的默认口径一致）
HOME_OVERVIEW_DAYS = 7


@superadmin_required
def home_view(request):
    """控制台首页：关键指标概览 + 待关注事项 + 各模块入口

    待关注事项（待处理反馈 / 生效中的公告）只做计数，点进去由各自模块页处理 ——
    首页只回答「有没有事情等着我」，不重复实现列表逻辑。
    """
    return render(request, 'console/home.html', {
        'overview_days': HOME_OVERVIEW_DAYS,
        'stats': stats_query.overview(HOME_OVERVIEW_DAYS),
        'counts': {
            'apps': UserApp.objects.count(),
            'users': User.objects.count(),
            'banned_users': User.objects.filter(status=False).count(),
            'feedback_open': Feedback.objects.filter(
                status__in=(Feedback.Status.PENDING, Feedback.Status.PROCESSING)).count(),
            'announcements': Announcement.visible_queryset().count(),
        },
    })


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
            deleted_app_id = app.app_id
            app.delete()
            # 统计表按 APPID 聚合且只追加：项目删掉后历史行不会消失，会在看板上变成「已删除项目」，
            # 因此删除项目时一并清理（服务端缓冲可能残留极少量未落库的行，由看板的标签兜底）
            purged = purge_app(deleted_app_id)
            messages.success(request, _('项目「%(name)s」已删除，其全部 Token 已同步失效') % {'name': app.name})
            if purged:
                messages.info(request, _('同时清理该项目的调用统计 %(n)s 行') % {'n': purged})
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

    # APPSECRET 只按需下发：创建后一次性展示（created）或超管显式点击查看某个项目（reveal），
    # 避免列表页把全部项目的明文密钥一次性渲染进 HTML
    reveal = None
    reveal_id = (request.GET.get('reveal') or '').strip()
    if reveal_id:
        app = _project_or_404(reveal_id)
        if app:
            reveal = {
                'id': str(app.pk),
                'app_id': app.app_id,
                'app_secret': app.app_secret,
            }
    return render(request, 'console/projects.html', {
        'apps': apps,
        'keyword': keyword,
        'created': created,
        'reveal': reveal,
    })


# ==================== API 服务策略（服务 / 线路 / 端点三级继承） ====================

def _policy_level_labels():
    """层级：值 -> 已翻译文案"""
    return {value: _(label) for value, label in ApiServicePolicy.LEVEL_CHOICES}


def _policy_status_labels():
    """服务状态：值 -> 已翻译文案"""
    return {value: _(label) for value, label in ApiServicePolicy.STATUS_CHOICES}


def _policy_mode_labels():
    """策略认证模式：值 -> 已翻译文案（每次调用实时取词，避免在模块级固化译文）"""
    return {value: _(label) for value, label in ApiServicePolicy.AUTH_MODE_CHOICES}


def _policy_scope_labels():
    """项目范围：值 -> 已翻译文案"""
    return {value: _(label) for value, label in ApiServicePolicy.APP_SCOPE_CHOICES}


def _policy_docs_visible_labels():
    """文档可见性：值 -> 已翻译文案"""
    return {value: _(label) for value, label in ApiServicePolicy.DOCS_VISIBLE_CHOICES}


def _policy_audience_labels():
    """使用范围：值 -> 已翻译文案"""
    return {value: _(label) for value, label in ApiServicePolicy.AUDIENCE_CHOICES}


@superadmin_required
def services_view(request):
    """超管：API 服务策略管理（服务 / 线路 / 端点三级继承）

    GET  ：按前缀顺序列出全部策略（含真实「生效结果」，复用 resolve_service_policy()）
    POST ：action = create / edit / toggle / delete
    """
    if request.method == 'POST':
        return _handle_service_action(request)
    return _render_services(request)


def _tree_lookup(tree):
    """前缀 / 路径 -> (中文路径标签, 是否已在文档登记)，供列表页展示带中文名的路径"""
    lookup = {}
    for svc in tree:
        lookup[svc['prefix']] = (svc['name'], svc['registered'])
        for ch in svc['channels']:
            lookup[ch['prefix']] = (f"{svc['name']} / {ch['name']}", ch['registered'])
            for ep in ch['endpoints']:
                lookup[ep['path']] = (f"{svc['name']} / {ch['name']} / {ep['name']}",
                                      ep['registered'])
    return lookup


def _render_services(request):
    """渲染策略列表：层级 / 路径 / 状态 / 认证模式 / 生效结果 / 项目范围 / 白名单数

    「生效结果」直接复用认证中间件的 resolve_service_policy() / requires_auth()，
    保证页面显示与接口实际鉴权一致。
    """
    level_labels = _policy_level_labels()
    status_labels = _policy_status_labels()
    mode_labels = _policy_mode_labels()
    scope_labels = _policy_scope_labels()
    docs_visible_labels = _policy_docs_visible_labels()
    audience_labels = _policy_audience_labels()
    tree = service_tree()
    lookup = _tree_lookup(tree)
    policies = []
    for policy in ApiServicePolicy.objects.annotate(whitelist_count=Count('apps')):
        effective = resolve_service_policy(policy.path_prefix)
        eff_status = status_def(effective['status'])
        # 一条策略可覆盖多条线路：逐前缀给出中文路径标签（未登记的留空）
        path_rows = []
        for prefix in policy.all_prefixes:
            label, registered = lookup.get(prefix, ('', False))
            path_rows.append({'prefix': prefix, 'label': label, 'registered': registered})
        policies.append({
            'id': str(policy.pk),
            'name': policy.name,
            'level': policy.level,
            'level_label': level_labels[policy.level],
            'path_prefix': policy.path_prefix,
            'path_prefixes': policy.all_prefixes,
            'path_rows': path_rows,
            'status': policy.status,
            'status_label': status_labels[policy.status],
            'auth_mode': policy.auth_mode,
            'auth_mode_label': mode_labels[policy.auth_mode],
            'app_scope': policy.app_scope,
            'scope_label': scope_labels[policy.app_scope],
            'docs_visible': policy.docs_visible,
            'docs_visible_label': docs_visible_labels[policy.docs_visible],
            'audience': policy.audience,
            'audience_label': audience_labels[policy.audience],
            'whitelist_count': policy.whitelist_count,
            'remark': policy.remark,
            'effective_status_label': eff_status['label'],
            'effective_status_badge': eff_status['badge'],
            'effective_auth': requires_auth(policy.path_prefix),
            'effective_scope': effective['app_scope'],
            'effective_docs_visible': effective['docs_visible'],
            'effective_audience': effective['audience'],
            'app_ids': [str(pk) for pk in policy.apps.values_list('pk', flat=True)],
        })
    return render(request, 'console/services.html', {
        'policies': policies,
        'tree': tree,
        'level_choices': list(level_labels.items()),
        'status_choices': list(status_labels.items()),
        'mode_choices': list(mode_labels.items()),
        'scope_choices': list(scope_labels.items()),
        'docs_visible_choices': list(docs_visible_labels.items()),
        'audience_choices': list(audience_labels.items()),
        'apps': UserApp.objects.order_by('name'),
    })


def _policy_or_none(raw_id):
    """按主键（自增整数）取策略；非法值返回 None"""
    raw = str(raw_id or '').strip()
    return ApiServicePolicy.objects.filter(pk=raw).first() if raw.isdigit() else None


def _handle_service_action(request):
    action = (request.POST.get('action') or '').strip()
    if action == 'create':
        return _action_create_policy(request)
    if action == 'delete_bulk':
        return _action_delete_policies(request)
    policy = _policy_or_none(request.POST.get('id'))
    if policy is None:
        messages.error(request, _('服务策略不存在'))
        return redirect('website:console_services')
    if action == 'edit':
        return _action_edit_policy(request, policy)
    if action == 'toggle':
        return _action_toggle_policy(request, policy)
    if action == 'delete':
        return _action_delete_policy(request, policy)
    messages.error(request, _('不支持的操作'))
    return redirect('website:console_services')


def _derive_prefix(request):
    """由「服务 → 线路 → 端点」三级选择推导 (level, path_prefix)；非法返回 (None, 错误文案)

    供「接口公告」等单选调用方使用（公告一条只挂一个前缀）；策略多选线路见
    :func:`_derive_prefixes`。
    """
    service = (request.POST.get('service') or '').strip()
    channel = (request.POST.get('channel') or '').strip()
    endpoint = (request.POST.get('endpoint') or '').strip()
    if not service.startswith('/api/'):
        return None, _('请选择 API 服务')
    if channel and not channel.startswith(service.rstrip('/') + '/'):
        return None, _('线路与所选服务不匹配')
    if endpoint and not endpoint.startswith(channel.rstrip('/') + '/'):
        return None, _('端点与所选线路不匹配')
    if endpoint:
        return ('endpoint', endpoint), None
    if channel:
        return ('channel', channel), None
    return ('service', service), None


def _derive_prefixes(request):
    """由「服务 → 线路（可多选）→ 端点」推导 (level, [前缀, ...])；非法返回 (None, 错误文案)

    线路支持多选：同一服务下的多条线路可以共用一条策略（第一条作主前缀，其余进
    ``extra_prefixes``）。端点仍为单选，且只在恰好选中一条线路时可填。
    """
    service = (request.POST.get('service') or '').strip()
    channels = [c.strip() for c in request.POST.getlist('channels') if c.strip()]
    channels = list(dict.fromkeys(channels))  # 去重保序
    endpoint = (request.POST.get('endpoint') or '').strip()
    if not service.startswith('/api/'):
        return None, _('请选择 API 服务')
    for channel in channels:
        if not channel.startswith(service.rstrip('/') + '/'):
            return None, _('线路与所选服务不匹配')
    if endpoint:
        if len(channels) != 1:
            return None, _('端点只能归属一条线路，请只选择一条线路')
        if not endpoint.startswith(channels[0].rstrip('/') + '/'):
            return None, _('端点与所选线路不匹配')
        return ('endpoint', [endpoint]), None
    if channels:
        return ('channel', channels), None
    return ('service', [service]), None


def _let_existing_yield(prefixes, keep_policy=None):
    """让已占用这些前缀的原策略「让位」（新策略接管线路）

    - 原策略的前缀全被接管 → 删除该策略（等同于被覆盖）；
    - 只被接管一部分 → 原策略保留剩余线路（必要时把剩余的第一条提升为主前缀）。

    :return: 被删除的策略名列表（供页面提示「原策略已让位」）
    """
    removed = []
    others = ApiServicePolicy.objects.all()
    if keep_policy is not None:
        others = others.exclude(pk=keep_policy.pk)
    for policy in list(others):
        owned = policy.all_prefixes
        remaining = [p for p in owned if p not in prefixes]
        if len(remaining) == len(owned):
            continue
        if not remaining:
            removed.append(policy.name)
            policy.delete()
            continue
        policy.path_prefix = remaining[0]
        policy.extra_prefixes = remaining[1:]
        policy.save(update_fields=['path_prefix', 'extra_prefixes', 'updated_time'])
    return removed


def _policy_form_data(request):
    """读取并校验策略表单，返回 (data, error)；data['apps'] 为白名单项目查询集"""
    name = (request.POST.get('name') or '').strip()
    status = (request.POST.get('status') or '').strip()
    mode = (request.POST.get('auth_mode') or '').strip()
    scope = (request.POST.get('app_scope') or '').strip()
    docs_visible = (request.POST.get('docs_visible') or '').strip()
    audience = (request.POST.get('audience') or '').strip()
    remark = (request.POST.get('remark') or '').strip()
    if not name:
        return None, _('请填写策略名称')
    derived, error = _derive_prefixes(request)
    if error:
        return None, error
    level, prefixes = derived
    if status not in _policy_status_labels():
        return None, _('非法的服务状态')
    if mode not in _policy_mode_labels():
        return None, _('非法的认证模式')
    if scope not in _policy_scope_labels():
        return None, _('非法的项目范围')
    if docs_visible not in _policy_docs_visible_labels():
        return None, _('非法的文档可见性')
    if audience not in _policy_audience_labels():
        return None, _('非法的使用范围')
    # 选中的线路若已被其它策略占用，不报错：由 _let_existing_yield() 让原策略让位
    path_prefix, extra_prefixes = prefixes[0], prefixes[1:]
    try:
        ApiServicePolicy(name=name, level=level, path_prefix=path_prefix,
                         extra_prefixes=extra_prefixes).clean()
    except ValidationError as exc:
        return None, '；'.join(exc.messages)
    app_ids = []
    for raw in request.POST.getlist('apps'):
        try:
            app_ids.append(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
    return {
        'name': name, 'level': level, 'path_prefix': path_prefix,
        'extra_prefixes': extra_prefixes, 'status': status,
        'auth_mode': mode, 'app_scope': scope,
        'docs_visible': docs_visible, 'audience': audience, 'remark': remark,
        'apps': UserApp.objects.filter(pk__in=app_ids),
    }, None


def _notify_yielded(request, yielded):
    """提示哪些原策略因线路被接管而让位"""
    if yielded:
        messages.info(request, _('原策略「%(names)s」的线路已被接管，该策略已让位')
                      % {'names': '、'.join(yielded)})


def _action_create_policy(request):
    data, error = _policy_form_data(request)
    if error:
        messages.error(request, error)
        return redirect('website:console_services')
    apps = data.pop('apps')
    yielded = _let_existing_yield({data['path_prefix'], *data['extra_prefixes']})
    policy = ApiServicePolicy.objects.create(**data)
    policy.apps.set(apps)
    messages.success(request, _('服务策略「%(name)s」已创建') % {'name': policy.name})
    _notify_yielded(request, yielded)
    return redirect('website:console_services')


def _action_edit_policy(request, policy):
    data, error = _policy_form_data(request)
    if error:
        messages.error(request, error)
        return redirect('website:console_services')
    apps = data.pop('apps')
    yielded = _let_existing_yield({data['path_prefix'], *data['extra_prefixes']},
                                  keep_policy=policy)
    for field, value in data.items():
        setattr(policy, field, value)
    policy.save()  # post_save 信号自动使策略缓存失效，改动对接口鉴权立即生效
    policy.apps.set(apps)
    messages.success(request, _('服务策略「%(name)s」已更新') % {'name': policy.name})
    _notify_yielded(request, yielded)
    return redirect('website:console_services')


def _action_toggle_policy(request, policy):
    """启用 / 停用：停用即把状态置为「维护中」（命中请求返回 30004，不做签名校验）"""
    if policy.status == 'maintenance':
        policy.status = 'normal'
        policy.save(update_fields=['status', 'updated_time'])
        messages.success(request, _('服务策略「%(name)s」已启用') % {'name': policy.name})
    else:
        policy.status = 'maintenance'
        policy.save(update_fields=['status', 'updated_time'])
        messages.success(request, _('服务策略「%(name)s」已停用，该服务进入维护态') % {'name': policy.name})
    return redirect('website:console_services')


def _action_delete_policy(request, policy):
    name = policy.name
    policy.delete()
    messages.success(request, _('服务策略「%(name)s」已删除') % {'name': name})
    return redirect('website:console_services')


def _action_delete_policies(request):
    """批量删除：按列表页勾选的主键集合删除；一条都没勾或均为非法值则提示后返回"""
    ids = [raw for raw in request.POST.getlist('ids') if str(raw).isdigit()]
    if not ids:
        messages.error(request, _('请先勾选要删除的服务策略'))
        return redirect('website:console_services')
    queryset = ApiServicePolicy.objects.filter(pk__in=ids)
    deleted = queryset.count()
    queryset.delete()
    messages.success(request, _('已删除 %(n)s 条服务策略') % {'n': deleted})
    return redirect('website:console_services')


# ==================== API 调用统计看板 ====================

# 可选时间范围（天）与默认值；90 天与小时表保留期（HOUR_RETENTION_DAYS）对齐
STATS_RANGES = (7, 30, 90)
STATS_DEFAULT_RANGE = 7
# 失败率页内标记阈值（只在页面上提示，不告警）：≥5% 标黄、≥20% 标红；样本不足不判定
STATS_RATE_WARN = 5
STATS_RATE_DANGER = 20
STATS_MIN_RATE_CALLS = 20
# 热力图 / 矩阵的强度等级数（0 = 无数据，1..4 递增）
STATS_HEAT_LEVELS = 4
# 服务 × 时段矩阵展示的服务条数
STATS_MATRIX_SERVICES = 6


def _parse_days(request):
    """解析 ?days=，非法值回退默认范围"""
    try:
        days = int(request.GET.get('days') or STATS_DEFAULT_RANGE)
    except (TypeError, ValueError):
        days = STATS_DEFAULT_RANGE
    return days if days in STATS_RANGES else STATS_DEFAULT_RANGE


def _service_names():
    """服务前缀 -> 当前语言的服务名（与官网服务清单同源）"""
    return {svc['url_prefix']: _(svc['name']) for svc in SERVICES}


# 扫描器探测路径被统计归并后落到的服务前缀（见 api_stats.UNMATCHED_PATH）
_UNMATCHED_SERVICE = service_of(UNMATCHED_PATH)


def _service_label(prefix, names):
    """服务展示名：清单里没有的前缀（如 /api/）原样展示"""
    if prefix == _UNMATCHED_SERVICE:
        return _('未匹配路径（疑似扫描）')
    return names.get(prefix, prefix)


def _service_url(prefix):
    """服务详情页地址（服务前缀去掉两侧斜杠后作为路径参数）"""
    return reverse('website:console_stats_service', args=[prefix.strip('/')])


def _app_names(app_ids):
    """APPID -> 项目名"""
    ids = [key for key in app_ids if key and key != NO_APP]
    return dict(UserApp.objects.filter(app_id__in=ids).values_list('app_id', 'name'))


def _app_label(app_id, app_names, for_option=False):
    """接入项目显示标签

    统计表是按 app_id 聚合的追加型事实表：项目删掉后历史行仍在，但已经查不到名字。
    这类「已删除项目」在表格里只显示类别（下方另有 app_id 副行，无需重复），
    在筛选下拉里则补上 app_id —— 否则多个已删除项会挤成一批同名选项，无法区分。
    """
    if app_id == NO_APP:
        return _('开放接口 / 未认证')
    name = app_names.get(app_id)
    if name:
        return name
    deleted = _('已删除项目')
    return f'{deleted} · {app_id}' if for_option else deleted


def _rate_level(row):
    """失败率标记等级：样本不足 none / 正常 ok / 偏高 warn / 过高 danger"""
    if row['calls'] < STATS_MIN_RATE_CALLS:
        return 'none'
    if row['failed_rate'] >= STATS_RATE_DANGER:
        return 'danger'
    if row['failed_rate'] >= STATS_RATE_WARN:
        return 'warn'
    return 'ok'


def _mark_rates(rows):
    """给排行行补上失败率标记等级（模板据此上色）"""
    for row in rows:
        row['rate_level'] = _rate_level(row)
    return rows


def _status_rows(days, service=None, app_id=None):
    """状态码分布（说明文案按当前语言翻译）"""
    rows = stats_query.status_code_distribution(days, service=service, app_id=app_id)
    for row in rows:
        row['label'] = _(StatusCode.get_message(row['key']))
    return rows


def _service_rows(rows, names):
    """服务排行行：补服务名与详情页链接"""
    for row in rows:
        row['name'] = _service_label(row['key'], names)
        row['url'] = _service_url(row['key'])
    return rows


def _app_rows(rows, app_names, names):
    """项目排行行：补项目名、详情页链接与主要服务名"""
    for row in rows:
        row['name'] = _app_label(row['key'], app_names)
        row['url'] = reverse('website:console_stats_app', args=[row['key']])
        row['top_service_name'] = _service_label(row.get('top_service') or '', names)
    return rows


def _endpoint_rows(rows, names):
    """接口排行行：补所属服务名（便于一眼看出属于哪个服务）"""
    for row in rows:
        row['service'] = service_of(row['key'])
        row['name'] = _service_label(row['service'], names)
    return rows


def _with_share(rows, total):
    """给排行行补上占区间总量的百分比（模板不能做除法，统一在此算好）"""
    for row in rows:
        row['share'] = round(row['calls'] * 100 / total, 1) if total else 0
    return rows


def _heat_cells(counts, top):
    """一行计数 -> 带强度等级（0-4）的单元格列表，供模板套色阶"""
    if not top:
        return [{'hour': hour, 'calls': 0, 'level': 0} for hour in range(len(counts))]
    step = (STATS_HEAT_LEVELS - 1) / top
    return [{'hour': hour, 'calls': n,
             'level': min(STATS_HEAT_LEVELS, 1 + int(n * step)) if n else 0}
            for hour, n in enumerate(counts)]


def _heatmap_rows(hours):
    """星期 × 小时热力图行（行=星期，列 24 小时，全局同一色阶）"""
    labels = [_('周一'), _('周二'), _('周三'), _('周四'), _('周五'), _('周六'), _('周日')]
    return [{'label': label, 'cells': _heat_cells(counts, hours['heatmap_max'])}
            for label, counts in zip(labels, hours['heatmap'])]


def _matrix_rows(matrix, names):
    """服务 × 时段矩阵行（每个服务单独色阶，突出各自的高峰时段）"""
    rows = []
    for item in matrix:
        top = max(item['hours']) if item['hours'] else 0
        rows.append({
            'name': _service_label(item['service'], names),
            'url': _service_url(item['service']),
            'total': item['total'],
            'cells': _heat_cells(item['hours'], top),
        })
    return rows


def _stats_common(days, service=None, app_id=None):
    """总览与两个详情页共用的取数：指标（含环比）+ 趋势 + 时段 + 状态码 + 峰值日期"""
    overview = stats_query.overview_compare(days, service=service, app_id=app_id)
    hours = stats_query.hour_analysis(days, service=service, app_id=app_id)
    return {
        'days': days,
        'range_choices': STATS_RANGES,
        # 页面说明用的展示文案（带 % 号，避免在 blocktrans 里写裸 % 触发格式化歧义）
        'rate_warn_label': f'{STATS_RATE_WARN}%',
        'rate_danger_label': f'{STATS_RATE_DANGER}%',
        'min_rate_calls': STATS_MIN_RATE_CALLS,
        'overview': overview,
        'trend': stats_query.daily_trend(days, service=service, app_id=app_id),
        'hours': hours,
        'heatmap_rows': _heatmap_rows(hours),
        # 日内高峰时段（24 小时里调用量最大的那一小时）
        'peak_hour': max(hours['profile'], key=lambda item: item['calls']) if hours['peak'] else None,
        'status_codes': _with_share(_status_rows(days, service, app_id), overview['calls']),
        'peak_days': _mark_rates(stats_query.peak_days(days, service=service, app_id=app_id)),
    }


@superadmin_required
def stats_view(request):
    """超管：调用统计总览（?days=7|30|90，可按服务 / 项目筛选）

    数据口径见 API/common/api_stats.py（写入）与 API/common/api_stats_query.py（查询）；
    本视图只取数 + 整理展示字段，图表由本地托管的 Chart.js 绘制。
    """
    days = _parse_days(request)
    service_keys = stats_query.service_keys()
    app_keys = stats_query.app_keys()
    # 只接受出现过的筛选值，避免手改 URL 得到一片空白
    service = (request.GET.get('service') or '').strip()
    service = service if service in service_keys else ''
    app_id = (request.GET.get('app_id') or '').strip()
    app_id = app_id if app_id in app_keys else ''

    names = _service_names()
    app_names = _app_names(app_keys)
    context = _stats_common(days, service or None, app_id or None)
    total = context['overview']['calls']
    context.update({
        'service_choice': service,
        'app_choice': app_id,
        'service_options': sorted(
            ({'value': key, 'label': _service_label(key, names)} for key in service_keys),
            key=lambda item: item['label']),
        'app_options': sorted(
            ({'value': key, 'label': _app_label(key, app_names, for_option=True)} for key in app_keys),
            key=lambda item: item['label']),
        'services': _mark_rates(_with_share(_service_rows(
            stats_query.service_ranking(days, service=service or None,
                                        app_id=app_id or None), names), total)),
        'apps': _mark_rates(_with_share(_app_rows(
            stats_query.app_ranking(days, limit=20, service=service or None,
                                    with_top_service=True), app_names, names), total)),
        'endpoints': _mark_rates(_endpoint_rows(
            stats_query.endpoint_ranking(days, limit=20, service=service or None,
                                         app_id=app_id or None), names)),
        'failed_endpoints': _mark_rates(_endpoint_rows(
            stats_query.endpoint_ranking(days, limit=10, service=service or None,
                                         app_id=app_id or None,
                                         order='failed', min_calls=STATS_MIN_RATE_CALLS), names)),
        'matrix_rows': _matrix_rows(
            stats_query.service_hour_matrix(days, app_id=app_id or None,
                                            top=STATS_MATRIX_SERVICES), names),
    })
    return render(request, 'console/stats.html', context)


@superadmin_required
def stats_service_view(request, service):
    """超管：单个服务的调用统计详情（/console/stats/service/<api/email>/）"""
    days = _parse_days(request)
    prefix = '/' + service.strip('/') + '/'
    names = _service_names()
    context = _stats_common(days, service=prefix)
    context.update({
        'service': prefix,
        'service_name': _service_label(prefix, names),
        'endpoints': _mark_rates(_endpoint_rows(
            stats_query.endpoint_ranking(days, limit=20, service=prefix), names)),
        'apps': _mark_rates(_app_rows(
            stats_query.app_ranking(days, limit=20, service=prefix),
            _app_names(stats_query.app_keys()), names)),
    })
    return render(request, 'console/stats_service.html', context)


@superadmin_required
def stats_app_view(request, app_id):
    """超管：单个接入项目的调用统计详情（/console/stats/app/<APPID>/）"""
    days = _parse_days(request)
    names = _service_names()
    context = _stats_common(days, app_id=app_id)
    context.update({
        'app_id': app_id,
        'app_name': _app_label(app_id, _app_names([app_id])),
        'services': _mark_rates(_service_rows(
            stats_query.service_ranking(days, app_id=app_id), names)),
        'endpoints': _mark_rates(_endpoint_rows(
            stats_query.endpoint_ranking(days, limit=20, app_id=app_id), names)),
    })
    return render(request, 'console/stats_app.html', context)
