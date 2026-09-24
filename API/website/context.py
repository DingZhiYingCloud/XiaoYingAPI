"""官网前台模板上下文处理器：向全站模板注入登录态与页脚友链

登录态信息存于会话 request.session['website_user']，结构：
    {user_id, account, username, token, expire_time, email?, phone?}
未登录时为 None，模板统一用 website_user 判断。
"""
from API.models import FriendLink


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
