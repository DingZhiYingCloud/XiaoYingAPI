"""微博服务 - 业务层

职责：把「取登录凭据（调用方自带 优先，否则平台托管）→ 调微博爬虫」编排好，
返回 `(ok, data/message)`；不组装 HTTP 响应、不读 `request` 对象。

凭据口径（与知乎服务一致）：
    · **调用方自带**：请求里带了 `cookie` 就用它，仅本次生效 —— 不落库、不参与账号表，
      失败也不会去改平台账号的状态；
    · **平台托管**：没带就回落到「平台账号」表里的一份可用凭据（后台 `/console/accounts/`
      维护）；调用中发现失效会顺手把该账号标成「已过期」，与人工点「校验」等效。
"""
from django.conf import settings
from django.core import signing

from API.common import platform_accounts
from SpiderServices.weibo.main import (
    WeiboCredentialExpired,
    WeiboError,
    WeiboSpider,
)

PLATFORM = 'weibo'
NO_ACCOUNT_MESSAGE = '未提供 Cookie，且平台尚未配置可用的微博账号，请自带 Cookie 或在后台「账号管理」中添加'

# 「代理播放」地址的时效令牌：<video> 标签没法带项目签名，故用 Django 签名令牌自证。
# 令牌里只放一个微博 id（不含任何秘密）—— 播放时按 id 现场解析新鲜直链，所以地址可以长期复用。
VIDEO_TOKEN_SALT = 'weibo.video'
VIDEO_STREAM_PATH = '/api/weibo/video'
# 令牌有效期（秒）：给得比较长，便于调用方把 stream_url 连同内容一起长期保存；
# 令牌本身不含秘密，真要吊销换 SALT 即可。可在 .env 用 WEIBO_STREAM_TOKEN_TTL 覆盖。
VIDEO_TOKEN_TTL = int(getattr(settings, 'WEIBO_STREAM_TOKEN_TTL', 7 * 24 * 3600))


def make_video_token(status_id):
    """生成「代理播放」地址的时效令牌（<video> 无法携带项目签名，故用签名令牌自证）"""
    return signing.dumps({'id': str(status_id)}, salt=VIDEO_TOKEN_SALT, compress=True)


def parse_video_token(token):
    """校验并解出令牌里的微博 id

    :return: (status_id, None) 或 (None, 错误提示)
    """
    if not token:
        return None, '缺少播放令牌'
    try:
        data = signing.loads(token, salt=VIDEO_TOKEN_SALT, max_age=VIDEO_TOKEN_TTL)
    except signing.SignatureExpired:
        return None, '播放地址已过期，请重新获取'
    except signing.BadSignature:
        return None, '播放地址无效'
    status_id = str(data.get('id') or '').strip()
    if not status_id:
        return None, '播放地址无效'
    return status_id, None


def _usable_spider(cookie=''):
    """取一个抓取器：调用方自带 Cookie 优先，没有才用平台托管的账号

    :param cookie: 调用方自带的登录 Cookie（可为空）
    :return: (spider, account, error_message)
        · 调用方自带 Cookie → account 为 None（不是我们的账号，状态无需回写）
        · 回落平台账号      → account 为该账号对象（凭据失效时用来标「已过期」）
    """
    if cookie:
        return WeiboSpider(cookie=cookie), None, None
    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        return None, None, NO_ACCOUNT_MESSAGE
    return WeiboSpider(cookie=platform_accounts.credential_of(account)), account, None


def get_channels(cookie=''):
    """微博频道分类（「我的频道」+「频道推荐」）

    :param cookie: 调用方自带的登录 Cookie；留空则用平台托管的账号
    :return: (True, 分组列表) / (False, 中文错误说明)
    """
    spider, _account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        return True, spider.get_channels()
    except WeiboError as exc:
        return False, str(exc)


def get_feed(channel, containerid, limit, since_id, cookie=''):
    """按频道取内容

    :param cookie: 调用方自带的登录 Cookie；留空则用平台托管的账号
    :return: (True, {channel, containerid, count, total, since_id, next_since_id, has_more, list})
             / (False, 中文错误说明)
    """
    spider, account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        return True, spider.get_feed(channel, containerid, limit, since_id)
    except WeiboCredentialExpired as exc:
        if account is not None:
            # 只有平台自己的账号才回写「已过期」；调用方自带的凭据与我们无关
            platform_accounts.mark_expired(account, str(exc))
        return False, str(exc)
    except WeiboError as exc:
        return False, str(exc)


def check_credential(cookie=''):
    """校验微博登录凭据是否有效

    · 调用方自带 cookie → 只校验这一份，**完全不碰平台托管账号**（不读也不写状态）；
    · 未传 cookie      → 校验平台托管的账号，并把结果回写到账号表。

    平台托管分支：优先挑「可用账号」；若所有账号都已是过期态，也挑一个出来校验 ——
    这样用户在浏览器重新登录、把新 Cookie 填回后台后，一次校验就能把状态恢复。

    :return: (True, {valid, account, message}) / (False, 中文错误说明)
    """
    if cookie:
        ok, message = WeiboSpider(cookie=cookie).check_cookie()
        return True, {'valid': ok, 'account': '', 'message': message}

    from API.models import PlatformAccount

    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        account = (PlatformAccount.objects.filter(platform=PLATFORM)
                   .exclude(credential='').order_by('-updated_time').first())
    if account is None:
        return False, NO_ACCOUNT_MESSAGE

    ok, message = platform_accounts.check_account(account)
    return ok, {'valid': ok, 'account': account.account, 'message': message}


def open_video(status_id, range_header='', cookie=''):
    """按微博 id 解析直链并打开视频流（「代理播放」用）

    两步都在爬虫层完成：先按 id 解析**新鲜**直链（微博直链带 `Expires` 签名、会过期），
    再带 `Referer` 打开流（CDN 有 Referer 防盗链，缺了会 403）。

    :return: (True, requests.Response) / (False, 中文错误说明)
        —— 调用方用完负责 `response.close()`
    """
    spider, account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        url = spider.get_video_url(status_id)
        return True, spider.open_video_stream(url, range_header)
    except WeiboCredentialExpired as exc:
        if account is not None:
            # 只有平台自己的账号才回写「已过期」；调用方自带的凭据与我们无关
            platform_accounts.mark_expired(account, str(exc))
        return False, str(exc)
    except WeiboError as exc:
        return False, str(exc)
