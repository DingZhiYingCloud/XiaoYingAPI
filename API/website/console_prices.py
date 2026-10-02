"""超管控制台 - 线路价格

调用单价与服务策略**完全解耦**：本页只管「调一次扣多少点」，服务策略只管
「能不能调」。单价按「服务 / 线路 / 端点」三级逐级继承，兜底 1 点/次
（`DEFAULT_PRICE`），判定与扣费口径见 `API/common/credit_guard.py`。

页面形态：把服务树（真实 Django 路由，见 `service_tree`）**全量列出**为可折叠的
三级结构，每个节点一个价格输入框 —— 留空 = 跟随上级，填了就在该节点建一条
`ApiPricePolicy`；一次提交保存整页（批量），改动立即对接口生效、无需重启。

鉴权：仅 Django is_superuser（见 admin_auth.py）。
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.models import ApiPricePolicy
from API.models.Credit.price import DEFAULT_PRICE

from .admin_auth import notify_success, superadmin_required
from .service_tree import service_tree

REDIRECT_URL = 'website:console_prices'

# 表单字段名前缀：`price::/api/email/`。用 `::` 分隔是因为 URL 前缀里不会出现它，
# 无需 index 配对，后端遍历 POST 即可还原「前缀 -> 输入值」。
FIELD_PREFIX = 'price::'


def _level_of(prefix):
    """由前缀形状推出层级（与 ApiPricePolicy.clean() 的口径一致）；形状非法返回 None"""
    if not prefix.startswith('/api/'):
        return None
    depth = len([seg for seg in prefix.strip('/').split('/') if seg]) - 1
    trailing_slash = prefix.endswith('/')
    if depth == 1 and trailing_slash:
        return 'service'
    if depth == 2:
        return 'channel'
    if depth >= 3 and not trailing_slash:
        return 'endpoint'
    return None


def _known_prefixes(tree):
    """服务树里全部合法前缀（校验提交值，避免写入树外的野前缀）"""
    known = set()
    for svc in tree:
        known.add(svc['prefix'])
        for ch in svc['channels']:
            known.add(ch['prefix'])
            for ep in ch['endpoints']:
                known.add(ep['path'])
    return known


@superadmin_required
def prices_view(request):
    """线路价格页：GET 列出服务树全量节点 + 价格；POST 批量保存"""
    if request.method == 'POST':
        return _save(request)
    return _render(request)


def _render(request):
    tree = service_tree()
    explicit = {row.path_prefix: row.price for row in ApiPricePolicy.objects.all()}
    for svc in tree:
        svc_price = explicit.get(svc['prefix'])
        svc['explicit_price'] = svc_price
        svc['effective_price'] = svc_price if svc_price is not None else DEFAULT_PRICE
        for ch in svc['channels']:
            ch_price = explicit.get(ch['prefix'])
            ch['explicit_price'] = ch_price
            ch['effective_price'] = ch_price if ch_price is not None else svc['effective_price']
            for ep in ch['endpoints']:
                ep_price = explicit.get(ep['path'])
                ep['explicit_price'] = ep_price
                ep['effective_price'] = (ep_price if ep_price is not None
                                         else ch['effective_price'])
    explicit_count = len(explicit)
    return render(request, 'console/prices.html', {
        'tree': tree,
        'default_price': DEFAULT_PRICE,
        'explicit_count': explicit_count,
        'field_prefix': FIELD_PREFIX,
    })


def _save(request):
    """批量保存：留空 = 删除该节点的显式价（恢复跟随上级）；填值 = 建 / 改"""
    known = _known_prefixes(service_tree())
    saved = removed = 0
    bad = []
    for key, raw in request.POST.items():
        if not key.startswith(FIELD_PREFIX):
            continue
        prefix = key[len(FIELD_PREFIX):]
        level = _level_of(prefix)
        if level is None or prefix not in known:
            bad.append(prefix)
            continue
        text = (raw or '').strip()
        if not text:
            removed += ApiPricePolicy.objects.filter(path_prefix=prefix).delete()[0]
            continue
        try:
            value = Decimal(text)
        except (InvalidOperation, ValueError):
            bad.append(prefix)
            continue
        if value < 0:
            bad.append(prefix)
            continue
        obj = ApiPricePolicy(level=level, path_prefix=prefix, price=value)
        try:
            obj.clean()
        except ValidationError:
            bad.append(prefix)
            continue
        ApiPricePolicy.objects.update_or_create(
            path_prefix=prefix, defaults={'level': level, 'price': value})
        saved += 1

    if saved or removed:
        notify_success(request, _('已保存 %(saved)s 条单价、清除 %(removed)s 条')
                       % {'saved': saved, 'removed': removed})
    if bad:
        messages.error(request, _('有 %(n)s 个节点的价格非法或不在服务树内，已跳过')
                       % {'n': len(bad)})
    if not saved and not removed and not bad:
        messages.info(request, _('没有改动'))
    return redirect(REDIRECT_URL)
