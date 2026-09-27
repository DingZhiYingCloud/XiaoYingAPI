"""超管控制台 - 用户管理（列表 / 详情 / 增删改）

鉴权：仅 Django is_superuser（见 admin_auth.py）；匿名与普通用户会被重定向到 /login/。

页面：
    /console/users/             列表：搜索（账号/用户名/邮箱/手机号）+ 筛选 + 分页，行内封禁/解封
    /console/users/<UUID>/      详情：基本资料、注册信息、按项目分组的登录明细、Token 明细、验证记录时间线

写操作（均为 POST，action 区分；业务校验复用 user_center 的 admin_* 函数，与前台注册同一口径）：
    create / edit / reset_password / ban / unban / delete
    删除需在提交时手工输入该用户账号（服务端二次校验），并级联删除其 Token 与验证记录。

口径（页面文案需与之一致）：
- **累计登录次数** = `user_login_log` 行数。每次登录成功即写一条，退出登录与重置密码都不会
  减少；该表自本次改造起开始记录，改造之前的历史登录无法回填。
- **当前有效登录** = 未过期的 `user_token` 行数（登录态；退出登录、重置密码、封禁会使其失效）。
- **剩余有效天数** = 该项目下最近一次签发的 Token 距今的剩余天数（不足 1 天按 0 显示）。
- 用户是全局用户池（不属于任何项目），「在哪个项目」只能由登录记录得出。
"""
import math

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from API.apis.user_center.users.utils import (
    METHOD_EMAIL, METHOD_PHONE, SCENE_REGISTER,
    admin_create_user, admin_reset_password, admin_update_user,
)
from API.models import User, UserApp, UserLoginLog, UserToken, UserVerifyRecord

from .admin_auth import superadmin_required

# 列表分页
PAGE_SIZE_CHOICES = (20, 50, 100)
PAGE_SIZE_DEFAULT = 20
# 详情页验证记录时间线最多展示条数
VERIFY_TIMELINE_LIMIT = 50

# 验证场景 / 验证方式 / 登录方式的展示文案（中文源语言，渲染时翻译）
_SCENE_LABELS = {
    'register': '注册验证',
    'login': '登录验证码',
    'reset': '重置密码',
    'verify': '验证',
}
_TYPE_LABELS = {METHOD_EMAIL: '邮箱', METHOD_PHONE: '手机号'}
_LOGIN_METHOD_LABELS = dict(UserLoginLog.METHOD_CHOICES)

# 列表状态筛选取值 -> user.status
_STATUS_FILTERS = {'normal': True, 'banned': False}


# ==================== 通用取数 ====================

def _parse_page_size(request):
    """解析 ?size=，非法值回退默认每页条数"""
    try:
        size = int(request.GET.get('size') or PAGE_SIZE_DEFAULT)
    except (TypeError, ValueError):
        size = PAGE_SIZE_DEFAULT
    return size if size in PAGE_SIZE_CHOICES else PAGE_SIZE_DEFAULT


def _filtered_users(request):
    """用户列表查询集（搜索 + 状态 / 注册方式 / 登录项目筛选）

    注册方式与登录项目走子查询（IN 一批 user_id），避免 JOIN 造成重复行；
    显式 order_by('-create_time')：annotate 聚合会带上 GROUP BY，
    此时 Django 不再套用 Meta.ordering（分页会得到不稳定的顺序）。
    """
    keyword = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    register_type = (request.GET.get('register_type') or '').strip()
    app_id = (request.GET.get('app_id') or '').strip()

    users = User.objects.order_by('-create_time')
    if keyword:
        users = users.filter(
            Q(account__icontains=keyword) | Q(username__icontains=keyword)
            | Q(email__icontains=keyword) | Q(phone__icontains=keyword))
    if status in _STATUS_FILTERS:
        users = users.filter(status=_STATUS_FILTERS[status])
    if register_type in _TYPE_LABELS:
        users = users.filter(id__in=UserVerifyRecord.objects.filter(
            scene=SCENE_REGISTER, type=register_type).values('user_id'))
    if app_id:
        # app_id 传的是项目对外标识（app_ 前缀），不是外键 UUID，故按 app__app_id 过滤
        users = users.filter(id__in=UserLoginLog.objects.filter(
            app__app_id=app_id).values('user_id'))
    return users


def _with_login_stats(users):
    """给用户补登录统计：累计登录次数 / 登录过的项目数 / 当前有效登录数 / 最后登录时间

    distinct=True 消除「登录日志 × Token」两条聚合链 JOIN 造成的行放大。
    """
    now = timezone.now()
    return users.annotate(
        login_total=Count('login_logs', distinct=True),
        login_projects=Count('login_logs__app', distinct=True),
        active_tokens=Count('tokens', filter=Q(tokens__expire_time__gt=now), distinct=True),
        last_login=Max('login_logs__create_time'),
    )


def _days_left(expire_time):
    """剩余有效天数（向上取整到天，已过期或不足 1 天返回 0）"""
    if not expire_time:
        return 0
    seconds = (expire_time - timezone.now()).total_seconds()
    return max(0, math.ceil(seconds / 86400))


def _token_state(token, user):
    """Token 当前状态：返回 (语义等级, 展示文案)

    等级供模板判断徽标样式；文案已按当前语言翻译。
    账号封禁 / 项目停用优先于过期——这两种情况下 Token 即使未到期也不可用。
    """
    now = timezone.now()
    if not user.status:
        return 'banned', _('账号已封禁')
    if not token.app.status:
        return 'disabled', _('项目已停用')
    if token.expire_time and now >= token.expire_time:
        return 'expired', _('已过期')
    return 'valid', _('有效')


def _register_info(user):
    """注册信息：注册方式 / 注册来源项目（来自该用户的注册验证记录）

    注册验证记录可能有多条（同一次注册同时绑定邮箱与手机号 → 合并为同一账号），
    因此方式与项目都按去重集合展示；历史记录没有发起项目（app 为空）。
    """
    records = (UserVerifyRecord.objects.filter(user=user, scene=SCENE_REGISTER)
               .select_related('app').order_by('create_time'))
    types, apps, has_unknown = [], {}, False
    for record in records:
        label = _(_TYPE_LABELS.get(record.type, record.type))
        if label not in types:
            types.append(label)
        if record.app_id:
            apps[str(record.app_id)] = record.app.name
        else:
            has_unknown = True
    return {
        'records': records,
        'methods': types,
        'apps': list(apps.values()),
        'has_unknown_app': has_unknown,
    }


def _project_logins(user):
    """按项目聚合的登录明细（登录次数 / 其中验证码登录次数 / 首次与最后登录 / Token 状态）

    同一用户在同一项目可能有多条 Token（每次登录新建一条），因此额外合并
    「当前有效登录数」与「最近一次签发 Token 的过期时间」，用于展示剩余有效天数。
    """
    rows = (UserLoginLog.objects.filter(user=user)
            .values('app_id', 'app__name', 'app__app_id', 'app__status', 'app__token_expire_days')
            .annotate(total=Count('id'),
                      code_total=Count('id', filter=Q(method=UserLoginLog.METHOD_CODE)),
                      first_login=Min('create_time'),
                      last_login=Max('create_time'))
            .order_by('-total'))
    tokens = (UserToken.objects.filter(user=user).values('app_id')
              .annotate(valid_total=Count('id', filter=Q(expire_time__gt=timezone.now())),
                        latest_expire=Max('expire_time'),
                        last_active=Max('last_active_time')))
    token_map = {row['app_id']: row for row in tokens}

    now = timezone.now()
    result = []
    for row in rows:
        token = token_map.get(row['app_id'], {})
        expire = token.get('latest_expire')
        result.append({
            'app_id': row['app__app_id'],
            'app_name': row['app__name'],
            'app_enabled': row['app__status'],
            'expire_days': row['app__token_expire_days'],
            'total': row['total'],
            'code_total': row['code_total'],
            'password_total': row['total'] - row['code_total'],
            'first_login': row['first_login'],
            'last_login': row['last_login'],
            'last_active': token.get('last_active'),
            'valid_total': token.get('valid_total', 0),
            'expire_time': expire,
            'expired': bool(expire and now >= expire),
            'days_left': _days_left(expire),
        })
    return result


def _tokens(user):
    """Token 明细（最近签发在前）"""
    rows = []
    for token in UserToken.objects.filter(user=user).select_related('app').order_by('-create_time'):
        level, label = _token_state(token, user)
        rows.append({
            'app_name': token.app.name,
            'app_id': token.app.app_id,
            'create_time': token.create_time,
            'expire_time': token.expire_time,
            'last_active': token.last_active_time,
            'expired': token.expire_time <= timezone.now(),
            'days_left': _days_left(token.expire_time),
            'state_level': level,
            'state_label': label,
        })
    return rows


def _verify_timeline(user):
    """验证记录时间线（注册 / 登录验证码 / 重置密码 / 验证）"""
    rows = []
    records = (UserVerifyRecord.objects.filter(user=user).select_related('app')
               .order_by('-create_time')[:VERIFY_TIMELINE_LIMIT])
    for record in records:
        rows.append({
            'scene': _(_SCENE_LABELS.get(record.scene, record.scene)),
            'method': _(_TYPE_LABELS.get(record.type, record.type)),
            'credential': record.credential,
            'app_name': record.app.name if record.app_id else '',
            'created': record.create_time,
            'expire_time': record.expire_time,
            'is_used': record.is_used,
        })
    return rows


def _recent_logs(user, limit=20):
    """最近登录记录（含登录方式、IP 与客户端）"""
    rows = []
    logs = (UserLoginLog.objects.filter(user=user).select_related('app')
            .order_by('-create_time')[:limit])
    for log in logs:
        rows.append({
            'created': log.create_time,
            'app_name': log.app.name,
            'method': _(_LOGIN_METHOD_LABELS.get(log.method, log.method)),
            'ip': log.ip,
            'user_agent': log.user_agent,
        })
    return rows


# ==================== 列表页 ====================

@superadmin_required
def users_view(request):
    """超管：用户列表（搜索 / 筛选 / 分页）与写操作入口"""
    if request.method == 'POST':
        return _handle_user_action(request)

    users = _with_login_stats(_filtered_users(request))
    paginator = Paginator(users, _parse_page_size(request))
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'console/users.html', {
        'page_obj': page,
        'paginator': paginator,
        'total': paginator.count,
        'keyword': (request.GET.get('q') or '').strip(),
        'status_filter': (request.GET.get('status') or '').strip(),
        'register_type': (request.GET.get('register_type') or '').strip(),
        'app_filter': (request.GET.get('app_id') or '').strip(),
        'page_size': _parse_page_size(request),
        'size_choices': PAGE_SIZE_CHOICES,
        'register_type_options': [('email', _('邮箱注册')), ('phone', _('手机号注册'))],
        'apps': UserApp.objects.order_by('name'),
        'page_prefix': _page_prefix(request),
    })


def _page_prefix(request):
    """分页链接前缀：当前筛选参数 + 结尾 '&'（无参数时为空串），供 ?{{ page_prefix }}page=N"""
    params = request.GET.copy()
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{encoded}&' if encoded else ''


# ==================== 详情页 ====================

@superadmin_required
def user_detail_view(request, user_id):
    """超管：单个用户的详细资料与登录明细"""
    user = get_object_or_404(User, pk=user_id)
    logs = UserLoginLog.objects.filter(user=user)
    aggregate = logs.aggregate(total=Count('id'), projects=Count('app_id', distinct=True),
                               last=Max('create_time'))
    register = _register_info(user)
    return render(request, 'console/user_detail.html', {
        'target': user,
        'summary': {
            'login_total': aggregate['total'] or 0,
            'login_projects': aggregate['projects'] or 0,
            'last_login': aggregate['last'],
            'active_tokens': UserToken.objects.filter(
                user=user, expire_time__gt=timezone.now()).count(),
        },
        'register': register,
        'logs_by_app': _project_logins(user),
        'tokens': _tokens(user),
        'verify_rows': _verify_timeline(user),
        'verify_limit': VERIFY_TIMELINE_LIMIT,
        'recent_logs': _recent_logs(user),
    })


# ==================== 写操作 ====================

def _handle_user_action(request):
    """处理用户写操作（action 区分），成功后回到来源页"""
    action = (request.POST.get('action') or '').strip()

    if action == 'create':
        return _action_create(request)
    user = _target_or_none(request)
    if user is None:
        messages.error(request, _('用户不存在'))
        return redirect('website:console_users')

    if action == 'edit':
        return _action_edit(request, user)
    if action == 'reset_password':
        return _action_reset_password(request, user)
    if action in ('ban', 'unban'):
        return _action_set_status(request, user, action == 'ban')
    if action == 'delete':
        return _action_delete(request, user)

    messages.error(request, _('不支持的操作'))
    return redirect('website:console_users')


def _target_or_none(request):
    user_id = (request.POST.get('user_id') or '').strip()
    return User.objects.filter(pk=user_id).first() if user_id else None


def _redirect_after(request, user):
    """写操作后回跳：优先回来源页（next，仅允许站内地址），否则回该用户详情页"""
    next_url = (request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('website:console_user_detail', user_id=user.pk)


def _action_create(request):
    ok, result = admin_create_user(
        email=request.POST.get('email'), phone=request.POST.get('phone'),
        password=request.POST.get('password'), username=request.POST.get('username'))
    if not ok:
        messages.error(request, result)
        return redirect('website:console_users')
    messages.success(request, _('用户创建成功：账号 %(account)s（请转告用户，账号与密码即可登录）')
                     % {'account': result.account})
    return redirect('website:console_user_detail', user_id=result.pk)


def _action_edit(request, user):
    ok, result = admin_update_user(
        user, username=request.POST.get('username'),
        email=request.POST.get('email'), phone=request.POST.get('phone'))
    if not ok:
        messages.error(request, result)
    elif not result:
        messages.info(request, _('资料未发生变化'))
    else:
        messages.success(request, _('资料已更新（换绑的邮箱/手机号需用户重新验证后才能用于登录）'))
    return _redirect_after(request, user)


def _action_reset_password(request, user):
    ok, result = admin_reset_password(user, request.POST.get('password'))
    if not ok:
        messages.error(request, result)
    else:
        messages.success(request, _('密码已重置，该用户全部项目的登录态已作废，需重新登录'))
    return _redirect_after(request, user)


def _action_set_status(request, user, banned):
    user.status = not banned
    user.save(update_fields=['status', 'updated_time'])
    if banned:
        messages.success(request, _('已封禁「%(account)s」：该用户所有项目都无法登录')
                         % {'account': user.account})
    else:
        messages.success(request, _('已解封「%(account)s」') % {'account': user.account})
    return _redirect_after(request, user)


def _action_delete(request, user):
    if (request.POST.get('confirm_account') or '').strip() != user.account:
        messages.error(request, _('删除已取消：输入的账号与原账号不一致'))
        return redirect('website:console_user_detail', user_id=user.pk)
    account = user.account
    user.delete()  # 级联删除该用户的 Token、验证记录、登录日志
    messages.success(request, _('用户「%(account)s」已删除（含其 Token、验证记录与登录日志）')
                     % {'account': account})
    return redirect('website:console_users')
