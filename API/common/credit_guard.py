"""接入项目额度（点数余额）判定与扣减

**授权模型**：新建项目默认零额度 → 什么都调不了（生效 `auth_mode=open` 的开放接口除外，
它们不校验签名、拿不到调用项目）。有余额才能调接口；余额由超管在控制台手动充值
（暂无支付功能），调用成功后按调用单价扣减。

**调用单价**：由独立的 `ApiPricePolicy`（见 `API/models/Credit/price.py`，控制台
「线路价格」页）管理 —— 与服务策略（状态 / 认证 / 文档可见性 / 使用范围）**完全解耦**。
按「服务 / 线路 / 端点」三级逐级继承（端点覆写线路级 / 服务级），未配置时兜底
`DEFAULT_PRICE`（1 点/次）。解析见本模块 `resolve_price()` / `resolve_price_detail()`。

**扣费时机（仅扣成功调用）**：不逐请求扣，而是跟着调用统计的批量落库走
（进程内缓冲，满 200 条或每 5 秒一次，见 `API/common/api_stats.py`）：落库那一刻按
当时的生效单价算出该批次成功调用的消耗点数，写进统计表的 `cost_points` 列，同时
原子扣减项目余额。上游失败（40001）、参数错误（20001 / 20002）一律不扣费。

**为什么判定是近似值**：扣减滞后于真实用量（缓冲未落库 + 多 worker 各自缓冲），
故判定可能小幅乐观、余额允许短暂为负（欠费），下次充值自动抵扣。
本功能定位是「先充值后使用」的门槛，不作为精确计费依据。

**充值**：`recharge()` 原子加余额并写一条流水（`AppCreditLedger`）。只有充值 / 人工调整
才进流水，逐次扣费不进 —— 否则每秒几十次写会把 SQLite 的单写锁打爆；扣费的事实由
统计表的 `cost_points` 完整记录（按 app 可查累计消耗），两边能对上账。
"""
import logging
import time

from django.conf import settings
from django.db.models import F

logger = logging.getLogger('api.credit')

# 价格表查询的进程内 TTL 缓存（与「服务策略」缓存同款）：
# 后台保存 / 删除单价后由 API/apps.py 的信号立即失效。
_PRICE_CACHE = {'ts': 0.0, 'nodes': []}


def invalidate_api_price_cache():
    """立即失效调用单价缓存（后台改动单价后调用）"""
    _PRICE_CACHE['nodes'] = []
    _PRICE_CACHE['ts'] = 0.0


def _price_nodes():
    """全部显式单价节点（进程内 TTL 缓存）"""
    ttl = getattr(settings, 'API_SERVICE_POLICY_CACHE_TTL', 60)
    now = time.monotonic()
    if _PRICE_CACHE['nodes'] and now - _PRICE_CACHE['ts'] < ttl:
        return _PRICE_CACHE['nodes']
    from API.models.Credit.price import ApiPricePolicy

    nodes = list(ApiPricePolicy.objects.values('path_prefix', 'level', 'price'))
    _PRICE_CACHE['nodes'] = nodes
    _PRICE_CACHE['ts'] = now
    return nodes


def resolve_price_detail(path):
    """某路径的生效单价及其来源

    取命中该路径的最长前缀节点（端点级覆写线路级 / 服务级）；一个都没命中时兜底
    `DEFAULT_PRICE`。返回::

        {'price': Decimal, 'source': 'service'|'channel'|'endpoint'|'default', 'prefix': str}

    path 既可以是真实请求路径，也可以是调用统计里的归一化路径（端点级前缀由
    service_tree 截断到最后一个静态段，普通前缀匹配即可命中）。
    """
    from API.common.middleware import prefix_match
    from API.models.Credit.price import DEFAULT_PRICE

    matched = [node for node in _price_nodes() if prefix_match(path, node['path_prefix'])]
    if matched:
        best = max(matched, key=lambda node: len(node['path_prefix']))
        return {'price': best['price'], 'source': best['level'], 'prefix': best['path_prefix']}
    return {'price': DEFAULT_PRICE, 'source': 'default', 'prefix': ''}


def resolve_price(path):
    """某路径的生效单价（点/次）"""
    return resolve_price_detail(path)['price']


def insufficient(app, price):
    """调用前判定：余额够不够付这一次

    :param app: 已认证的接入项目（`UserApp`）；None（开放接口 / 未认证）时不做判定
    :param price: 本次调用的生效单价（点）
    :return: None 表示放行；不足时返回提示文案
    """
    if app is None or price is None or price <= 0:
        return None
    if app.balance >= price:
        return None
    return (f'额度不足：本次调用需 {price} 点，当前余额 {app.balance} 点，'
            f'请联系管理员充值')


def charge(points_by_app):
    """按项目批量扣减余额（原子更新，允许扣成负数 = 欠费）

    :param points_by_app: {app_id: Decimal 点数}
    :return: 实际扣减的项目数
    """
    from API.models import UserApp

    done = 0
    for app_id, points in points_by_app.items():
        if points <= 0:
            continue
        try:
            UserApp.objects.filter(app_id=app_id).update(balance=F('balance') - points)
            done += 1
        except Exception:
            # 只记日志（少扣而非多扣，对客户友好；统计已落库，可事后核账）
            logger.exception('额度扣减失败: app=%s 点数=%s', app_id, points)
    return done


def recharge(app, amount, operator='', remark=''):
    """给项目充值 / 调整额度：原子加余额并记一条流水

    :param amount: 正数=充值，负数=扣回 / 纠错
    :return: 调整后的余额
    """
    from django.db import transaction

    from API.models import AppCreditLedger, UserApp

    with transaction.atomic():
        UserApp.objects.filter(pk=app.pk).update(balance=F('balance') + amount)
        app.refresh_from_db(fields=['balance'])
        AppCreditLedger.objects.create(
            app=app, amount=amount, balance_after=app.balance,
            operator=operator or '', remark=remark or '',
        )
    return app.balance
