"""代练搬单 order_migration 业务层

两条职责：
1. **参数映射**：把「代练通」王者荣耀公开订单映射为「代练丸子」商家版发单参数。
2. **流水线编排**：抓单 → 发单（丸子）→ 监控「被接单」→ 代练通接单取账号 → 失败兜底撤单。

映射口径（与需求约定一致）：
    - 代练丸子固定发「王者荣耀 / 排位」
    - 区服（客户端）按代练通订单的 Zone 映射
    - 标题原样照搬代练通订单标题，不做解析
    - 发布价 = (代练通价 - 代练通手续费) × 80%
    - 双金（安全 / 效率保证金合计）= 发布价 × 双金倍数（后台可配，默认 2），两项均分

注意：编排里的「发单 / 接单 / 撤单」是**真实写操作**（涉及资金），命令行提供 --dry-run
只做「抓单 + 映射」，真实运行前请务必用 dry-run 核对。
"""
import json
import logging
import os
import random
import threading
import time
from typing import Tuple

logger = logging.getLogger('api.order_migration')

# 代练通大区 -> 代练丸子 region_name（「客户端」以代练通订单为准）
ZONE_MAP = {
    '安卓QQ': '安卓QQ',
    '苹果QQ': '苹果QQ',
    '安卓WX': '安卓微信',
    '苹果WX': '苹果微信',
}

# 代练丸子固定参数（当前只做王者荣耀排位）
GAME_ID = '1'
LEVELING_TYPE_NAME = '排位'

# 丸子发布价 = 净收入 × 80%（留 20% 差价）
PROFIT_RATIO = 0.8
# 双金倍数的允许范围（后台可配，默认 2）
DEPOSIT_RATIO_MIN, DEPOSIT_RATIO_MAX = 0, 5
DEFAULT_DEPOSIT_RATIO = 2


def dlt_cost(price) -> int:
    """代练通王者·代练区·公共频道手续费（元）

    阶梯（见代练通《收费标准》，公开单即公共频道，王者公共频道与优选频道同价）：
        p < 20            → 1
        20 ≤ p < 50       → 4
        50 ≤ p            → 5 + floor((p - 50) / 50)，封顶 20

    :param price: 代练通订单金额（元）
    :return: 手续费（元，整数）
    """
    value = float(price)
    if value < 20:
        return 1
    if value < 50:
        return 4
    return min(20, 5 + int((value - 50) // 50))


def recommended_amount(price) -> float:
    """代练丸子发布价 = (代练通价 - 手续费) × 80%，保留 2 位小数"""
    return round((float(price) - dlt_cost(price)) * PROFIT_RATIO, 2)


def deposit_ratio() -> int:
    """双金倍数（后台可配，0-5，默认 2）

    语义：丸子双金**合计**（安全保证金 + 效率保证金）= 发布价 × 该倍数。
    越界或异常时回落到默认值，避免脏配置导致发单失败。
    """
    try:
        value = int(_setting().deposit_ratio)
    except (TypeError, ValueError):
        return DEFAULT_DEPOSIT_RATIO
    return min(DEPOSIT_RATIO_MAX, max(DEPOSIT_RATIO_MIN, value))


def deposits(amount) -> Tuple[float, float]:
    """双金（安全保证金, 效率保证金）：两项均分「发布价 × 双金倍数」"""
    each = round(float(amount) * deposit_ratio() / 2, 2)
    return each, each


def map_order(title, price, zone, time_limit) -> Tuple[bool, dict | str]:
    """代练通订单字段 → 代练丸子发单业务参数

    :param title: 代练通订单标题（原样照搬）
    :param price: 代练通订单金额（元）
    :param zone: 代练通大区（如 安卓QQ / 苹果WX）
    :param time_limit: 代练通订单时限（小时）
    :return: (True, 丸子发单参数 dict) 或 (False, 错误说明)
    """
    title = (title or '').strip()
    zone_name = (zone or '').strip()
    if not title:
        return False, '订单标题不能为空'
    region_name = ZONE_MAP.get(zone_name)
    if not region_name:
        return False, f"暂不支持的大区: {zone_name or '(空)'}（支持 {'/'.join(ZONE_MAP)}）"
    try:
        price_value = float(price)
        hours = int(float(time_limit))
    except (TypeError, ValueError):
        return False, '价格 / 时限必须为数值'
    if price_value <= 0:
        return False, '订单价格必须大于 0'
    if hours <= 0:
        return False, '订单时限必须大于 0'

    amount = recommended_amount(price_value)
    if amount <= 0:
        return False, '按规则计算的发布价不大于 0，无法发布'
    security, efficiency = deposits(amount)

    return True, {
        'game_id': GAME_ID,
        'leveling_type_name': LEVELING_TYPE_NAME,
        'region_name': region_name,
        'title': title,
        'hour': hours,
        'amount': amount,
        'security_deposit': security,
        'efficiency_deposit': efficiency,
        # 计算依据，便于核对成本与差价
        'dlt_price': round(price_value, 2),
        'dlt_cost': dlt_cost(price_value),
    }


# ==================== 流水线编排 ====================
# 抓单（代练通）→ 映射 → 发单（代练丸子）→ 监控「被接单」→ 代练通接单取账号 → 失败兜底撤单
# 发单 / 接单 / 撤单是真实写操作（涉及资金），务必先用 dry-run 核对。

# 代练通王者荣耀
DLT_GAME_ID = 107

# 代练通订单状态：只有「未接手」才表示我们还能接；其它（12 正在代练 / 16 撤销中 / 17 已结算…）都不行
DLT_STATUS_WAITING = 11

# 代练通状态展示名（监控日志用，只列常见几种）
DLT_STATUS_TEXT = {
    11: '未接手（可接）', 12: '正在代练', 13: '等待验收',
    14: '订单异常', 15: '锁定订单', 16: '申请撤销中', 17: '已结算',
}


def dlt_status_text(status):
    """代练通状态的展示名（未知状态原样返回数字）"""
    return DLT_STATUS_TEXT.get(status, f'状态{status}')


# 运行配置：以后台「代练搬单」页面的设置为准，.env 仅作兜底默认
QQ_ENV = 'ORDER_MIGRATION_QQ'                 # 我们的 QQ 号（填入账号 / 联系方式，引导打手加好友）
INTERVAL_ENV = 'ORDER_MIGRATION_INTERVAL'     # 轮询间隔秒，默认 20
PRICE_MIN_ENV = 'ORDER_MIGRATION_PRICE_MIN'   # 只搬 >= 该价的单（留空 = 不限）
PRICE_MAX_ENV = 'ORDER_MIGRATION_PRICE_MAX'   # 只搬 <= 该价的单（留空 = 不限）


def _env(name, default=''):
    return (os.getenv(name) or default).strip()


def _setting():
    """搬单运行设置单例（后台「代练搬单」页可配；.env 仅作兜底默认）"""
    from API.models import OrderMigrationSetting
    return OrderMigrationSetting.get_solo()


def _num_or_none(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def our_qq() -> str:
    """我们的 QQ 号（页面配置优先，回落 .env）"""
    return (_setting().our_qq or _env(QQ_ENV)).strip()


def interval_seconds() -> int:
    """轮询间隔（秒），最小 5；「被接单」检测的最坏延迟即此值"""
    value = _setting().interval_seconds or _num_or_none(_env(INTERVAL_ENV, '20')) or 20
    return max(5, int(value))


def cycle_publish_limit() -> int:
    """每轮最多发布多少条"""
    return max(0, int(_setting().publish_limit or 1))


def _price_bounds():
    """价格区间：页面配置优先；页面两项都空时回落 .env"""
    setting = _setting()
    if setting.price_min is None and setting.price_max is None:
        return _num_or_none(_env(PRICE_MIN_ENV)), _num_or_none(_env(PRICE_MAX_ENV))
    return setting.price_min, setting.price_max


def _keyword() -> str:
    """标题关键词过滤（页面配置；留空 = 不限）"""
    return (_setting().keyword or '').strip()


def blacklist_words():
    """标题黑名单词表（独立表，后台可逐条增删；标题命中任意一个词就不搬运）

    出处：这类标题（联系/看要求/勿扰/俱乐部…）发到丸子有被判定成「公告」的嫌疑。
    """
    from API.models import OrderMigrationBlacklist

    return [w for w in OrderMigrationBlacklist.objects.values_list('word', flat=True) if w]


def alert(message: str):
    """告警（当前落日志；后续可扩展为通知渠道）"""
    logger.error('[代练搬单] %s', message)


def _dig(obj, key):
    """在嵌套 dict 中递归查找第一个 key（上游响应嵌套层级不稳定时用）"""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _dig(value, key)
            if found is not None:
                return found
    return None


def _brief(value, limit=200):
    """把上游响应 / 异常压成一行可读说明（dict 取 message/msg，避免整串 Python repr）"""
    if isinstance(value, dict):
        value = value.get('message') or value.get('msg') or value
    return str(value)[:limit]


def _fetch_dlt_orders(keyword='', page_size=100):
    """抓取代练通王者订单：合并「公开单池」与「搜索池」，按单号去重

    实测两个接口的订单池不一致，需合并才能覆盖完整：
    - `get_game_orders`（IsPub=1）：常规公开订单池
    - `search_orders(is_pub=0)`：含「指定单 / 自定义发布(LevelType2=14)」等，普通池里拿不到

    `keyword` 会作为上游 `SearchStr` 下发（代练通支持按**订单号或标题**搜），
    这是精确命中某笔单最可靠的方式；留空则返回各池全量。
    任一路失败不影响另一路；两路都失败才报错。
    :return: (orders, errors)
    """
    from API.apis.DaiLianTong import utils as dlt_utils

    fetches = (
        lambda: dlt_utils.get_game_orders(game_id=DLT_GAME_ID, page=1, page_size=page_size,
                                          filter_type=0, search_str=keyword),
        lambda: dlt_utils.search_orders(game_id=DLT_GAME_ID, search_str=keyword, is_pub=0, pg_type=0,
                                        filter_type=0, page=1, page_size=20),
    )
    orders, seen, errors = [], set(), []
    for fetch in fetches:
        ok, result = fetch()
        if not ok:
            errors.append(str(result))
            continue
        for item in ((result.get('data') or {}).get('items') or []):
            serial = str(item.get('SerialNo') or '').strip()
            if serial and serial not in seen:
                seen.add(serial)
                orders.append(item)
    return orders, errors


def fetch_candidates(page_size=100):
    """抓取代练通王者荣耀订单并映射为丸子发单参数

    合并「公开单池 + 搜索池」（见 `_fetch_dlt_orders`），不按订单类型过滤。
    价格区间 / 关键词由设置控制（留空 = 不限）；关键词会透传给上游搜索，
    可填**订单号**或标题里的独特文字来精确只搬某笔单。
    只返回映射成功且未搬运过的候选。
    :return: (True, [candidate, ...]) 或 (False, 错误说明)
    """
    from API.models import OrderMigration

    keyword = _keyword()
    items, errors = _fetch_dlt_orders(keyword=keyword, page_size=page_size)
    if not items and errors:
        return False, '；'.join(errors)

    price_min, price_max = _price_bounds()
    words = blacklist_words()
    known = set(OrderMigration.objects.values_list('dlt_serial_no', flat=True))

    candidates = []
    for item in items:
        serial = str(item.get('SerialNo') or '').strip()
        if not serial or serial in known:
            continue
        title = item.get('Title') or ''
        # 标题黑名单：命中任意一个词就跳过（这类标题像公告，发到丸子有被判定公告的嫌疑）
        hit = next((w for w in words if w in title), '')
        if hit:
            logger.info('[代练搬单] 标题命中黑名单「%s」，跳过 %s：%s', hit, serial, title)
            continue
        # 关键词可匹配订单号或标题（上游已按它搜索，这里再兜一层本地过滤）
        if keyword and keyword not in title and keyword not in serial:
            continue
        try:
            price = float(item.get('Price'))
        except (TypeError, ValueError):
            continue
        if price_min is not None and price < price_min:
            continue
        if price_max is not None and price > price_max:
            continue
        ok_map, mapped = map_order(title, price, item.get('Zone'), item.get('TimeLimit'))
        if not ok_map:
            continue
        try:
            ensure = float(item.get('Ensure') or 0)
        except (TypeError, ValueError):
            ensure = 0.0
        mapped.update({'dlt_serial_no': serial,
                       'dlt_zone': (item.get('Zone') or '').strip(),
                       'dlt_time_limit': item.get('TimeLimit'),
                       'dlt_ensure': round(ensure, 2)})
        candidates.append(mapped)
    return True, candidates


def publish_candidate(candidate, dry_run=False):
    """把一条候选发布到丸子并落库

    先落库（`发单中`）再发单：即使发单成功后进程崩溃、来不及回填丸子单号，
    本地也已留下含**代练通单号**的记录 —— 重启时由 `reconcile_on_startup` 找回丸子单号。

    :return: dry_run 时 (True, 预览 dict)；真实发单时 (True, 记录) 或 (False, 记录/错误说明)
    """
    from API.models import MigrationStatus, OrderMigration

    serial = candidate['dlt_serial_no']
    if dry_run:
        return True, {'dry_run': True, 'dlt_serial_no': serial, 'title': candidate['title'],
                      'region_name': candidate['region_name'], 'hour': candidate['hour'],
                      'amount': candidate['amount'],
                      'security_deposit': candidate['security_deposit'],
                      'efficiency_deposit': candidate['efficiency_deposit']}

    qq = our_qq()
    if not qq:
        return False, f'未配置 {QQ_ENV}（我们的 QQ 号），无法发单'

    # ① 先落库：占位为「发单中」，把代练通单号等关键信息先记下来
    record, _ = OrderMigration.objects.update_or_create(
        dlt_serial_no=serial,
        defaults={
            'dlt_title': candidate['title'][:255],
            'dlt_price': candidate['dlt_price'],
            'dlt_zone': candidate['dlt_zone'],
            'dlt_time_limit': int(candidate['dlt_time_limit'] or 0),
            'dlt_ensure': candidate.get('dlt_ensure') or 0,
            'amount': candidate['amount'],
            'security_deposit': candidate['security_deposit'],
            'efficiency_deposit': candidate['efficiency_deposit'],
            'status': MigrationStatus.PUBLISHING,
            'message': '',
        })

    # ② 调丸子发单
    from API.apis.DaiLianWanZi import utils as dlwz_utils
    ok, res = dlwz_utils.publish_order(
        game_id=candidate['game_id'], tasks=None,
        amount=candidate['amount'], hour=candidate['hour'],
        security_deposit=candidate['security_deposit'],
        efficiency_deposit=candidate['efficiency_deposit'],
        region_name=candidate['region_name'],
        leveling_type_name=candidate['leveling_type_name'],
        login_method=2, game_account=qq, game_password=qq, game_role=qq,
        player_phone=qq, contact_phone=qq, contact_qq=qq,
        title=candidate['title'],
        take_level=_setting().take_level, perf_rate=0, take_count=0,
        use_tier=_setting().use_tier)

    if not ok:
        # 网络异常 / 超时：丸子是否真的收到不确定，保持「发单中」交给启动对账判定，避免误判
        record.message = f'发单结果未知（请求异常），等待启动对账: {str(res)[:400]}'
        record.save()
        alert(f'发单结果未知 {serial}: {res}')
        return False, record

    if not isinstance(res, dict) or res.get('code') != 0:
        # 丸子明确拒绝（如余额不足）：不会产生订单，直接置失败
        record.status = MigrationStatus.FAILED
        record.message = str(res)[:500]
        record.save()
        alert(f'发单失败 {serial}: {res}')
        return False, record

    # ③ 回填丸子单号，转「待接单」
    record.dlwz_trade_no = str((res.get('data') or {}).get('trade_no') or '').strip()
    record.dlwz_status = (res.get('data') or {}).get('status')
    record.status = MigrationStatus.PUBLISHED if record.dlwz_trade_no else MigrationStatus.PUBLISHING
    record.message = '' if record.dlwz_trade_no else '发单成功但响应未含丸子单号，等待启动对账'
    record.save()
    if not record.dlwz_trade_no:
        alert(f'发单响应未含丸子单号 {serial}: {res}')
        return False, record
    return True, record


def dlt_order_state(serial):
    """核对代练通原单当前状态（监控用）

    为什么需要：丸子上那笔只是**镜像**，一旦代练通的原单被别人接走 / 撤销 / 删除，
    再等丸子有没有人接就是白等，应立刻回滚丸子那笔。

    :return: (state_ok, info)
        · state_ok=True  → info = {'available': bool, 'status': int|None, 'reason': str}
          available=False 表示**确定不可接**（已被接走 / 已撤销 / 原单已不存在）
        · state_ok=False → info = {'available': None, 'status': None, 'reason': <说明>}
          查询失败（可能只是网络抖动）→ 调用方本轮跳过该笔，**不要**据此回滚
    """
    from API.apis.DaiLianTong import utils as dlt_utils

    # 公开视角（IsPublish='1'）即可读到 Status，且不会暴露号主账号
    ok, res = dlt_utils.get_order_detail(serial, is_publish='1')
    if not ok:
        return False, {'available': None, 'status': None, 'reason': _brief(res)}
    if not isinstance(res, dict):
        return False, {'available': None, 'status': None, 'reason': '返回格式异常'}
    if res.get('code') != 0:
        reason = str(res.get('message') or '').strip() or _brief(res)
        # 「没有找到该订单」：公开池 / 搜索池 / 详情全站都查不到 → 原单已被撤销或删除，
        # 属**确定**不可接（不是网络抖动），应回滚丸子那笔，避免继续白等。
        if '没有找到' in reason:
            return True, {'available': False, 'status': None,
                          'reason': '原单已不存在（已被撤销或删除）'}
        return False, {'available': None, 'status': None, 'reason': reason}

    data = res.get('data') or {}
    try:
        status = int(data.get('Status'))
    except (TypeError, ValueError):
        return False, {'available': None, 'status': None, 'reason': '代练通订单状态无法识别'}
    return True, {'available': status == DLT_STATUS_WAITING, 'status': status,
                  'reason': dlt_status_text(status)}


def _is_taken(order) -> bool:
    """丸子发单方订单是否已被打手接单

    以「接单人字段」为准：被接单后订单会带上 takerUsername / takeUuid /
    takeFrontendParentUserId。（发单方侧 assignTakerList 恒为空，不能用。）
    """
    if not order:
        return False
    return bool(order.get('takerUsername') or order.get('takeUuid')
                or order.get('takeFrontendParentUserId'))


def poll_dlwz_orders():
    """拉取丸子「我发布的」订单，返回 {tradeNo: order}（含全部状态）

    :return: (True, dict) 或 (False, 错误说明)
    """
    from API.apis.DaiLianWanZi import utils as dlwz_utils
    ok, res = dlwz_utils.get_my_orders(authorization='', table_type=0, page=1, page_size=100)
    if not ok:
        return False, res
    orders = _dig(res, 'ordersList') or []
    return True, {str(o.get('tradeNo')): o for o in orders}


def _cancel_dlwz(trade_no):
    """撤单丸子订单；返回 (成功与否, 响应)"""
    from API.apis.DaiLianWanZi import utils as dlwz_utils
    ok, res = dlwz_utils.cancel_order(trade_no)
    return (ok and isinstance(res, dict) and res.get('code') == 0), res


def _revoke_dlwz(trade_no, reason='抢接失败，申请撤销'):
    """申请撤销（发单方发起，需对方同意）；凭证图未配置时不发。返回 (成功与否, 响应/提示)"""
    image = (_setting().revoke_image or '').strip()
    if not image:
        return False, '未配置撤销凭证图URL'
    from API.apis.DaiLianWanZi import utils as dlwz_utils
    ok, res = dlwz_utils.apply_revocation(trade_no, 1, reason, [image])
    return (ok and isinstance(res, dict) and res.get('code') == 0), res


def _cancel_or_revoke(trade_no, reason='抢接失败，申请撤销'):
    """撤销丸子订单：优先「取消」（钱原路退回）；取消不了（已被接单/代练中）再「申请撤销」。

    :return: (结果说明文本, 结果类型)；结果类型 ∈ {'cancelled', 'revoked', 'failed'}
    """
    cancel_ok, _res = _cancel_dlwz(trade_no)
    if cancel_ok:
        return '（已撤单）', 'cancelled'
    revoke_ok, _rres = _revoke_dlwz(trade_no, reason)
    if revoke_ok:
        return '（取消失败→已发起申请撤销，需对方同意）', 'revoked'
    return '（取消失败，且未能自动撤销，需人工处理）', 'failed'


def _rollback_and_fail(record, message):
    """兜底：先尝试取消丸子订单；取消不了（已被接单/代练中）再发「申请撤销」，最后置为失败"""
    from API.models import MigrationStatus

    note = ''
    if record.dlwz_trade_no:
        note, _outcome = _cancel_or_revoke(record.dlwz_trade_no)
    record.status = MigrationStatus.FAILED
    record.message = (message + note)[:500]
    record.save()
    alert(f'{record.dlt_serial_no} {record.message}')


def cancel_all_pending():
    """一键撤销全部「待接单」记录，并释放其占用的代练通双金预扣（无人值守时清场）

    用途：睡觉 / 忙时不想盯着 QQ 同意好友申请 —— 把这些还没被接的单一次撤掉，
    撤完就不会再被接单、也就不需要人工交接。

    处理范围：
        · published（已有丸子单号）：先「取消订单」（待付待接可取消，钱原路退回）；
          取消不了再「申请撤销」（需对方同意）。
        · publishing（发单中、还没拿到丸子单号）：无法调丸子撤单，仅释放占用。
    不论撤销结果如何，记录都会离开「待接单 / 发单中」状态 —— 即**释放**其代练通双金预扣
    （代练通侧本就未真扣，属本系统记账；释放后下一轮即可重新使用）。

    :return: 汇总 dict（total / cancelled / revoked / failed / errors）
    """
    from API.models import MigrationStatus, OrderMigration

    records = list(OrderMigration.objects.filter(
        status__in=(MigrationStatus.PUBLISHED, MigrationStatus.PUBLISHING)))
    result = {'total': len(records), 'cancelled': 0, 'revoked': 0, 'failed': 0, 'errors': []}

    for record in records:
        if record.dlwz_trade_no:
            note, outcome = _cancel_or_revoke(record.dlwz_trade_no, reason='商家主动撤销')
            result[outcome] += 1
            if outcome == 'failed':
                result['errors'].append(f'{record.dlt_serial_no} 撤销失败，需人工处理')
                alert(f'{record.dlt_serial_no} 一键撤销失败：{note}')
        else:
            note = '（无丸子单号，仅释放预扣）'
            result['cancelled'] += 1
        record.status = MigrationStatus.CANCELLED
        record.message = ('一键撤销：' + note)[:500]
        record.save()

    logger.info('一键撤销完成：共 %s 笔（撤单 %s / 申请撤销 %s / 失败 %s）',
                result['total'], result['cancelled'], result['revoked'], result['failed'])
    return result


def _take_on_dlt(record):
    """在代练通接单并取号主账号；失败则回滚（丸子撤单）+ 告警

    :return: True=接单成功，False=已兜底失败
    """
    from API.apis.DaiLianTong import utils as dlt_utils
    from API.models import MigrationStatus

    ok, res = dlt_utils.receive_order(order_id=record.dlt_serial_no)
    if not ok or not isinstance(res, dict) or res.get('code') != 0:
        _rollback_and_fail(record, f'代练通接单失败: {res}')
        return False

    ok2, detail = dlt_utils.get_order_detail(record.dlt_serial_no)
    account_text = ''
    if ok2 and isinstance(detail, dict) and detail.get('code') == 0:
        dd = detail.get('data') or {}
        # Actor 在接单方视角(IsPublish=0)是角色名明文
        account_text = json.dumps({
            'GameAcc': dd.get('GameAcc'), 'GamePass': dd.get('GamePass'),
            'GameRole': dd.get('Actor') or '', 'EnGamePass': dd.get('EnGamePass'),
            'Zone': dd.get('Zone'), 'Server': dd.get('Server'),
        }, ensure_ascii=False)[:2000]

    record.account_info = account_text
    record.status = MigrationStatus.TAKEN
    record.message = '代练通接单成功' if account_text else '代练通接单成功（未取到账号详情）'
    record.save()
    alert(f'{record.dlt_serial_no} 代练通接单成功，请通过 QQ 将账号交给丸子打手')
    return True


# ==================== 被接单通知（邮件） ====================

def notify_taken(record):
    """代练丸子被接单时发邮件通知

    「声音提醒」不走服务端：服务器（尤其 Linux 云主机）没有扬声器，
    改由后台页面用浏览器语音播报（见 console 页的轮询脚本），故此处只发邮件。
    """
    from django.conf import settings

    setting = _setting()
    if not setting.notify_mail:
        return

    # 收件人：页面配置优先，留空回落 .env 的发件邮箱（QQ_MAIL_ACCOUNT）
    recipient = (setting.notify_mail_to
                 or getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
    if not recipient:
        alert('被接单邮件未发送：通知邮箱未填，且 .env 无 QQ_MAIL_ACCOUNT')
        return

    from API.apis.emails.v1.utils import send_email

    subject = f'【代练搬单】丸子订单已被接单 {record.dlwz_trade_no}'
    body = '\n'.join([
        '代练丸子的搬单订单已被打手接单，请及时通过 QQ 把号主账号交给打手。',
        '',
        f'丸子订单号：{record.dlwz_trade_no}',
        f'代练通订单号：{record.dlt_serial_no}',
        f'标题：{record.dlt_title}',
        f'发布价：{record.amount} 元',
        f'状态：{record.get_status_display()}',
    ])
    ok, message = send_email(subject, body, [recipient])
    if ok:
        logger.info('被接单通知邮件已发送 %s → %s', record.dlwz_trade_no, recipient)
    else:
        alert(f'被接单通知邮件发送失败 {record.dlwz_trade_no}: {message}')


def taken_feed(after):
    """取「已被接单」且更新时间晚于 after 的记录，供后台页面轮询后播放语音提醒

    :param after: datetime；None 表示「从此刻开始」——不回放历史记录
    :return: (游标 ISO 时间, [{'trade_no', 'serial', 'time'}, ...])
    """
    from django.utils import timezone

    from API.models import MigrationStatus, OrderMigration

    now = timezone.now()
    if after is None:
        return now.isoformat(), []
    rows = (OrderMigration.objects.filter(status=MigrationStatus.TAKEN,
                                          updated_time__gt=after)
            .order_by('updated_time')
            .values('dlwz_trade_no', 'dlt_serial_no', 'updated_time'))
    items = [{'trade_no': r['dlwz_trade_no'], 'serial': r['dlt_serial_no'],
              'time': r['updated_time'].isoformat()} for r in rows]
    cursor = items[-1]['time'] if items else after.isoformat()
    return cursor, items


def dlt_balance():
    """代练通可用余额（元）= 总资金 − 冻结资金；失败返回 (False, 说明)"""
    from API.apis.DaiLianTong import utils as dlt_utils

    ok, res = dlt_utils.get_balance()
    if not ok:
        return False, _brief(res)
    return True, res['available']


def dlwz_balance():
    """代练丸子可用余额（元）；失败返回 (False, 说明)"""
    from API.apis.DaiLianWanZi import utils as dlwz_utils

    ok, res = dlwz_utils.get_balance()
    if not ok:
        return False, _brief(res)
    return True, res['available']


def reserved_dlt_deposit():
    """已发布/发单中记录占用的代练通双金合计（跨轮占用）

    这些单尚未在代练通接单，但迟早要押双金，必须先从可用余额里占住，避免跨轮超发。
    「发单中」也计入：其丸子单可能已存在，保守占用更安全。
    """
    from API.models import MigrationStatus, OrderMigration

    rows = (OrderMigration.objects.filter(
        status__in=(MigrationStatus.PUBLISHED, MigrationStatus.PUBLISHING))
        .values_list('dlt_ensure', flat=True))
    return round(sum(float(value or 0) for value in rows), 2)


def _match_dlwz_order(record, orders):
    """在候选丸子订单里找出与「发单中」记录匹配的（标题 + 发布价一致）

    仅作**保守**匹配：金额取整数分比较；标题严格相等。返回全部命中的候选，
    由调用方要求「唯一命中」才认领 —— 多条命中视为歧义，不自动认领。
    """
    matched = []
    title = (record.dlt_title or '').strip()
    for order in orders:
        if (order.get('title') or '').strip() != title:
            continue
        try:
            if abs(float(order.get('amount')) - float(record.amount)) > 0.01:
                continue
        except (TypeError, ValueError):
            continue
        matched.append(order)
    return matched


def reconcile_on_startup():
    """启动对账：把本地「发单中」记录与丸子上真实订单对齐

    场景：发单成功后进程崩溃 → 本地记录停在「发单中」且没有丸子单号。
    做法：拉丸子「我发布的」订单（排除本地已认领的单号），对每条「发单中」记录
          按「标题 + 发布价」找回丸子单号；**唯一命中**才认领为「待接单」，
          找不到 / 多条命中 → 置失败并告警（不猜，避免认错单去代练通接单）。

    说明：丸子订单列表分页返回（本函数取前 100 条，即最新一页）；
    该场景下待对账记录都是最近发单，故首页足够覆盖。

    :return: 汇总 dict（checked / recovered / failed / errors）
    """
    from API.models import MigrationStatus, OrderMigration

    result = {'checked': 0, 'recovered': 0, 'failed': 0, 'errors': []}
    pending = list(OrderMigration.objects.filter(status=MigrationStatus.PUBLISHING))
    if not pending:
        return result
    result['checked'] = len(pending)

    ok, orders = poll_dlwz_orders()
    if not ok:
        result['errors'].append(f'拉取丸子订单失败: {orders}')
        return result

    claimed = set(OrderMigration.objects.exclude(dlwz_trade_no='')
                  .values_list('dlwz_trade_no', flat=True))
    candidates = [o for o in orders.values()
                  if str(o.get('tradeNo') or '') and str(o.get('tradeNo')) not in claimed]

    for record in pending:
        matched = _match_dlwz_order(record, candidates)
        if len(matched) == 1:
            order = matched[0]
            candidates.remove(order)
            record.dlwz_trade_no = str(order.get('tradeNo'))
            record.dlwz_status = order.get('status')
            record.status = MigrationStatus.PUBLISHED
            record.message = '启动对账：已找回丸子单号'
            record.save()
            result['recovered'] += 1
        else:
            record.status = MigrationStatus.FAILED
            record.message = (f'启动对账：丸子订单无法唯一确认（标题+发布价 匹配到 {len(matched)} 条）'
                              '，需人工核查')[:500]
            record.save()
            alert(f'{record.dlt_serial_no} {record.message}')
            result['failed'] += 1
    return result


def run_cycle(publish_limit=1, dry_run=False):
    """执行一轮搬单流水线

    每轮顺序（与需求约定一致）：
        取实时余额 → 抓单 → 过滤 → 随机抽单 → 逐条「余额够才发」→ 监控。

    为避免「代练通已停接、丸子还在收单」的无效等待：任一余额不足即**中断本轮发单**
    （已发的保留），直接进入监控阶段；等待轮询间隔后下一轮再重来。

    1) 取代练通 / 丸子实时余额（每轮各查一次）
    2) 抓单并映射（代练通王者公开池 + 搜索池）
    3) 随机抽取不超过 publish_limit 条，逐条判断「代练通双金」与「丸子发单成本」是否够，
       够就真发；余额不足 / 查询失败则该轮不再发单
    4) 监控：先查代练通原单是否还能接，再查丸子是否被接单 → 代练通接单取账号

    :return: 汇总 dict（fetched / published / taken / rollback / errors / monitor）
    """
    summary = {'fetched': 0, 'published': 0, 'taken': 0, 'rollback': 0,
               'errors': [], 'monitor': []}

    # 阶段 0：先取实时余额（代练通 / 丸子各一次）；任一失败则本轮不发单，只监控。
    #         dry-run 只做抓单 + 映射，不联网查余额。
    ok_dlt, dlt_avail = (True, 0.0)
    ok_dlwz, dlwz_avail = (True, 0.0)
    if not dry_run:
        ok_dlt, dlt_avail = dlt_balance()
        ok_dlwz, dlwz_avail = dlwz_balance()
        if not ok_dlt:
            summary['errors'].append(f'代练通余额查询失败，本轮不发单: {dlt_avail}')
        if not ok_dlwz:
            summary['errors'].append(f'丸子余额查询失败，本轮不发单: {dlwz_avail}')

    # 阶段 1：抓单并映射（代练通王者公开池 + 搜索池）
    ok, candidates = fetch_candidates()
    if not ok:
        summary['errors'].append(f'抓单失败: {candidates}')
        candidates = []
    summary['fetched'] = len(candidates)

    if dry_run:
        for candidate in candidates[:max(0, publish_limit)]:
            publish_candidate(candidate, dry_run=True)
        return summary

    # 阶段 3 + 4：随机抽单 → 逐条余额闸门 → 发单
    if ok_dlt and ok_dlwz and candidates:
        limit = max(0, int(publish_limit))
        picked = (random.sample(candidates, limit) if limit < len(candidates)
                  else list(candidates))
        # 代练通可用 = 实时余额 − 已发布未完成占用（跨轮占用）；丸子发单即时扣款，无需占用
        reserved = reserved_dlt_deposit()
        dlt_left = round(dlt_avail - reserved, 2)
        dlwz_left = round(dlwz_avail, 2)
        for candidate in picked:
            need_dlt = float(candidate.get('dlt_ensure') or 0)
            if dlt_left < need_dlt:
                summary['errors'].append(
                    f'代练通余额不足，本轮停止发单：本单双金 {need_dlt} > 可用 {dlt_left}'
                    f'（实时余额 {dlt_avail} − 待接单占用 {reserved}）')
                break
            need_dlwz = float(candidate['amount'])
            if dlwz_left < need_dlwz:
                summary['errors'].append(
                    f'丸子余额不足，本轮停止发单：本单发布价 {need_dlwz} > 可用 {dlwz_left}'
                    f'（实时余额 {dlwz_avail}）')
                break
            dlt_left = round(dlt_left - need_dlt, 2)
            dlwz_left = round(dlwz_left - need_dlwz, 2)
            ok2, result = publish_candidate(candidate)
            if ok2:
                summary['published'] += 1
            else:
                # 发单失败：退还预扣，把额度让给后面的单
                dlt_left = round(dlt_left + need_dlt, 2)
                dlwz_left = round(dlwz_left + need_dlwz, 2)
                summary['errors'].append(f"发布失败 {candidate.get('dlt_serial_no')}: {result}")

    # 阶段 5：监控（对全部已发布记录，逐笔一行：先核对代练通原单，再查丸子）
    from API.models import MigrationStatus, OrderMigration

    monitor = summary['monitor']
    records = list(OrderMigration.objects.filter(status=MigrationStatus.PUBLISHED))
    if not records:
        monitor.append('本轮无「待接单」记录，无需监控')
        return summary

    monitor.append(f'开始监控 {len(records)} 笔待接单（逐笔：先核对代练通原单，再查丸子）')

    # 先取一次丸子「我发布的」订单快照；失败也能继续核对代练通（丸子部分标为未核对）
    orders, orders_ok = {}, True
    ok3, orders_res = poll_dlwz_orders()
    if ok3:
        orders = orders_res
    else:
        orders_ok = False
        summary['errors'].append(f'轮询丸子失败: {orders_res}')

    for record in records:
        label = (f'{record.dlt_serial_no} → {record.dlwz_trade_no or "(无丸子单号)"}'
                 f'｜{record.dlt_title[:18]}｜{record.amount} 元')

        # ① 代练通原单：已被接走 / 已撤销 / 原单不存在 → 丸子那笔就是白等，立刻回滚
        state_ok, info = dlt_order_state(record.dlt_serial_no)
        if not state_ok:
            # 查询失败可能只是网络抖动，这轮不动它，避免误撤
            monitor.append(f'{label}｜代练通核对失败：{info["reason"]} → 本轮跳过')
            summary['errors'].append(f'代练通状态查询失败 {record.dlt_serial_no}: {info["reason"]}')
            continue
        if not info['available']:
            _rollback_and_fail(record, f'代练通{info["reason"]}，丸子上这笔无需再等')
            monitor.append(f'{label}｜代练通：{info["reason"]} → 已回滚撤单')
            summary['rollback'] += 1
            continue

        head = f'{label}｜代练通：{info["reason"]}'
        # ② 紧接着查丸子：被接单就回代练通接单取账号
        if not orders_ok:
            monitor.append(f'{head}｜丸子：本轮查询失败，未核对')
            continue
        order = orders.get(record.dlwz_trade_no)
        if not order:
            monitor.append(f'{head}｜丸子：未找到该单（可能已撤 / 已结束）→ 跳过')
            continue
        record.dlwz_status = order.get('status')
        record.save()
        if not _is_taken(order):
            monitor.append(f'{head}｜丸子：状态 {order.get("status")}（待接单），暂未被人接单')
            continue
        if _take_on_dlt(record):
            summary['taken'] += 1
            monitor.append(f'{head}｜丸子：已被打手接单 → 代练通接单成功，账号已取到')
        else:
            summary['rollback'] += 1
            monitor.append(f'{head}｜丸子：已被打手接单，但代练通接单失败 → 已回滚')
        # 被接单通知（邮件）：每笔只通知一次（处理完 record 已离开 published 状态）
        notify_taken(record)
    return summary


def run_once(publish_count=None, dry_run=False):
    """执行一轮并把运行时间 / 结果写回设置（供后台线程 / 控制台 / 命令调用）"""
    from django.utils import timezone

    from API.models import OrderMigrationSetting

    if publish_count is None:
        publish_count = cycle_publish_limit()
    try:
        summary = run_cycle(publish_limit=publish_count, dry_run=dry_run)
        error = ''
    except Exception as exc:                    # noqa: BLE001 线程/页面入口需兜底，避免整个循环挂掉
        logger.exception('搬单流水线执行异常')
        summary = {'fetched': 0, 'published': 0, 'taken': 0, 'rollback': 0, 'errors': [str(exc)]}
        error = str(exc)[:500]

    setting = OrderMigrationSetting.get_solo()
    setting.last_run_time = timezone.now()
    setting.last_run_summary = (
        f"抓取 {summary['fetched']} / 发布 {summary['published']} / "
        f"接单 {summary['taken']} / 兜底 {summary['rollback']}")[:255]
    setting.last_error = (error or '；'.join(summary['errors']))[:500]
    setting.run_logs = _append_run_log(setting.run_logs, summary, setting.last_run_time)
    setting.save(update_fields=['last_run_time', 'last_run_summary', 'last_error',
                                'run_logs', 'updated_time'])

    # 监控明细同时打印到服务日志（终端 / uwsgi 日志），便于实时观察
    for line in summary.get('monitor', []):
        logger.info('[代练搬单·监控] %s', line)
    return summary


# ==================== 运行日志（供后台页实时展示） ====================

# 滚动日志保留的最近轮数（避免设置表无限膨胀）
RUN_LOG_LIMIT = 30


def _append_run_log(raw, summary, when):
    """把一轮结果追加到滚动日志（JSON 文本）末尾，只留最近 RUN_LOG_LIMIT 条"""
    try:
        logs = json.loads(raw or '[]')
    except (json.JSONDecodeError, TypeError):
        logs = []
    if not isinstance(logs, list):
        logs = []
    logs.append({
        'time': when.isoformat(),
        'fetched': summary['fetched'], 'published': summary['published'],
        'taken': summary['taken'], 'rollback': summary['rollback'],
        'errors': [str(e) for e in summary['errors'][:5]],
        'monitor': [str(m) for m in summary.get('monitor', [])[:40]],
    })
    return json.dumps(logs[-RUN_LOG_LIMIT:], ensure_ascii=False)


def recent_run_logs(limit=RUN_LOG_LIMIT):
    """最近的运行日志（最新在前），供后台页轮询展示"""
    try:
        logs = json.loads(_setting().run_logs or '[]')
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(logs, list):
        return []
    return list(reversed(logs[-limit:]))


# ==================== 后台自动运行线程 ====================
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def start_worker():
    """启动后台搬单线程（幂等；由 API/apps.py 在服务进程里调用一次）

    线程每 `interval_seconds()` 醒一次，只有设置里开启「自动运行」才执行一轮，
    默认关闭 —— 避免未配置就自动发单 / 接单。
    """
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
    threading.Thread(target=_worker_loop, name='order-migration', daemon=True).start()
    logger.info('代练搬单监控线程已启动')


def _worker_loop():
    """后台主循环：启动先对账一次，之后仅当设置开启「自动运行」时执行一轮"""
    from django.db import close_old_connections

    close_old_connections()
    try:
        # 启动对账：把「发单中」记录与丸子上真实订单对齐（防止崩溃丢记录后无人接管）
        result = reconcile_on_startup()
        if result['checked'] or result['errors']:
            logger.info('启动对账：检查 %s / 找回 %s / 失败 %s %s',
                        result['checked'], result['recovered'], result['failed'],
                        result['errors'] or '')
    except Exception:
        logger.exception('启动对账异常')

    while True:
        try:
            close_old_connections()
            if _setting().auto_run:
                run_once()
        except Exception:
            logger.exception('代练搬单线程异常')
        time.sleep(interval_seconds())
