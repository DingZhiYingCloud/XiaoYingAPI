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
"""
from functools import wraps

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login

from API.common.views import handler404

# 未具备超管会话时，跳转统一登录页
ADMIN_LOGIN_PATH = '/login/'


def is_superadmin(user):
    """是否为可用的超级管理员"""
    return bool(user and user.is_authenticated and user.is_superuser and user.is_active)


def superadmin_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME):
    """视图装饰器：非超管一律跳转管理员登录页（带 next 回跳）

    开启「后台入口隐身」时改为返回 404（复用全站 404 视图，响应体与状态码都和
    访问不存在的地址一致，探测者区分不出来）。默认开启，见 SecuritySetting。

    两种写法都支持：
        @superadmin_required
        @superadmin_required(redirect_field_name='next')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if is_superadmin(request.user):
                return func(request, *args, **kwargs)
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
