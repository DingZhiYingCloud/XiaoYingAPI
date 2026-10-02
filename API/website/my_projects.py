"""前台「我的项目」—— 接入方自助管理自己的接入项目

页面：
    GET  /my/projects/                 我的项目列表（含额度余额）
    POST /my/projects/                 action=create 自助创建项目（自动归属于当前用户）
    GET  /my/projects/<uuid>/          项目详情（APPID / APPSECRET / 额度 / 重置密钥）
    POST /my/projects/<uuid>/          action=reset_secret 重置 APPSECRET

鉴权：走官网会话（`views._current_user` 读的 session 登录态），未登录跳 `/login/?next=`。

**归属隔离**：所有查询都以 `owner=当前用户` 过滤，别人的项目一律 404 —— 不靠前端隐藏，
服务端硬隔离。`owner` 为空的项目（平台自有 / 存量项目）不会出现在任何人的列表里，
仍由超管在控制台管理。

**额度**：新建项目默认零额度，余额由超管在控制台充值；客户只能**看**余额，**不能自己改**。
判定与扣费口径见 `API/common/credit_guard.py`。
"""
import logging
from functools import wraps
from urllib.parse import quote

from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from API.common import api_stats_query as stats_query
from API.models import User, UserApp

from .views import _current_user

logger = logging.getLogger(__name__)

# 应用名称长度上限（与 UserApp.name 的 max_length 一致）
NAME_MAX_LENGTH = 100


def _current_app_user(request):
    """当前登录的业务用户（未登录返回 None；已封禁用户视为未登录）"""
    session = _current_user(request)
    user_id = (session or {}).get('user_id')
    if not user_id:
        return None
    return User.objects.filter(pk=user_id, status=True).first()


def login_required(view):
    """要求官网登录：未登录跳登录页并带 next 回跳；已登录则把用户对象传给视图"""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = _current_app_user(request)
        if user is None:
            return redirect(f'{reverse("website:login")}?next={quote(request.get_full_path())}')
        return view(request, user, *args, **kwargs)
    return wrapper


def _my_app_or_404(user, app_id):
    """取当前用户名下的项目：不属于本人（或不存在）一律 404，不泄露"该 ID 是否存在" """
    return get_object_or_404(UserApp, pk=app_id, owner=user)


@login_required
def projects_view(request, user):
    """我的项目：列表 + 自助创建"""
    if request.method == 'POST':
        return _create(request, user)

    return render(request, 'my_projects/list.html', {
        'apps': UserApp.objects.filter(owner=user),
    })


def _create(request, user):
    """自助创建项目：名称唯一即可，APPID / APPSECRET 由模型自动生成"""
    if (request.POST.get('action') or '').strip() != 'create':
        messages.error(request, _('不支持的操作'))
        return redirect('website:my_projects')

    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, _('请填写应用名称'))
        return redirect('website:my_projects')
    if len(name) > NAME_MAX_LENGTH:
        messages.error(request, _('应用名称过长（最多 %(n)s 个字符）') % {'n': NAME_MAX_LENGTH})
        return redirect('website:my_projects')

    try:
        app = UserApp.objects.create(name=name, owner=user)
    except IntegrityError:
        messages.error(request, _('应用名称已被占用，请更换'))
        return redirect('website:my_projects')

    messages.success(request, _('项目「%(name)s」创建成功，请到详情页保存你的 APPSECRET')
                     % {'name': app.name})
    return redirect('website:my_project_detail', app_id=app.pk)


@login_required
def project_detail_view(request, user, app_id):
    """项目详情（APPID / APPSECRET / 额度）+ 重置密钥"""
    app = _my_app_or_404(user, app_id)
    if request.method == 'POST':
        return _reset_secret(request, user, app)

    return render(request, 'my_projects/detail.html', {
        'app': app,
        'total_calls': stats_query.app_total_calls(app.app_id),
    })


def _reset_secret(request, user, app):
    """重置 APPSECRET（旧密钥立即失效）"""
    if (request.POST.get('action') or '').strip() != 'reset_secret':
        messages.error(request, _('不支持的操作'))
        return redirect('website:my_project_detail', app_id=app.pk)

    app.reset_secret()
    logger.info('接入项目 %s 的 APPSECRET 被重置（owner=%s）', app.app_id, user.pk)
    messages.warning(request, _('APPSECRET 已重置：旧密钥立即失效，请马上更新你服务端的配置'))
    return redirect('website:my_project_detail', app_id=app.pk)
