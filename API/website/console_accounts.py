"""超管控制台 - 账号管理（通用平台账号 + 登录凭据托管）

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/accounts/   账号列表 + 新增 / 编辑表单
    POST /console/accounts/   action = save（新增 / 编辑）/ delete（删除）/ check（校验凭据）

口径：
    · 一行 = 一个第三方平台账号（知乎 / 小红书 / 微博 / 百家号 / 今日头条 …）；
      「登录凭据（Cookie）」与「密码」**AES 加密落库**，页面与接口均**不回显明文**；
    · 编辑时「登录凭据 / 密码」留空 = **保持原值不变**（避免手滑清空）；
    · 更新凭据后状态重置为「未校验」并记录「最近登录时间」；
    · 「校验」调各平台注册的校验器（`API/common/platform_accounts.py`），结果回写
      `status` / `check_message` / `last_check_time`；未接入校验器的平台不显示该按钮。
"""
import logging

from django.core.exceptions import ValidationError
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from API.common import platform_accounts
from API.models import AccountStatus, Platform, PlatformAccount

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.accounts')

REDIRECT_URL = 'website:console_accounts'


@superadmin_required
def accounts_view(request):
    """账号管理：展示 + 新增 / 编辑 + 删除 + 校验"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save':
            return _save(request)
        if action == 'delete':
            return _delete(request)
        if action == 'check':
            return _check(request)
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)
    return _render(request)


def _render(request):
    supported = set(platform_accounts.supported_platforms())
    # 平台名（模型选项）按当前语言翻译后展示，与「接口公告」等页口径一致
    platform_labels = {value: _(label) for value, label in Platform.choices}
    rows = []
    for record in PlatformAccount.objects.all():
        # 模板据此决定是否渲染「校验」按钮（该平台有没有接入校验器）
        record.check_supported = record.platform in supported
        record.platform_label = platform_labels.get(record.platform, record.platform)
        rows.append(record)
    return render(request, 'console/accounts.html', {
        'rows': rows,
        'total': len(rows),
        'platform_choices': list(platform_labels.items()),
        'supported_platforms': supported,
        'has_credential_count': sum(1 for row in rows if row.has_credential),
    })


def _record_or_none(raw_id):
    """按主键取账号（缺失 / 非法 UUID 一律 None，不抛 500）"""
    raw = (raw_id or '').strip()
    if not raw:
        return None
    try:
        return PlatformAccount.objects.filter(pk=raw).first()
    except (ValidationError, ValueError):
        return None


def _save(request):
    """新增或编辑账号

    「登录凭据」「密码」留空表示**保持原值**：这样编辑备注、改名时不至于把凭据清掉。
    """
    raw_id = (request.POST.get('id') or '').strip()
    platform = (request.POST.get('platform') or '').strip()
    account_name = (request.POST.get('account') or '').strip()
    password = (request.POST.get('password') or '').strip()
    credential = (request.POST.get('credential') or '').strip()
    remark = (request.POST.get('remark') or '').strip()

    if platform not in {value for value, _label in Platform.choices}:
        messages.error(request, _('平台取值非法'))
        return redirect(REDIRECT_URL)
    if not account_name:
        messages.error(request, _('账号标识不能为空'))
        return redirect(REDIRECT_URL)

    if raw_id:
        record = _record_or_none(raw_id)
        if record is None:
            messages.error(request, _('账号不存在'))
            return redirect(REDIRECT_URL)
    else:
        record = PlatformAccount()

    duplicated = PlatformAccount.objects.filter(platform=platform, account=account_name)
    if record.pk:
        duplicated = duplicated.exclude(pk=record.pk)
    if duplicated.exists():
        messages.error(request, _('同一平台下该账号标识已存在'))
        return redirect(REDIRECT_URL)

    credential_changed = bool(credential) or not record.pk
    record.platform = platform
    record.account = account_name
    if password:
        record.password = password
    if credential:
        record.credential = credential
    record.remark = remark
    if credential_changed:
        # 凭据是新录入 / 被替换：状态回到「未校验」，并记一笔「最近登录时间」
        record.status = AccountStatus.UNKNOWN
        record.check_message = ''
        record.last_login_time = timezone.now()
    record.save()

    logger.info('平台账号已保存 platform=%s account=%s operator=%s',
                platform, account_name, request.user.get_username())
    notify_success(request, _('已保存账号「%(name)s」') % {'name': record.account})
    return redirect(REDIRECT_URL)


def _delete(request):
    """删除账号（连带它的凭据一并删除）"""
    record = _record_or_none(request.POST.get('id'))
    if record is None:
        messages.error(request, _('账号不存在'))
        return redirect(REDIRECT_URL)
    label = str(record)
    record.delete()
    logger.info('平台账号已删除 %s operator=%s', label, request.user.get_username())
    notify_success(request, _('已删除账号「%(name)s」') % {'name': label})
    return redirect(REDIRECT_URL)


def _check(request):
    """校验凭据是否仍有效（结果由 platform_accounts.check_account 回写账号表）"""
    record = _record_or_none(request.POST.get('id'))
    if record is None:
        messages.error(request, _('账号不存在'))
        return redirect(REDIRECT_URL)

    ok, message = platform_accounts.check_account(record)
    label = record.account
    if ok:
        notify_success(request, _('「%(name)s」凭据有效：%(msg)s')
                       % {'name': label, 'msg': message})
    else:
        messages.warning(request, _('「%(name)s」凭据校验未通过：%(msg)s')
                         % {'name': label, 'msg': message})
    return redirect(REDIRECT_URL)
