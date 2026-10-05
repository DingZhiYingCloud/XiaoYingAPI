"""超级管理员控制台 - 侧边栏菜单（声明式，一处维护）

新增控制台页面时**只在这里加一行**，模板与高亮逻辑无需改动
（与文档中心 /docs/* 的菜单思路一致，但这里是人工声明的固定菜单，
不像文档菜单那样由服务注册表自动生成）。

**分组口径（按「管什么」划分，而不是按「谁用」）**：

| 分组 | 管的对象 | 成员 |
| --- | --- | --- |
| 概览 | 控制台自身 | 控制台首页 |
| 安全 | 控制台自身的防护 | 安全设置 |
| 接口治理 | 对外提供的 API 本身 | 服务策略、接口公告、AI 模型 |
| 数据运营 | 接入方 / 流量 / 站点与内容 | 接入项目、支付设置、账号管理、调用统计、服务余量、官网外观、红果短剧 |
| 用户支持 | 用户体系与用户声音 | 用户管理、问题反馈 |

判断一个模块该进哪组，先问「它管的对象是什么」：
控制台自身的安全开关 → 安全；
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
        'title': '安全',
        'icon': 'shield',
        'items': [
            {
                'key': 'console_security', 'name': '安全设置', 'url': 'website:console_security',
                'icon': 'shield',
                'desc': '控制台自身的安全开关：后台入口隐身（未登录访问后台一律返回 404，'
                        '防止被路径探测发现入口）。',
            },
            {
                'key': 'console_audit', 'name': '操作日志', 'url': 'website:console_audit',
                'icon': 'history',
                'desc': '控制台写操作的审计留痕：谁在什么时候改了哪个功能、结果如何。'
                        '由所有控制台视图的必经入口统一采集，新增页面不会漏记。',
            },
            {
                'key': 'console_ip_bans', 'name': 'IP 封禁', 'url': 'website:console_ip_bans',
                'icon': 'shield-ban',
                'desc': '人工封禁 / 解禁来源 IP（默认 7 天，也能自定义天数或永久）。被封 IP 的 '
                        '/api/ 请求一律返回「IP 已被封禁」，官网前台顶部同步提示原因与解禁时间。',
            },
        ],
    },
    {
        'title': '接口治理',
        'icon': 'shield-check',
        'items': [
            {
                'key': 'console_services', 'name': '服务策略', 'url': 'website:console_services',
                'icon': 'shield-check', 'desc': '按服务 / 线路 / 端点三级配置认证模式、对外状态、文档可见性与使用范围，逐级继承。',
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
                'key': 'console_pay', 'name': '支付设置', 'url': 'website:console_pay',
                'icon': 'credit-card',
                'desc': '在线支付的全局开关、各支付渠道的商户配置'
                        '（商户ID / 密钥加密落库 / 可用支付方式）、订单列表（可手动查单与退款）'
                        '与最近用户余额流水。',
            },
            {
                'key': 'console_accounts', 'name': '账号管理', 'url': 'website:console_accounts',
                'icon': 'key-round',
                'desc': '统一托管第三方平台账号与登录凭据（Cookie）：知乎、小红书、微博、百家号、今日头条等；'
                        '凭据加密落库、页面不回显，并可一键校验凭据是否过期（过期即提示重新登录）。',
            },
            {
                'key': 'console_stats', 'name': '调用统计', 'url': 'website:console_stats',
                'icon': 'chart-column', 'desc': '按服务、接口、项目与结果查看调用量与耗时。',
            },
            {
                'key': 'console_quotas', 'name': '服务余量', 'url': 'website:console_quotas',
                'icon': 'gauge',
                'desc': '监控上游服务账号还剩多少（51代理余额、超级鹰题分），可逐项设置最低数量阈值，'
                        '低于阈值时发邮件提醒（告警只发一次，恢复后重新武装）。',
            },
            {
                'key': 'console_appearance', 'name': '官网外观', 'url': 'website:console_appearance',
                'icon': 'swatch-book',
                'desc': '切换官网首页与接口文档中心的视觉气质（多套预设可切换），并可覆盖首页头图文案；'
                        '颜色仍由访客选择的主题决定，二者互不冲突。',
            },
            {
                'key': 'console_haijiao_register', 'name': '海角自动注册',
                'url': 'website:console_haijiao_register',
                'icon': 'user-plus',
                'desc': '全自动注册海角社区账号：出口可选直连 / 51代理 / 巨量代理（默认 51代理），'
                        '验证码交超级鹰打码识别（识别类型可选、默认 1902），'
                        '打码没打对时自动向超级鹰报错返分并换图重试，进度实时推送（注册中请勿关闭页面）。',
            },
            {
                'key': 'console_order_migration', 'name': '代练搬单',
                'url': 'website:console_order_migration',
                'icon': 'repeat',
                'desc': '把代练通王者荣耀订单自动搬运到代练丸子发单：标题照搬、默认排位、区服按代练通大区，'
                        '发布价 =（代练通价 − 手续费）× 80%；监控丸子「被接单」后回代练通接单取账号，'
                        '抢接失败自动撤单并告警。可手动执行一轮或开启后台自动运行。',
            },
            {
                'key': 'console_push_logs', 'name': '推送日志',
                'url': 'website:console_push_logs',
                'icon': 'send',
                'desc': '消息推送服务（当前接入 Server酱）每次推送的记录：标题 / 正文摘要、发起项目、'
                        '成功或失败、上游返回码与推送ID，便于回看与排错。SendKey 在「账号管理」维护。',
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
