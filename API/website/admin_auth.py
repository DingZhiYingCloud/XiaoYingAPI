"""官网“超级管理员”鉴权工具

规则：仅 Django 超级管理员（python manage.py createsuperuser 创建、
django.contrib.auth.models.User.is_superuser=True）可访问超管功能。
Django 原生后台已关闭；统一在 /login/ 登录，系统自动判断：
  是超管 → 走 Django 超管会话（request.user.is_superuser），前端自动显示超管入口；
  非超管（普通前台用户）→ 走用户中心会话，看不到也用不了超管功能。
未登录/非超管访问超管页面会跳转 /login/，普通用户即便回跳也进不去（防循环：普通登录一律回首页）。
"""
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test

# 未具备超管会话时，跳转统一登录页
ADMIN_LOGIN_PATH = '/login/'


def is_superadmin(user):
    """是否为可用的超级管理员"""
    return bool(user and user.is_authenticated and user.is_superuser and user.is_active)


def superadmin_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME):
    """视图装饰器：非超管一律跳转管理员登录页（带 next 回跳）"""
    actual_decorator = user_passes_test(
        lambda u: is_superadmin(u),
        login_url=ADMIN_LOGIN_PATH,
        redirect_field_name=redirect_field_name,
    )
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator
