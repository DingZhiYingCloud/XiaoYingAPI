"""超管控制台 - 代练搬单

鉴权：仅 Django is_superuser（见 admin_auth.py）。

页面：
    GET  /console/order-migration/   搬单设置 + 记录列表
    POST /console/order-migration/   action = save（保存设置）/ preview（抓单预览）
                                     / run（执行一轮）/ clear（清空记录）
                                     / clear_logs（清空运行日志）
                                     / cancel_all（一键撤销全部待接单 + 关自动运行）
                                     / owner_info（号主信息查询）
                                     / edit（编辑记录：改状态 + 备注，仅本地）
                                     / blacklist_add, blacklist_delete（标题黑名单增删）
    GET  /console/order-migration/feed/   搬单页实时数据轮询（记录 / 统计 / 运行日志 / 语音，JSON）

搬单流水线逻辑在 API/apis/order_migration/utils.py；本页只负责配置读写、手动触发与展示。
真正的「全自动」由后台线程按设置间隔执行（auto_run 开启时），见 utils.start_worker()。
"""
import logging
from datetime import datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from API.apis.order_migration import utils as om_utils
from API.models import (MigrationStatus, OrderMigration, OrderMigrationBlacklist,
                        OrderMigrationSetting)

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.order_migration')

REDIRECT_URL = 'website:console_order_migration'
PAGE_SIZE = 20

# 记录列表可筛选的状态（可多选，如「待接单 + 失败」）
FILTER_STATUSES = (
    (MigrationStatus.PUBLISHED.value, '待接单'),
    (MigrationStatus.TAKER_JOINED.value, '待报单号'),
    (MigrationStatus.TAKEN.value, '已接单'),
    (MigrationStatus.WAITING_ACCEPT.value, '等待验收'),
    (MigrationStatus.SETTLED.value, '已结算'),
    (MigrationStatus.BOOSTER_CANCEL.value, '打手申请退单'),
    (MigrationStatus.FAILED.value, '失败'),
    (MigrationStatus.CANCELLED.value, '已撤单'),
    (MigrationStatus.PUBLISHING.value, '发单中'),
)
_FILTER_KEYS = {key for key, _label in FILTER_STATUSES}


def _selected_statuses(request):
    """取本次请求选中的状态（过滤掉非法值，保持顺序去重）"""
    picked, seen = [], set()
    for value in request.GET.getlist('status'):
        if value in _FILTER_KEYS and value not in seen:
            seen.add(value)
            picked.append(value)
    return picked


def _status_filters(selected):
    """构造状态筛选项（含「点击切换该状态」后的链接）"""
    filters = []
    for key, label in FILTER_STATUSES:
        toggled = [s for s in selected if s != key]
        active = key in selected
        if not active:
            toggled.append(key)
        query = urlencode([('status', s) for s in toggled])
        filters.append({'key': key, 'label': _(label), 'active': active,
                        'href': f'?{query}' if query else '?'})
    return filters


@superadmin_required
def order_migration_view(request):
    """代练搬单页：展示 + 保存设置 + 抓单预览 / 执行一轮 / 清空记录"""
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save':
            return _save(request)
        if action == 'preview':
            return _preview(request)
        if action == 'run':
            return _run(request)
        if action == 'clear':
            return _clear(request)
        if action == 'clear_logs':
            return _clear_logs(request)
        if action == 'cancel_all':
            return _cancel_all(request)
        if action == 'owner_info':
            return _owner_info(request)
        if action == 'edit':
            return _edit(request)
        if action == 'blacklist_add':
            return _blacklist_add(request)
        if action == 'blacklist_delete':
            return _blacklist_delete(request)
        messages.error(request, _('不支持的操作'))
        return redirect(REDIRECT_URL)
    return _render(request)


def _parse_float(raw):
    """空串返回 None；非数字返回 'ERR'"""
    raw = (raw or '').strip()
    if raw == '':
        return None
    try:
        return float(raw)
    except ValueError:
        return 'ERR'


def _persist(request):
    """把表单里的搬单设置写入单例；校验失败时已提示，返回 False"""
    try:
        interval = max(5, int((request.POST.get('interval_seconds') or '20').strip() or 20))
        limit = max(0, int((request.POST.get('publish_limit') or '1').strip() or 1))
    except ValueError:
        messages.error(request, _('轮询间隔 / 每轮上限必须是整数'))
        return False

    price_min = _parse_float(request.POST.get('price_min'))
    price_max = _parse_float(request.POST.get('price_max'))
    if price_min == 'ERR' or price_max == 'ERR':
        messages.error(request, _('价格上下限必须是数字'))
        return False
    if price_min is not None and price_max is not None and price_min > price_max:
        messages.error(request, _('价格下限不能大于上限'))
        return False

    try:
        deposit_ratio = int((request.POST.get('deposit_ratio') or '2').strip() or 2)
    except ValueError:
        messages.error(request, _('双金倍数必须是整数'))
        return False
    deposit_ratio = min(om_utils.DEPOSIT_RATIO_MAX,
                        max(om_utils.DEPOSIT_RATIO_MIN, deposit_ratio))

    setting = OrderMigrationSetting.get_solo()
    setting.our_qq = (request.POST.get('our_qq') or '').strip()[:32]
    setting.interval_seconds = interval
    setting.publish_limit = limit
    setting.deposit_ratio = deposit_ratio
    setting.price_min = price_min
    setting.price_max = price_max
    setting.keyword = (request.POST.get('keyword') or '').strip()[:64]
    take_level = (request.POST.get('take_level') or '-1').strip()
    setting.take_level = int(take_level) if take_level in ('-1', '0', '1') else -1
    setting.use_tier = request.POST.get('use_tier') == 'on'
    setting.revoke_image = (request.POST.get('revoke_image') or '').strip()[:500]
    setting.notify_mail = request.POST.get('notify_mail') == 'on'
    setting.notify_mail_to = (request.POST.get('notify_mail_to') or '').strip()[:254]
    setting.notify_sound = request.POST.get('notify_sound') == 'on'
    setting.notify_sound_text = (request.POST.get('notify_sound_text') or '').strip()[:100]
    setting.notify_qq = (request.POST.get('notify_qq') or '').strip()[:32]
    setting.auto_run = request.POST.get('auto_run') == 'on'
    setting.save()
    return True


def _save(request):
    """保存搬单设置"""
    if not _persist(request):
        return redirect(REDIRECT_URL)
    notify_success(request, _('代练搬单设置已保存'))
    return redirect(REDIRECT_URL)


def _blacklist_add(request):
    """新增一条标题黑名单"""
    word = (request.POST.get('word') or '').strip()[:64]
    if not word:
        messages.error(request, _('请输入要加入黑名单的词'))
        return redirect(REDIRECT_URL)
    _row, created = OrderMigrationBlacklist.objects.get_or_create(word=word)
    if created:
        notify_success(request, _('已加入黑名单：%(word)s') % {'word': word})
    else:
        messages.info(request, _('黑名单里已有：%(word)s') % {'word': word})
    return redirect(REDIRECT_URL)


def _blacklist_delete(request):
    """删除一条标题黑名单"""
    word = (request.POST.get('word') or '').strip()
    deleted, _rows = OrderMigrationBlacklist.objects.filter(word=word).delete()
    if deleted:
        notify_success(request, _('已从黑名单移除：%(word)s') % {'word': word})
    else:
        messages.info(request, _('黑名单里没有：%(word)s') % {'word': word})
    return redirect(REDIRECT_URL)


def _local_str(value, fmt):
    """把 aware datetime / ISO 字符串按**本地时区**格式化（页面显示用）

    库里存的是 UTC（USE_TZ=True），直接 strftime 会比本地时间少 8 小时，
    必须经 localtime() 转换后再格式化。
    """
    from django.utils import timezone as dj_timezone

    if not value:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if dj_timezone.is_naive(value):
        value = dj_timezone.make_aware(value)
    return dj_timezone.localtime(value).strftime(fmt)


@superadmin_required
@require_GET
def feed_view(request):
    """搬单页实时数据（JSON）：记录列表（支持状态筛选 + 分页）/ 统计 / 最近运行 / 运行日志 / 新「被接单」

    页面每几秒轮询一次即可**免刷新**看到最新状态；`after` 为「被接单」语音游标，
    只用于浏览器语音播报，避免回放历史；`status` 可多选、`page` 为记录列表页码。
    """
    setting = OrderMigrationSetting.get_solo()
    all_records = OrderMigration.objects.all()
    selected = _selected_statuses(request)
    listed = all_records.filter(status__in=selected) if selected else all_records
    paginator = Paginator(listed, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    records = [{
        'id': str(r.pk),
        'serial': r.dlt_serial_no,
        'trade_no': r.dlwz_trade_no,
        'title': r.dlt_title,
        'amount': r.amount,
        'status': r.status,
        'dlwz_status': r.dlwz_status,
        'message': r.message,
        'account_info': r.account_info,
        'time': _local_str(r.create_time, '%m-%d %H:%M'),
    } for r in page.object_list]

    logs = [{'time': _local_str(log.get('time'), '%m-%d %H:%M:%S'),
             'fetched': log.get('fetched'), 'published': log.get('published'),
             'taken': log.get('taken'), 'rollback': log.get('rollback'),
             'errors': log.get('errors') or [],
             'monitor': log.get('monitor') or []}
            for log in om_utils.recent_run_logs()]

    raw = (request.GET.get('after') or '').strip()
    after = None
    if raw:
        try:
            after = datetime.fromisoformat(raw)
        except ValueError:
            after = None
    cursor, taken = om_utils.taken_feed(after)

    return JsonResponse({
        'ok': True,
        'cursor': cursor,
        'taken': taken,
        'records': records,
        'page': page.number,
        'num_pages': paginator.num_pages,
        'filtered_total': paginator.count,
        'stats': {
            'total': all_records.count(),
            'published': all_records.filter(status=MigrationStatus.PUBLISHED).count(),
            'taker_joined': all_records.filter(status=MigrationStatus.TAKER_JOINED).count(),
            'taken': all_records.filter(status=MigrationStatus.TAKEN).count(),
            'waiting_accept': all_records.filter(status=MigrationStatus.WAITING_ACCEPT).count(),
            'settled': all_records.filter(status=MigrationStatus.SETTLED).count(),
            'booster_cancel': all_records.filter(status=MigrationStatus.BOOSTER_CANCEL).count(),
            'failed': all_records.filter(status=MigrationStatus.FAILED).count(),
        },
        'run': {
            'time': _local_str(setting.last_run_time, '%Y-%m-%d %H:%M:%S'),
            'summary': setting.last_run_summary,
            'error': setting.last_error,
            'auto_run': setting.auto_run,
        },
        'logs': logs,
    })


def _preview(request):
    """抓单预览：拉取代练通王者排位公开单并映射，不写任何真实订单"""
    ok, candidates = om_utils.fetch_candidates(page_size=20)
    if not ok:
        messages.error(request, _('抓单失败：%(msg)s') % {'msg': candidates})
        return redirect(REDIRECT_URL)
    if not candidates:
        messages.info(request, _('没有可搬的新订单（可能都被搬运过，或都被价格区间过滤）'))
        return redirect(REDIRECT_URL)
    messages.success(request, _('抓取到 %(n)s 条候选（未发布）') % {'n': len(candidates)})
    return _render(request, preview=candidates)


def _run(request):
    """执行一轮流水线（真实发单 / 接单 / 兜底撤单）

    run_once 是跨进程互斥的：已有进程（多为后台自动线程）在执行本轮时返回 None，
    这里只提示、不重复执行 —— 否则同一笔订单会被发两次。
    """
    summary = om_utils.run_once()
    if summary is None:
        messages.warning(request, _('已有进程正在执行本轮，请稍后重试'))
        return redirect(REDIRECT_URL)
    note = _('已执行一轮：抓取 %(f)s / 发布 %(p)s / 接单 %(t)s / 兜底 %(r)s') % {
        'f': summary['fetched'], 'p': summary['published'],
        't': summary['taken'], 'r': summary['rollback']}
    if summary['errors']:
        messages.warning(request, note + ' ' + _('错误：%(e)s') % {'e': '；'.join(summary['errors'])})
    else:
        notify_success(request, note)
    return redirect(REDIRECT_URL)


def _clear(request):
    """清空全部搬单记录"""
    deleted, _rows = OrderMigration.objects.all().delete()
    notify_success(request, _('已清空 %(n)s 条搬单记录') % {'n': deleted})
    return redirect(REDIRECT_URL)


def _clear_logs(request):
    """清空运行日志（只清日志，不动搬单记录）"""
    setting = OrderMigrationSetting.get_solo()
    setting.run_logs = ''
    setting.save(update_fields=['run_logs', 'updated_time'])
    notify_success(request, _('已清空运行日志'))
    return redirect(REDIRECT_URL)


def _cancel_all(request):
    """一键撤销全部「待接单」，并关闭自动运行（无人值守清场）

    睡觉 / 忙时不想盯 QQ 同意好友申请：把还没被接的单一次撤掉，同时关掉自动运行，
    避免撤销后系统又继续发新单。撤销后这些单的**代练通双金预扣即释放**。
    """
    summary = om_utils.cancel_all_pending()
    setting = OrderMigrationSetting.get_solo()
    setting.auto_run = False
    setting.save(update_fields=['auto_run', 'updated_time'])

    note = _('已撤销 %(total)s 笔待接单（撤单 %(cancelled)s / 申请撤销 %(revoked)s / 失败 %(failed)s），'
             '预扣资金已释放，自动运行已关闭') % summary
    if summary['errors']:
        messages.warning(request, note + ' ' + _('需人工处理：%(e)s') % {'e': '；'.join(summary['errors'])})
    else:
        notify_success(request, note)
    return redirect(REDIRECT_URL)


def _owner_info(request):
    """查询号主信息：输入代练丸子订单号或代练通订单号均可"""
    from API.apis.DaiLianTong import utils as dlt_utils

    raw = (request.POST.get('order') or '').strip()
    if not raw:
        messages.error(request, _('请输入代练丸子订单号或代练通订单号'))
        return redirect(REDIRECT_URL)

    # 丸子订单号形如 WZ...；否则按代练通订单号（SerialNo）处理
    serial, trade = raw, ''
    if raw.upper().startswith('WZ'):
        record = OrderMigration.objects.filter(dlwz_trade_no=raw).first()
        if record is None:
            messages.error(request, _('未找到该丸子订单对应的搬单记录：%(no)s') % {'no': raw})
            return redirect(REDIRECT_URL)
        serial, trade = record.dlt_serial_no, raw

    ok, data = dlt_utils.get_owner_info(serial)
    if not ok:
        messages.error(request, _('获取号主信息失败：%(msg)s') % {'msg': data})
        return redirect(REDIRECT_URL)
    return _render(request, owner={'order': raw, 'serial': serial, 'trade': trade, 'info': data})


def _edit(request):
    """编辑一条搬单记录：改状态 + 备注（**只改本地记录**，平台动作需人工做）

    退单等需要人工定夺的场景下，管理员处理完平台后回来把本地状态改成最终结果即可；
    本操作不发任何平台请求，避免误触发资金动作。
    """
    from django.core.exceptions import ValidationError

    record_id = (request.POST.get('record_id') or '').strip()
    try:
        record = OrderMigration.objects.filter(pk=record_id).first()
    except (ValidationError, ValueError):
        record = None
    if record is None:
        messages.error(request, _('未找到该搬单记录'))
        return redirect(REDIRECT_URL)

    status = (request.POST.get('status') or '').strip()
    if status not in MigrationStatus.values:
        messages.error(request, _('状态不合法'))
        return redirect(REDIRECT_URL)

    record.status = status
    record.message = (request.POST.get('message') or '').strip()[:500]
    record.save(update_fields=['status', 'message', 'updated_time'])
    notify_success(request, _('已更新记录：%(no)s')
                   % {'no': record.dlwz_trade_no or record.dlt_serial_no})
    return redirect(REDIRECT_URL)


def _render(request, preview=None, owner=None):
    setting = OrderMigrationSetting.get_solo()
    selected = _selected_statuses(request)
    all_records = OrderMigration.objects.all()
    queryset = all_records.filter(status__in=selected) if selected else all_records
    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_prefix = urlencode([('status', s) for s in selected])
    return render(request, 'console/order_migration.html', {
        'setting': setting,
        'page_obj': page_obj,
        'paginator': paginator,
        'page_prefix': (page_prefix + '&') if page_prefix else '',
        'preview': preview,
        'owner': owner,
        'blacklist': OrderMigrationBlacklist.objects.all(),
        'status_filters': _status_filters(selected),
        'status_filter_active': bool(selected),
        'status_choices': MigrationStatus.choices,
        'stats': {
            'total': all_records.count(),
            'published': all_records.filter(status=MigrationStatus.PUBLISHED).count(),
            'taker_joined': all_records.filter(status=MigrationStatus.TAKER_JOINED).count(),
            'taken': all_records.filter(status=MigrationStatus.TAKEN).count(),
            'waiting_accept': all_records.filter(status=MigrationStatus.WAITING_ACCEPT).count(),
            'settled': all_records.filter(status=MigrationStatus.SETTLED).count(),
            'booster_cancel': all_records.filter(status=MigrationStatus.BOOSTER_CANCEL).count(),
            'failed': all_records.filter(status=MigrationStatus.FAILED).count(),
        },
    })
