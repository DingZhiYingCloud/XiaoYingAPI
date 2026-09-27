"""超级管理员控制台 - 侧边栏菜单（声明式，一处维护）

新增控制台页面时**只在这里加一行**，模板与高亮逻辑无需改动
（与文档中心 /docs/* 的菜单思路一致，但这里是人工声明的固定菜单，
不像文档菜单那样由服务注册表自动生成）。

约定：
- 分组（group）顺序 = 侧边栏显示顺序；分组内的项按声明顺序显示。
- **未实现的功能不要提前放进菜单**，避免点进去是空链接；页面可用了再补一行。
- 分组名与项名都写中文（源语言），由模板 {% trans %} 在渲染时翻译。

item 字段：
    key   - 唯一标识，同时用于 active 高亮判定
             （取值 = URL name 去掉 'website:' 前缀；由 _active_key 按 URL 前缀匹配）
    name  - 菜单文案（中文源语言）
    url   - URL name（模板里用 {% url %} 解析，避免硬编码路径）
    icon  - lucide 图标名（站点已全局加载 lucide）
    desc  - 一句话说明，供控制台首页的入口卡片复用
"""
from django.urls import NoReverseMatch, reverse

# 控制台首页地址（前缀匹配时需排除，见 _active_key）
CONSOLE_HOME = '/console/'

MENU = [
    {
        'title': '概览',
        'items': [
            {
                'key': 'console_home', 'name': '控制台首页', 'url': 'website:console_home',
                'icon': 'layout-dashboard', 'desc': '控制台总览与各模块入口。',
            },
        ],
    },
    {
        'title': '运营',
        'items': [
            {
                'key': 'console_projects', 'name': '接入项目', 'url': 'website:console_projects',
                'icon': 'boxes', 'desc': '创建 / 编辑 / 启停 / 删除接入项目；APPID、APPSECRET 由系统自动生成。',
            },
            {
                'key': 'console_services', 'name': '服务策略', 'url': 'website:console_services',
                'icon': 'shield-check', 'desc': '按服务 / 线路 / 端点三级配置认证模式、对外状态与项目白名单，逐级继承。',
            },
            {
                'key': 'console_stats', 'name': '调用统计', 'url': 'website:console_stats',
                'icon': 'chart-column', 'desc': '按服务、接口、项目与结果查看调用量与耗时。',
            },
        ],
    },
    {
        'title': '用户',
        'items': [
            {
                'key': 'console_users', 'name': '用户管理', 'url': 'website:console_users',
                'icon': 'users', 'desc': '查看用户资料与登录明细（登录过的项目、次数、最后登录、剩余有效天数），支持建号、编辑、封禁、重置密码与删除。',
            },
        ],
    },
]


def console_menu_context(request):
    """模板上下文：仅 /console/* 注入 console_menu 与当前高亮项

    其他页面不注入，避免无谓的上下文变量。
    """
    if not request.path.startswith('/console/'):
        return {}
    return {'console_menu': MENU, 'console_active_key': _active_key(request)}


def _active_key(request):
    """当前菜单高亮项：按「已解析 URL 的最长前缀」匹配

    这样才能让详情页也高亮其所属菜单（如 /console/users/<id>/ 高亮「用户管理」、
    /console/stats/service/... 高亮「调用统计」）；控制台首页只精确匹配，
    否则它会吃掉所有 /console/ 子页（前缀最短但覆盖最广）。
    """
    matched, matched_len = '', 0
    for group in MENU:
        for item in group['items']:
            try:
                href = reverse(item['url'])
            except NoReverseMatch:
                continue
            if href == CONSOLE_HOME:
                if request.path == href:
                    return item['key']
                continue
            if request.path.startswith(href) and len(href) > matched_len:
                matched, matched_len = item['key'], len(href)
    return matched
