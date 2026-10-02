"""官网前台模板上下文处理器：向全站模板注入登录态、页脚友链与联系方式

登录态信息存于会话 request.session['website_user']，结构：
    {user_id, account, username, token, expire_time, email?, phone?}
未登录时为 None，模板统一用 website_user 判断。
"""
from API.apis.feedback.utils import serialize_contacts
from API.models import FriendLink, SiteAppearance

from .services import SERVICES


def website_user(request):
    """返回 {'website_user': dict|None}，供母版导航/页脚等判断登录状态"""
    return {'website_user': request.session.get('website_user')}


def friend_links(request):
    """返回 {'footer_friend_links': [...]}，供页脚「友情链接」nav 渲染

    数据来自 SEO 友情链接模块（FriendLink）：只取启用项，按排序权重倒序
    （沿用模型 Meta.ordering：-sort, -create_time）。无数据时为空列表，
    模板据此整块隐藏。
    """
    return {'footer_friend_links': list(FriendLink.objects.filter(status=True))}


def footer_contacts(request):
    """返回 {'footer_contacts': [...]}，供页脚「联系我们」nav 渲染

    取的是**官网自身那个接入项目**（`settings.WEB_APP_NAME`，默认「小影API官网」）
    在后台「联系方式」模块（/console/contacts/）里维护的那份数据。

    前台不再硬编码任何微信 / Telegram 账号：后台给官网项目配几个平台，
    页脚就展示几个（平台被停用或没填值的不出现）；一条都没有时为空列表，
    模板据此整块隐藏。读取口径与反馈页「开发者联系方式」完全一致
    （同一个 serialize_contacts），因此两处展示永远同步。
    """
    from .views import _web_app      # 局部导入：本模块在 Django 启动阶段即被模板引擎加载，
                                     # 而 views 会连带导入验证码 / 用户中心等重依赖（同 feedback_views 的做法）
    return {'footer_contacts': serialize_contacts(_web_app())}


def _fill_count(text, count):
    """把外观文案里的 {n} 占位替换成当前聚合服务数量（其余原样保留）"""
    return (text or '').replace('{n}', str(count))


def ip_ban_notice(request):
    """返回 {'ip_ban_notice': dict|None}，供母版顶部「IP 已被封禁」提示条渲染

    数据由 `IPBanMiddleware` 挂在 request 上（控制台 / 后台路径不参与判定，那里恒为 None）。
    提示条里的联系方式直接用同页已有的 footer_contacts，不在这里重复取数。
    """
    ban = getattr(request, 'ip_ban', None)
    if ban is None or request.path.startswith('/console/'):
        return {'ip_ban_notice': None}
    return {'ip_ban_notice': {
        'ip': ban.ip,
        'reason': ban.reason,
        'permanent': ban.is_permanent,
        'expire_time': ban.expire_time,
    }}


def site_appearance(request):
    """返回 {'site_feel', 'site_appearance', 'site_hero'}，供官网首页与文档中心套用视觉气质

    - site_feel：预设键，母版写进 <html data-feel="...">，样式见 API/static/css/input.css。
      控制台等未使用 `feel-*` 类名的页面不受影响（预设样式只挂在 feel-* 上）。
    - site_hero：首页 Hero 的文案覆盖（留空表示用模板内置文案，模板侧自行回退）。
    """
    appearance = SiteAppearance.get_solo()
    count = len(SERVICES)
    return {
        'site_feel': appearance.preset,
        'site_appearance': appearance,
        'site_hero': {
            'badge': (appearance.hero_badge or '').strip(),
            'title': _fill_count(appearance.hero_title, count),
            'subtitle': _fill_count(appearance.hero_subtitle, count),
        },
    }
