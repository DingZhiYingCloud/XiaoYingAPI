"""文档中心左侧菜单构建器（自动生成，无需手工维护）

菜单来源：
1. 已接入文档的服务（API.website.docs 注册表）→ 展开显示其全部子线路（channels）；
2. 尚未接入文档的服务（官网服务清单 SERVICES）→ 按“服务对外状态”展示
   （默认开发中；超级管理员可在「服务策略」页 /console/services/ 指定 正常/开发中/维护中/已下线）。
   一旦在 docs 注册表补上该服务文档，菜单自动从“开发中”变成可展开。

状态展示规则：状态字段由 service_status 统一计算。
   - 服务级：策略显式设置优先，否则按是否接入文档派生（正常 / 开发中）；
   - 线路级：取该线路下全部端点的生效状态里**最严重**的一个（端点级策略也会体现）；
   - 开发中 / 已下线 → 禁用态（不可展开、不可点击）；其余状态 → 正常展示。

结构：docs_menu = [ {name, url, slug, url_prefix, disabled, status, status_label,
                    status_badge, status_icon, status_fg,
                    children: [{name, url, channel, disabled,
                                status, status_label, status_badge,
                                status_icon, status_fg}]}, ... ]
"""
from ..service_status import (
    UNCLICKABLE_STATUSES,
    annotate as _annotate,
    channel_status_fields,
    status_fields,
)
from ..services import SERVICES as _MARKET
from ..services import localize as _localize_services


def build_docs_menu():
    """按官网服务清单顺序构建菜单（幂等、无缓存：数据源均为常量，构建开销极小）

    被服务策略判为「文档隐藏」的服务整项略过；线路则先剔除隐藏端点，
    整条线路端点全被隐藏时该线路也不展示（与文档页 /docs/<slug>/ 口径一致）。
    """
    from . import all_docs as _all
    from . import localize as _localize_doc
    from ...common.middleware import is_docs_hidden
    # 菜单名与子线路名均来源于声明常量，需按当前语言翻译（对副本翻译，不污染原文）
    ready = {svc.prefix: _localize_doc(svc) for svc in _all()}
    menu = []
    for item in _annotate(_localize_services(_MARKET), lambda p: p in ready):
        prefix = item['url_prefix']
        if is_docs_hidden(prefix):
            continue
        doc = ready.get(prefix)
        unavailable = item['status'] in UNCLICKABLE_STATUSES
        if doc is not None and not unavailable:
            children = []
            for ch in doc.channels:
                endpoints = [ep for ep in ch.endpoints if not is_docs_hidden(ep.path)]
                if not endpoints:
                    continue
                # 线路状态 = 该线路下端点最严重者（端点级策略也会体现）
                fields = channel_status_fields([ep.path for ep in endpoints])
                children.append({
                    'name': ch.name,
                    'url': f'/docs/{doc.slug}/#channel-{ch.slug}',
                    'channel': ch.slug,
                    # 与服务级一致：开发中 / 已下线的线路同样占位不可点击
                    'disabled': fields['status'] in UNCLICKABLE_STATUSES,
                    **fields,
                })
            menu.append({
                'name': doc.name,
                'url': f'/docs/{doc.slug}/',
                'slug': doc.slug,
                'url_prefix': prefix,
                'disabled': False,
                **status_fields(item['status']),
                'children': children,
            })
        else:
            # 未录入文档 or 开发中/已下线：导航占位展示（带状态图标，无子项）
            menu.append({
                'name': item['name'],
                'url': '',
                'slug': '',
                'url_prefix': prefix,
                'disabled': True,
                **status_fields(item['status']),
                'children': [],
            })
    return menu
