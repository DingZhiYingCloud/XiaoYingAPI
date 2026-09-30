"""超级管理员控制台 - 侧边栏菜单（声明式，一处维护）

新增控制台页面时**只在这里加一行**，模板与高亮逻辑无需改动
（与文档中心 /docs/* 的菜单思路一致，但这里是人工声明的固定菜单，
不像文档菜单那样由服务注册表自动生成）。

**分组口径（按「管什么」划分，而不是按「谁用」）**：

| 分组 | 管的对象 | 成员 |
| --- | --- | --- |
| 概览 | 控制台自身 | 控制台首页 |
| 接口治理 | 对外提供的 API 本身 | 服务策略、接口公告、AI 模型 |
| 数据运营 | 接入方 / 流量 / 站点与内容 | 接入项目、调用统计、官网外观、红果短剧 |
| 用户支持 | 用户体系与用户声音 | 用户管理、问题反馈 |

判断一个模块该进哪组，先问「它管的对象是什么」：
对外接口本身的认证 / 状态 / 公告 / 能力接入 → 接口治理；
接入方、流量数据、站点外观与内容 → 数据运营；
用户资料与用户反馈 → 用户支持。

约定：
- 分组（group）顺序 = 侧边栏显示顺序；分组内的项按声明顺序显示。
- **未实现的功能不要提前放进菜单**，避免点进去是空链接；页面可用了再补一行。
- 分组名与项名都写中文（源语言），由模板 {% trans %} 在渲染时翻译。

group 字段：
    title - 分组标题（中文源语言）
    icon  - 分组图标（lucide 图标名，渲染在标题左侧）

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
        'icon': 'layout-dashboard',
        'items': [
            {
                'key': 'console_home', 'name': '控制台首页', 'url': 'website:console_home',
                'icon': 'layout-dashboard', 'desc': '控制台总览与各模块入口。',
            },
        ],
    },
    {
        'title': '接口治理',
        'icon': 'shield-check',
        'items': [
            {
                'key': 'console_services', 'name': '服务策略', 'url': 'website:console_services',
                'icon': 'shield-check', 'desc': '按服务 / 线路 / 端点三级配置认证模式、对外状态与项目白名单，逐级继承。',
            },
            {
                'key': 'console_announcements', 'name': '接口公告', 'url': 'website:console_announcements',
                'icon': 'megaphone', 'desc': '给服务 / 线路 / 端点三级 API 对象发布公告，在官网文档中心对应位置展示。',
            },
            {
                'key': 'console_ai_models', 'name': 'AI 模型', 'url': 'website:console_ai_models',
                'icon': 'bot', 'desc': '维护 AI 厂商与模型（上游地址、平台密钥、模型能力），调用方只需选模型即可无缝切换。',
            },
        ],
    },
    {
        'title': '数据运营',
        'icon': 'chart-column',
        'items': [
            {
                'key': 'console_projects', 'name': '接入项目', 'url': 'website:console_projects',
                'icon': 'boxes', 'desc': '创建 / 编辑 / 启停 / 删除接入项目；APPID、APPSECRET 由系统自动生成。',
            },
            {
                'key': 'console_stats', 'name': '调用统计', 'url': 'website:console_stats',
                'icon': 'chart-column', 'desc': '按服务、接口、项目与结果查看调用量与耗时。',
            },
            {
                'key': 'console_appearance', 'name': '官网外观', 'url': 'website:console_appearance',
                'icon': 'swatch-book',
                'desc': '切换官网首页与接口文档中心的视觉气质（多套预设可切换），并可覆盖首页头图文案；'
                        '颜色仍由访客选择的主题决定，二者互不冲突。',
            },
            {
                'key': 'console_dramas_hongguo', 'name': '红果短剧',
                'url': 'website:console_dramas_hongguo',
                'icon': 'clapperboard',
                'desc': '预处理导出剧集（解密落盘，供上传外部平台）与第 4 集及以后的外链登记管理。',
            },
        ],
    },
    {
        'title': '用户支持',
        'icon': 'users',
        'items': [
            {
                'key': 'console_users', 'name': '用户管理', 'url': 'website:console_users',
                'icon': 'users', 'desc': '查看用户资料与登录明细（登录过的项目、次数、最后登录、剩余有效天数），支持建号、编辑、封禁、重置密码与删除。',
            },
            {
                'key': 'console_feedback', 'name': '问题反馈', 'url': 'website:console_feedback',
                'icon': 'messages-square',
                'desc': '查看各接入项目提交的反馈（按项目 / 状态 / 类型 / AI 审核状态筛选），回复可带图与视频；'
                        'AI 只提醒、管理员可强制发送；还可手动送审与维护反馈类型字典。',
            },
            {
                'key': 'console_contacts', 'name': '联系方式', 'url': 'website:console_contacts',
                'icon': 'headset',
                'desc': '维护开发者联系方式的「平台字典」（渠道、填写项、跳转链接模板）与各接入项目的具体值；'
                        '展示在对应项目的反馈页与公开区底部，子项目也可调 /api/feedback/contacts 自行渲染。',
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
