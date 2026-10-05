"""知乎服务 - 业务层

职责：把「取登录凭据（调用方自带 优先，否则平台托管）→ 调知乎爬虫」编排好，
返回 `(ok, data/message)`；不组装 HTTP 响应、不读 `request` 对象。

凭据口径：
    · **调用方自带**：请求里带了 `cookie` 就用它，仅本次生效 —— 不落库、不参与账号表，
      失败也不会去改平台账号的状态；
    · **平台托管**：没带就回落到「平台账号」表里的一份可用凭据（后台 `/console/accounts/`
      维护）；调用中发现失效会顺手把该账号标成「已过期」，与人工点「校验」等效。
"""
from API.common import platform_accounts
from SpiderServices.zhihu.main import (
    ZhihuCredentialExpired,
    ZhihuError,
    ZhihuSpider,
)

PLATFORM = 'zhihu'
NO_ACCOUNT_MESSAGE = '未提供 Cookie，且平台尚未配置可用的知乎账号，请自带 Cookie 或在后台「账号管理」中添加'


def _usable_spider(cookie=''):
    """取一个抓取器：调用方自带 Cookie 优先，没有才用平台托管的账号

    :param cookie: 调用方自带的登录 Cookie（可为空）
    :return: (spider, account, error_message)
        · 调用方自带 Cookie → account 为 None（不是我们的账号，状态无需回写）
        · 回落平台账号      → account 为该账号对象（凭据失效时用来标「已过期」）
    """
    if cookie:
        return ZhihuSpider(cookie=cookie), None, None
    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        return None, None, NO_ACCOUNT_MESSAGE
    return ZhihuSpider(cookie=platform_accounts.credential_of(account)), account, None


def get_hot(limit=50, cookie=''):
    """知乎热榜

    :param cookie: 调用方自带的登录 Cookie；留空则用平台托管的账号
    :return: (True, 列表) / (False, 中文错误说明)
    """
    spider, account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        return True, spider.get_hot(limit)
    except ZhihuCredentialExpired as exc:
        if account is not None:
            # 只有平台自己的账号才回写「已过期」；调用方自带的凭据与我们无关
            platform_accounts.mark_expired(account, str(exc))
        return False, str(exc)
    except ZhihuError as exc:
        return False, str(exc)


def check_credential(cookie=''):
    """校验知乎登录凭据是否有效

    · 调用方自带 cookie → 只校验这一份，**完全不碰平台托管账号**（不读也不写状态）；
    · 未传 cookie      → 校验平台托管的账号，并把结果回写到账号表。

    平台托管分支：优先挑「可用账号」；若所有账号都已是过期态，也挑一个出来校验 ——
    这样用户在浏览器重新登录、把新 Cookie 填回后台后，一次校验就能把状态恢复。

    :return: (True, {valid, account, message}) / (False, 中文错误说明)
    """
    if cookie:
        ok, message = ZhihuSpider(cookie=cookie).check_cookie()
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


def get_question(question_id, answer_limit=5, comment_limit=3,
                 question_comment_limit=10, cookie=''):
    """知乎问题详情（问题本体 / 回答 / 评论 / 相关问题 / 大家都在搜）

    :param question_id: 知乎问题 ID（视图已归一为纯数字 ID）
    :param cookie: 调用方自带的登录 Cookie；留空则用平台托管的账号
    :return: (True, 详情 dict) / (False, 中文错误说明)
    """
    spider, account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        return True, spider.get_question(question_id, answer_limit, comment_limit,
                                         question_comment_limit)
    except ZhihuCredentialExpired as exc:
        if account is not None:
            # 只有平台自己的账号才回写「已过期」；调用方自带的凭据与我们无关
            platform_accounts.mark_expired(account, str(exc))
        return False, str(exc)
    except ZhihuError as exc:
        return False, str(exc)


def get_article(article_id, comment_limit=10, cookie=''):
    """知乎专栏文章详情（文章本体 / 评论 / 大家都在搜）

    :param article_id: 知乎专栏文章 ID（视图已归一为纯数字 ID）
    :param cookie: 调用方自带的登录 Cookie；留空则用平台托管的账号
    :return: (True, 详情 dict) / (False, 中文错误说明)
    """
    spider, account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        return True, spider.get_article(article_id, comment_limit)
    except ZhihuCredentialExpired as exc:
        if account is not None:
            platform_accounts.mark_expired(account, str(exc))
        return False, str(exc)
    except ZhihuError as exc:
        return False, str(exc)


def get_search(keyword, limit=20, offset=0, cookie=''):
    """知乎综合搜索（结果自带完整正文与图片 / 大家都在搜）

    :param keyword: 搜索关键词
    :param cookie: 调用方自带的登录 Cookie；留空则用平台托管的账号
    :return: (True, {count, is_end, next_offset, list, hot_searches}) / (False, 中文错误说明)
    """
    spider, account, error = _usable_spider(cookie)
    if error:
        return False, error
    try:
        return True, spider.get_search(keyword, limit, offset)
    except ZhihuCredentialExpired as exc:
        if account is not None:
            platform_accounts.mark_expired(account, str(exc))
        return False, str(exc)
    except ZhihuError as exc:
        return False, str(exc)
