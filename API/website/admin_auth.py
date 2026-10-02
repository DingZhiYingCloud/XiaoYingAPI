"""官网“超级管理员”鉴权工具

规则：仅 Django 超级管理员（python manage.py createsuperuser 创建、
django.contrib.auth.models.User.is_superuser=True）可访问超管功能。
Django 原生后台已关闭；统一在 /login/ 登录，系统自动判断：
  是超管 → 走 Django 超管会话（request.user.is_superuser），前端自动显示超管入口；
  非超管（普通前台用户）→ 走用户中心会话，看不到也用不了超管功能。
未登录/非超管访问超管页面会跳转 /login/，普通用户即便回跳也进不去（防循环：普通登录一律回首页）。

**后台入口隐身**（`SecuritySetting.hide_console`，默认开启，可在 /console/security/ 关掉）：
开启时，未登录 / 非超管访问后台页面**直接返回 404**，而不是 302 跳登录页 ——
302 等于告诉探测者「这个地址存在」，而 404 与访问一个根本不存在的地址表现完全一致，
据此无法判断后台在哪。开启后超管本人也需**先从 /login/ 登录**，再访问后台即可正常进入
（登录成功后首页有「超级管理员」入口）。

**它同时是控制台操作审计的采集点**：所有控制台视图都经 `superadmin_required`，故写操作
（POST/PUT/PATCH/DELETE）在这里统一落 `ConsoleAuditLog` —— 集中一处，新加页面不可能漏记。
视图用 `notify_success()` 提示成功时，那句话会一并作为审计日志的可读说明（见
`API/models/Security/audit.py` 的说明）。
"""
import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login

from API.common.views import handler404

logger = logging.getLogger('api.console')

# 未具备超管会话时，跳转统一登录页
ADMIN_LOGIN_PATH = '/login/'

# 需要审计的请求方法：控制台的写操作都是 POST，PUT/PATCH/DELETE 一并覆盖（将来新增也不用改）
_AUDITED_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


def is_superadmin(user):
    """是否为可用的超级管理员"""
    return bool(user and user.is_authenticated and user.is_superuser and user.is_active)


def notify_success(request, note):
    """给操作者一条成功提示，并把同一句话作为本次操作的审计说明

    两处共用一句话（调用方只写一次），既能保证「日志里的话就是操作者当时看到的话」，
    也避免文案在提示与日志里各写一遍、日后不同步。
    """
    messages.success(request, note)
    request.audit_note = note


def _client_ip(request):
    """来源 IP：优先取 Nginx 透传的 X-Forwarded-For 首段（生产走反代，REMOTE_ADDR 是 127.0.0.1）"""
    forwarded = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()[:45]
    return (request.META.get('REMOTE_ADDR') or '')[:45]


def _record_audit(request, response):
    """把一次控制台写操作落库

    审计写入失败绝不能影响业务（写日志表出错就把管理员的操作卡住是不可接受的），
    故整体兜底：出错只记 error 日志。
    """
    from django.urls import resolve

    from API.models import ConsoleAuditLog

    try:
        try:
            view_name = resolve(request.path_info).url_name or ''
        except Exception:                       # 路由解析失败不影响记录其余字段
            view_name = ''
        ConsoleAuditLog.objects.create(
            operator=str(getattr(request.user, 'username', '') or '')[:64],
            operator_id=getattr(request.user, 'pk', None),
            method=str(request.method)[:8],
            path=str(request.path_info)[:255],
            view_name=str(view_name)[:120],
            action=str(request.POST.get('action') or '')[:64],
            target=str(request.POST.get('id') or '')[:120],
            note=str(getattr(request, 'audit_note', '') or '')[:255],
            status_code=getattr(response, 'status_code', None),
            ip=_client_ip(request),
            user_agent=str(request.META.get('HTTP_USER_AGENT') or '')[:255],
        )
    except Exception:
        logger.exception('控制台操作日志写入失败: %s %s', request.method, request.path_info)


def superadmin_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME):
    """视图装饰器：非超管一律跳转管理员登录页（带 next 回跳）

    开启「后台入口隐身」时改为返回 404（复用全站 404 视图，响应体与状态码都和
    访问不存在的地址一致，探测者区分不出来）。默认开启，见 SecuritySetting。

    超管通过后，写操作（见 `_AUDITED_METHODS`）会落一条操作日志。

    两种写法都支持：
        @superadmin_required
        @superadmin_required(redirect_field_name='next')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if is_superadmin(request.user):
                response = func(request, *args, **kwargs)
                if request.method in _AUDITED_METHODS:
                    _record_audit(request, response)
                return response
            # 延迟导入：避免 admin_auth 在 app 注册完成前就拉起模型
            from API.models import SecuritySetting
            if SecuritySetting.get_solo().hide_console:
                return handler404(request)
            return redirect_to_login(request.get_full_path(), ADMIN_LOGIN_PATH,
                                     redirect_field_name)

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator
