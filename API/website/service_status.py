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

服务级状态（annotate）与线路级状态（channel_status_fields）分别取用：
- 服务级：只看服务级策略（显式设置优先，否则按是否接入文档派生）；
- 线路级：逐条按中间件口径解析该线路下**全部端点**的生效状态，取**最严重**的一个，
  因此端点级策略（如只把某个接口设为下线）也会体现在菜单里，且与真实拦截结果一致。
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

# 状态严重度：一条线路下挂多个端点时取最严重的那个作为线路展示状态
_SEVERITY = {'normal': 0, 'dev': 1, 'maintenance': 2, 'offline': 3}

# 菜单里「不可点击」的状态：与服务级现有行为保持一致（开发中 / 已下线为占位不可点）
UNCLICKABLE_STATUSES = ('dev', 'offline')

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


def status_fields(key):
    """某状态键对应的展示字段（状态 / 文案 / 徽标 / 图标 / 图标配色）

    服务级与线路级共用同一出口，避免两处各拼一遍字段名。
    """
    defs = status_def(key)
    return {
        'status': key,
        'status_label': defs['label'],
        'status_badge': defs['badge'],
        'status_icon': defs['icon'],
        'status_fg': defs['fg'],
    }


def worst_status(keys):
    """取一组状态键里最严重的一个（offline > maintenance > dev > normal）"""
    return max(keys, key=lambda k: _SEVERITY.get(k, 0), default=DEFAULT_REGISTERED)


def channel_status_fields(endpoint_paths):
    """线路（或任意一组端点）的展示字段：取其中**最严重**的生效状态

    逐条走中间件口径解析（服务 → 线路 → 端点逐级继承），因此线路下某个端点被
    单独设为维护 / 下线时，线路行也会标出来；展示与真实拦截永远一致。
    """
    from API.common.middleware import resolve_service_policy
    return status_fields(worst_status(
        resolve_service_policy(path)['status'] for path in endpoint_paths))


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
        out.append({
            **item,
            'registered': registered,
            **status_fields(key),
        })
    return out
