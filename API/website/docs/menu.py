"""文档中心左侧菜单构建器（自动生成，无需手工维护）

菜单来源：
1. 已接入文档的服务（API.website.docs 注册表）→ 展开显示其全部子线路（channels）；
2. 尚未接入文档的服务（官网服务清单 SERVICES）→ 按“服务对外状态”展示
   （默认建设中；超级管理员可通过侧栏齿轮弹窗手动指定 开放/测试中/维护中/已下线）。
   一旦在 docs 注册表补上该服务文档，菜单自动从“建设中”变成可展开。

状态展示规则：状态字段由 service_status.annotate 统一计算（手动优先，默认派生）。
   建设中 / 已下线 → 禁用态（不可展开、不可点击）；其余状态 → 正常展示。

结构：docs_menu = [ {name, url, slug, url_prefix, disabled, status, status_label,
                    status_badge, children: [{name, url, channel}]}, ... ]
"""
from ..service_status import annotate as _annotate
from ..services import SERVICES as _MARKET
from ..services import localize as _localize_services


def build_docs_menu():
    """按官网服务清单顺序构建菜单（幂等、无缓存：数据源均为常量，构建开销极小）"""
    from . import all_docs as _all
    from . import localize as _localize_doc
    # 菜单名与子线路名均来源于声明常量，需按当前语言翻译（对副本翻译，不污染原文）
    ready = {svc.prefix: _localize_doc(svc) for svc in _all()}
    menu = []
    for item in _annotate(_localize_services(_MARKET), lambda p: p in ready):
        prefix = item['url_prefix']
        doc = ready.get(prefix)
        unavailable = item['status'] in ('building', 'offline')
        if doc is not None and not unavailable:
            children = [
                {
                    'name': ch.name,
                    'url': f'/docs/{doc.slug}/#channel-{ch.slug}',
                    'channel': ch.slug,
                    'disabled': False,
                }
                for ch in doc.channels
            ]
            menu.append({
                'name': doc.name,
                'url': f'/docs/{doc.slug}/',
                'slug': doc.slug,
                'url_prefix': prefix,
                'disabled': False,
                'status': item['status'],
                'status_label': item['status_label'],
                'status_badge': item['status_badge'],
                'children': children,
            })
        else:
            # 未录入文档 or 手动标记建设中/已下线：导航占位展示（带状态徽标）
            menu.append({
                'name': item['name'],
                'url': '',
                'slug': '',
                'url_prefix': prefix,
                'disabled': True,
                'status': item['status'],
                'status_label': item['status_label'],
                'status_badge': item['status_badge'],
                'children': [],
            })
    return menu
