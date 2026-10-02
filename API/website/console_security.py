"""超管控制台 · 安全设置

`/console/security/`：控制台自身的安全开关。

目前只有一项「后台入口隐身」—— 未登录 / 非超管访问 `/console/**` 时返回 404 而不是
跳转登录页，避免被路径探测发现后台入口（见 `admin_auth.superadmin_required`）。

保存走普通 POST + 重定向（与 `console_appearance.py` 同一套路）。
鉴权：仅 Django is_superuser（见 admin_auth.superadmin_required）。
"""
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.models import SecuritySetting

from .admin_auth import notify_success, superadmin_required


@superadmin_required
def security_view(request):
    if request.method == 'POST':
        return _save(request)

    return render(request, 'console/security.html', {
        'setting': SecuritySetting.get_solo(),
    })


def _save(request):
    """保存安全开关

    复选框未勾选时浏览器根本不提交该字段，故用「字段是否出现在 POST 里」判定，
    而不是取它的值（避免「取消勾选后保存仍为开」这种经典坑）。
    """
    setting = SecuritySetting.get_solo()
    setting.hide_console = 'hide_console' in request.POST
    setting.save()
    notify_success(request, _('安全设置已保存'))
    return redirect('website:console_security')
