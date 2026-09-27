"""服务对外状态（唯一口径）

前台（官网首页 / 文档中心 / 左侧导航）展示的 API 服务状态：
- 取值与徽标样式统一在这里定义（STATUS_DEFS），模板/页面不得各自硬编码；
- 固定 4 态：正常 / 开发中 / 维护中 / 已下线（normal / dev / maintenance / offline）；
- 数据源为「服务策略」表（ApiServicePolicy）：**服务级**策略若显式设置了 status（非 inherit），
  以它为准；未设置则按默认派生：已接入文档(注册表) → 正常，未接入文档 → 开发中。
- 服务状态由超级管理员在「服务策略」页（/console/services/）统一维护（服务 / 线路 / 端点三级可继承）。

每个状态同时给出「徽标样式 badge」与「状态图标 icon / 前景色 fg」，均为现有类名
（badge 用 daisyUI 软色徽标；icon 用自托管 lucide 图标名，fg 用 Tailwind 语义文字色），
供模板按语义渲染：正常=成功、开发中=提示、维护中=警告、已下线=错误。
菜单/徽标里要展示状态图标时一律取本表，禁止在模板里写死图标名。
"""
from django.utils.translation import gettext as _

# 键 -> (中文文案, 徽标样式, 图标名, 图标前景色, 说明)
# 注：中文为源语言，展示时统一经 status_def() 翻译，请勿在本表内直接翻译。
STATUS_DEFS = {
    'normal':      {'label': '正常',   'badge': 'badge-soft badge-success',
                    'icon': 'circle-check',  'fg': 'text-success', 'desc': '正常对外可用'},
    'dev':         {'label': '开发中', 'badge': 'badge-soft badge-info',
                    'icon': 'flask-conical', 'fg': 'text-info',    'desc': '开发/测试阶段，功能可能不稳定'},
    'maintenance': {'label': '维护中', 'badge': 'badge-soft badge-warning',
                    'icon': 'wrench',        'fg': 'text-warning', 'desc': '临时维护，暂停使用'},
    'offline':     {'label': '已下线', 'badge': 'badge-soft badge-error',
                    'icon': 'ban',           'fg': 'text-error',   'desc': '服务下线，不可用'},
}
STATUS_KEYS = list(STATUS_DEFS.keys())

DEFAULT_REGISTERED = 'normal'  # 已接入文档、且未在策略里显式指定 → 正常
DEFAULT_UNREGISTERED = 'dev'   # 未接入文档、且未在策略里显式指定 → 开发中


def status_def(key):
    """取某状态的定义：{'label', 'badge', 'icon', 'fg', 'desc'}

    label/desc 按当前请求语言翻译（徽标样式、图标名与状态键保持原样）。
    统一出口，避免各页面各自翻译导致文案不一致。
    """
    d = STATUS_DEFS.get(key, STATUS_DEFS[DEFAULT_UNREGISTERED])
    return {'label': _(d['label']), 'badge': d['badge'],
            'icon': d['icon'], 'fg': d['fg'], 'desc': _(d['desc'])}


def _status_map():
    """显式指定了状态的服务级策略：服务前缀 -> 状态键（未设置 / inherit 的不在内）"""
    from API.models import ApiServicePolicy
    return {row.path_prefix: row.status
            for row in ApiServicePolicy.objects.filter(level='service')
            if row.status in STATUS_DEFS}


def annotate(items, is_registered):
    """给服务清单（官网 services.SERVICES 项）附加状态字段，供各页面渲染。

    :param items: 服务清单，每个 item 含 'url_prefix' 等展示字段
    :param is_registered: callable(url_prefix) -> bool（是否已接入文档）
    :return: 新列表（不改动传入对象），每项附加：
             status/status_label/status_badge/status_icon/status_fg/registered
    """
    manual = _status_map()
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
            'status_icon': defs['icon'],
            'status_fg': defs['fg'],
        })
    return out
