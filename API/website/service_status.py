"""服务对外状态（唯一口径）

前台（官网首页 / 文档中心 / 左侧导航）展示的 API 服务状态：
- 取值与徽标样式统一在这里定义（STATUS_DEFS），模板/页面不得各自硬编码；
- 展示规则：若某服务在 ServiceStatus 表中被“手动指定”了状态 → 以手动为准；
  否则按默认派生：已接入文档(注册表) → 开放，未接入文档 → 建设中。
- 手动状态由超级管理员在文档侧栏“服务设置”齿轮弹窗中维护（/console/services/api/）。

badge_class 均为 daisyUI 现有工具类（软色徽标）。
"""
from django.utils.translation import gettext as _

from API.models import ServiceStatus

# 键 -> (中文文案, 徽标样式, 说明)
# 注：中文为源语言，展示时统一经 status_def() 翻译，请勿在本表内直接翻译。
STATUS_DEFS = {
    'open':       {'label': '开放',     'badge': 'badge-soft badge-success', 'desc': '正常对外可用'},
    'testing':    {'label': '测试中',   'badge': 'badge-soft badge-info',    'desc': '内测/演示阶段'},
    'maintenance': {'label': '维护中',  'badge': 'badge-soft badge-warning', 'desc': '临时维护，暂停使用'},
    'building':   {'label': '建设中',   'badge': 'badge-ghost',              'desc': '尚未开放'},
    'offline':    {'label': '已下线',   'badge': 'badge-soft badge-error',   'desc': '服务下线，不可用'},
}
STATUS_KEYS = list(STATUS_DEFS.keys())

DEFAULT_REGISTERED = 'open'    # 已接入文档、且未手动指定 → 开放
DEFAULT_UNREGISTERED = 'building'  # 未接入文档、且未手动指定 → 建设中


def status_def(key):
    """取某状态的定义：{'label', 'badge', 'desc'}

    label/desc 按当前请求语言翻译（徽标样式与状态键保持原样）。
    统一出口，避免各页面各自翻译导致文案不一致。
    """
    d = STATUS_DEFS.get(key, STATUS_DEFS[DEFAULT_UNREGISTERED])
    return {'label': _(d['label']), 'badge': d['badge'], 'desc': _(d['desc'])}


def _manual_map():
    """当前所有手动指定的服务前缀 -> 状态键"""
    return {row.url_prefix: row.status for row in ServiceStatus.objects.only('url_prefix', 'status')}


def annotate(items, is_registered):
    """给服务清单（官网 services.SERVICES 项）附加状态字段，供各页面渲染。

    :param items: 服务清单，每个 item 含 'url_prefix' 等展示字段
    :param is_registered: callable(url_prefix) -> bool（是否已接入文档）
    :return: 新列表（不改动传入对象），每项附加：
             status/status_label/status_badge/registered
    """
    manual = _manual_map()
    out = []
    for item in items:
        prefix = item['url_prefix']
        registered = bool(is_registered(prefix))
        key = manual.get(prefix, DEFAULT_REGISTERED if registered else DEFAULT_UNREGISTERED)
        defs = status_def(key)
        out.append({
            **item,
            'registered': registered,
            'status': key,
            'status_label': defs['label'],
            'status_badge': defs['badge'],
        })
    return out
