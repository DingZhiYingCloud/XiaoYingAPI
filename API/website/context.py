"""官网前台模板上下文处理器：向全站模板注入当前登录态

登录态信息存于会话 request.session['website_user']，结构：
    {user_id, account, username, token, expire_time, email?, phone?}
未登录时为 None，模板统一用 website_user 判断。
"""


def website_user(request):
    """返回 {'website_user': dict|None}，供母版导航/页脚等判断登录状态"""
    return {'website_user': request.session.get('website_user')}
