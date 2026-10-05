"""平台账号凭据的通用能力层（跨平台的登录凭据托管与有效性校验）

这是「账号托管」这套底层能力的**唯一扩展点**：知乎、小红书、微博、百家号…
共用同一张账号表（`API/models/Accounts/account.py` 的 `PlatformAccount`），
差异只有「怎么判断这份凭据还有效」，各家实现一个校验函数即可。

职责：
    1. 可插拔的**校验器注册表**（下面 `_CHECKERS`）—— 新增平台只加一行
    2. 统一入口：校验某账号的凭据 / 取一个可用账号 / 取凭据明文
    3. 校验结果自动回写账号表（`status` / `check_message` / `last_check_time`）

为什么放在 `API/common/`：它被「后台账号管理页」与「各平台的 API 服务」共用，
不专属任何一个平台，与 `ip_guard.py` / `credential_crypto.py` 同类。

**新增一个平台（以小红书为例）只要三步**：
    1. `API/models/Accounts/account.py` 的 `Platform` 枚举加 `XIAOHONGSHU`；
    2. 在 `SpiderServices/xiaohongshu/` 里实现
       ``check_credential(cookie: str) -> tuple[bool, str]``（True=有效，str 给人和后台看）；
    3. 在下面的 `_CHECKERS` 里加一行。**无需改模型、无需迁移。**
"""
import importlib
import logging

logger = logging.getLogger('api.accounts')

# ==================== 校验器注册表 ====================
# 平台标识 -> "模块路径:函数名"。函数签名：``(cookie: str) -> (bool, str)``
# 返回值约定：(True, 说明) 表示凭据有效；(False, 原因) 表示已过期/失效，需要重新登录。
# 用「模块路径字符串 + 惰性导入」而不是直接 import：避免 Django 启动期就加载各平台爬虫，
# 也避免爬虫层与 common 层互相 import 形成环。
_CHECKERS = {
    'zhihu': 'SpiderServices.zhihu.main:check_credential',
    'weibo': 'SpiderServices.weibo.main:check_credential',
    'dlt': 'SpiderServices.DaiLianTong.utils:check_credential',
    'dlwz': 'SpiderServices.DaiLianWanZi.utils:check_credential',
}


def has_checker(platform: str) -> bool:
    """该平台是否已接入校验器（后台据此决定是否显示「校验」按钮）"""
    return platform in _CHECKERS


def supported_platforms() -> list[str]:
    """已接入校验器的平台清单"""
    return sorted(_CHECKERS)


def _load_checker(platform: str):
    """惰性加载校验函数；未注册或加载失败返回 None"""
    path = _CHECKERS.get(platform)
    if not path:
        return None
    module_path, _, func_name = path.partition(':')
    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except Exception:
        logger.exception('平台校验器加载失败 [%s] 路径=%s', platform, path)
        return None


def credential_of(account) -> str:
    """取账号的登录凭据明文（字段层已自动 AES 解密；页面与接口不应回显它）"""
    return (account.credential or '').strip()


def check_account(account):
    """校验一个账号的凭据是否有效，并把结果回写到账号表

    :return: (ok: bool, message: str)
        · 未录入凭据 / 未接入校验器 → 不改变 status，只更新说明与时间
        · 校验器返回 False          → status 置为 expired（需重新登录）
        · 校验器抛异常 / 加载失败    → status 置为 expired，说明写「校验异常」
    """
    from django.utils import timezone

    from API.models.Accounts.account import AccountStatus

    cookie = credential_of(account)
    now = timezone.now()

    if not cookie:
        account.check_message = '未录入登录凭据，无法校验'
        account.last_check_time = now
        account.save(update_fields=['check_message', 'last_check_time', 'updated_time'])
        return False, account.check_message

    checker = _load_checker(account.platform)
    if checker is None:
        account.check_message = '该平台暂未接入凭据校验'
        account.last_check_time = now
        account.save(update_fields=['check_message', 'last_check_time', 'updated_time'])
        return False, account.check_message

    try:
        ok, message = checker(cookie)
    except Exception as exc:
        logger.exception('凭据校验异常 [%s/%s]', account.platform, account.account)
        ok, message = False, f'校验异常：{exc}'

    message = (message or '').strip()[:255]
    account.check_message = message
    account.last_check_time = now
    account.status = AccountStatus.VALID if ok else AccountStatus.EXPIRED
    account.save(update_fields=['status', 'check_message', 'last_check_time', 'updated_time'])
    return bool(ok), message


def get_available_account(platform: str):
    """取一个「有凭据且未被判为过期」的账号；没有则返回 None

    优先级：valid（已校验有效）> unknown（还没校验过），同档按最近更新排前。
    —— 这样「刚导入、还没校验」的账号也能被服务直接用起来。
    """
    from API.models.Accounts.account import AccountStatus, PlatformAccount

    queryset = PlatformAccount.objects.filter(platform=platform).exclude(credential='')
    for status in (AccountStatus.VALID, AccountStatus.UNKNOWN):
        account = queryset.filter(status=status).order_by('-updated_time').first()
        if account:
            return account
    return None


def mark_expired(account, message=''):
    """把账号标记为「已过期（需重新登录）」

    供各平台服务在**实际调用**中发现凭据失效时顺手回写 —— 这样即便没跑校验，
    状态也会自动对齐真实情况（与「人工点校验」等效）。
    """
    from django.utils import timezone

    from API.models.Accounts.account import AccountStatus

    account.status = AccountStatus.EXPIRED
    account.check_message = (message or account.check_message or '')[:255]
    account.last_check_time = timezone.now()
    account.save(update_fields=['status', 'check_message', 'last_check_time', 'updated_time'])
    return account
