"""超管控制台 - 接入项目额度

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/credits/     项目余额列表（可搜索）+ 充值 + 充值流水
    POST /console/credits/     action = recharge（给某个项目充值 / 扣回）

额度是**唯一**的调用门槛：新建项目默认 0 → 什么都调不了（开放接口除外），
有余额才能调接口，调用成功按调用单价扣减（单价在「线路价格」页按
服务 / 线路 / 端点三级配置）。判定与扣费口径见 `API/common/credit_guard.py`。

目前没有支付功能，充值只能由超管在这里手动完成；每笔充值都会写一条流水
（`AppCreditLedger`），同时由 `superadmin_required` 自动落一条控制台操作审计。
"""
import logging
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from API.common import credit_guard
from API.models import AppCreditLedger, UserApp

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.credit')

REDIRECT_URL = 'website:console_credits'

# 流水展示条数上限（只看最近的，需要更早的历史直接查库）
LEDGER_LIMIT = 50


def _app_or_none(raw_id):
    """按主键（UUID）取项目；非法值返回 None（避免 UUID 解析异常冒泡成 500）"""
    try:
        return UserApp.objects.filter(pk=uuid.UUID(str(raw_id))).first()
    except (ValueError, TypeError, AttributeError):
        return None


@superadmin_required
def credits_view(request):
    """额度页：项目余额 + 充值 + 充值流水"""
    if request.method == 'POST':
        return _recharge(request)
    return _render(request)


def _render(request):
    keyword = (request.GET.get('q') or '').strip()
    apps = UserApp.objects.select_related('owner')
    if keyword:
        apps = apps.filter(Q(name__icontains=keyword) | Q(app_id__icontains=keyword))
    ledger = AppCreditLedger.objects.select_related('app')[:LEDGER_LIMIT]
    return render(request, 'console/credits.html', {
        'apps': apps.order_by('name'),
        'keyword': keyword,
        'ledger': ledger,
        'ledger_limit': LEDGER_LIMIT,
        'total': UserApp.objects.count(),
    })


def _recharge(request):
    """给某个项目充值 / 扣回：正数=充值，负数=扣回（两者都写流水）"""
    if (request.POST.get('action') or '').strip() != 'recharge':
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)

    app = _app_or_none(request.POST.get('id'))
    if app is None:
        messages.error(request, _('项目不存在'))
        return redirect(REDIRECT_URL)

    try:
        amount = Decimal((request.POST.get('amount') or '').strip())
    except (InvalidOperation, ValueError):
        messages.error(request, _('金额必须是数字'))
        return redirect(REDIRECT_URL)
    if amount == 0:
        messages.error(request, _('金额不能为 0'))
        return redirect(REDIRECT_URL)
    # 上限兜底：避免误输入把余额撑到溢出（max_digits=16, decimal_places=2）
    if abs(amount) > Decimal('99999999'):
        messages.error(request, _('单次金额过大（上限 99999999）'))
        return redirect(REDIRECT_URL)

    remark = (request.POST.get('remark') or '').strip()[:255]
    operator = str(getattr(request.user, 'username', '') or '')[:150]
    balance = credit_guard.recharge(app, amount, operator=operator, remark=remark)
    act = _('充值') if amount > 0 else _('扣回')
    notify_success(request, _('已为项目「%(name)s」%(act)s %(amount)s 点，当前余额 %(balance)s 点')
                   % {'name': app.name, 'act': act, 'amount': amount, 'balance': balance})
    # 带着搜索词回跳，充值人还能看到刚刚那个项目的当前余额
    return redirect(f'{reverse(REDIRECT_URL)}?q={quote(app.name)}')
