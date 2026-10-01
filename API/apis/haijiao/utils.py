"""海角社区 爬虫调用封装

本模块对 SpiderServices.haijiao.main 中的 HaijiaoSpider 进行薄封装：
- 每次调用创建新的爬虫实例（无状态，线程安全）
- 统一捕获异常，返回 (是否成功, 数据或错误信息) 二元组

注册为两步式（验证码需人工识别，后续可接入验证码识别自动化）：
  ① create_register_captcha()  取验证码，并把 captchaId 与本次出口代理写入缓存，返回 captcha_token
  ② submit_register()          凭 captcha_token 取回同一代理再提交注册
     —— 两步必须同一出口 IP，故代理不放请求参数、而是随会话缓存复用。
  注册成功后会把账号写入 haijiao_account 表（供后续使用）。

账号表（HaijiaoAccount）提供增删改查；登录支持直传账号或按 account_id 取库内账号。

金币签到：用账号表里存的 user_id + token 调源站签到接口（见 sign_in / sign_in_all），
先查任务状态再提交，已签到不重复提交。

自动注册：iter_auto_register() 把「取码 → 超级鹰打码 → 提交」串成一条流并逐帧报进度，
源站回「验证码错误」时自动向超级鹰报错返分并换图重试（详见该函数说明）；
仅供超管控制台的自动注册页使用，不提供对外接口。
"""
import base64
import logging
import os
import secrets
import string
import time

from django.core.cache import caches
from django.db.models import Q
from django.utils.timezone import localdate

from API.apis.chaojiying import utils as chaojiying_utils
from API.models import HaijiaoAccount
from SpiderServices.haijiao import utils as spider_utils
from SpiderServices.haijiao.main import HaijiaoSpider

logger = logging.getLogger(__name__)

# 注册验证码会话缓存：用文件缓存（跨进程共享，多 worker 下也能取到）；
# key 前缀与爬虫的数据缓存区分开，避免相互覆盖。
_SESSION_CACHE = caches['haijiao']
_SESSION_PREFIX = 'register_session:'
SESSION_TTL = 600   # 验证码会话有效期（秒）

# 自动生成的注册账号规则：源站用户名上限 12 字符，前缀 xy_ 占 3 位，故随机部分最多 9 位
USERNAME_PREFIX = 'xy_'
USERNAME_RANDOM_LEN = 9
PASSWORD_LEN = 10
MAX_BATCH_SIZE = 20   # 单次批量注册上限


def _run(action, fn, user_id=None, user_token=None):
    """
    执行爬虫操作，统一异常处理。

    :param action: 操作名称（用于错误提示前缀）
    :param fn: 接收爬虫实例的回调
    :param user_id: 覆盖默认登录凭据的账号 ID（可选）
    :param user_token: 覆盖默认登录凭据的登录 token（可选）
    :return: tuple[bool, Any] (True, data) 或 (False, message)
    """
    spider = HaijiaoSpider(user_id=user_id, user_token=user_token)
    try:
        return True, fn(spider)
    except Exception as e:
        return False, f"{action}失败: {e}"


def get_topics(tab='hot', page=1):
    """获取内容列表（分页）"""
    return _run("获取内容列表", lambda s: s.get_topics(tab=tab, page=page))


def get_domain_config():
    """获取今日域名配置（今日大陆可访问域名 / 备用 / 海外 / 影视站域名 + 客服邮箱）"""
    return _run("获取今日域名配置", lambda s: s.get_domain_config())


def get_topic_detail(topic_id, user_id=None, user_token=None):
    """获取帖子详情（可传自定义登录凭据 user_id / user_token）"""
    return _run("获取帖子详情", lambda s: s.get_topic_detail(topic_id),
                user_id=user_id, user_token=user_token)


def get_topic_comments(topic_id, page=1, search_type=0):
    """获取帖子评论列表（分页；search_type: 0=全部 1=只看楼主）"""
    return _run("获取帖子评论",
                lambda s: s.get_topic_comments(topic_id, page=page, search_type=search_type))


def get_comment_replies(comment_id, page=1):
    """获取某条主评论下的二级评论列表（分页）"""
    return _run("获取二级评论",
                lambda s: s.get_comment_replies(comment_id, page=page))


def search_topics(key, page=1, node_id=0):
    """搜索帖子（分页）"""
    return _run("搜索帖子", lambda s: s.search_topics(key, page=page, node_id=node_id))


def get_video_playlist(topic_id, attachment_id):
    """生成可直接播放的 m3u8（还原真密钥）"""
    return _run("生成视频播放列表",
                lambda s: s.get_video_playlist(topic_id, attachment_id))


def fetch_image(url):
    """抓取并解码混淆图片（返回 data URI）"""
    return _run("解码图片", lambda s: s.fetch_image(url))


def _image_data_uri(image: bytes) -> str:
    """把验证码图片转成 data URI（按文件头判断类型）"""
    if image[:4] == b'\x89PNG':
        mime = 'image/png'
    elif image[:3] == b'\xff\xd8\xff':
        mime = 'image/jpeg'
    elif image[:3] == b'GIF':
        mime = 'image/gif'
    else:
        mime = 'image/png'
    return f'data:{mime};base64,{base64.b64encode(image).decode()}'


def generate_credentials() -> dict:
    """生成一组注册用账号凭据

    规则：用户名 = xy_ + 9 位随机（小写字母/数字，合计 12 位，符合源站用户名长度上限）；
          密码 = 10 位（必含大写、小写、数字）；邮箱 = <用户名>@<6 位随机小写字母>.com。

    :return: {'username', 'password', 'email'}
    """
    suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits)
                     for _ in range(USERNAME_RANDOM_LEN))
    username = f'{USERNAME_PREFIX}{suffix}'

    pool = string.ascii_letters + string.digits
    chars = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
             secrets.choice(string.digits)]
    chars += [secrets.choice(pool) for _ in range(PASSWORD_LEN - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    password = ''.join(chars)

    domain = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(6))
    return {'username': username, 'password': password, 'email': f'{username}@{domain}.com'}


def _fetch_one_captcha(provider=None):
    """
    取一张注册验证码，并把「验证码会话」写入缓存（人工注册与自动注册共用）。

    源站要求取码与提交注册必须同一出口 IP，故代理不放请求参数、而是随会话缓存带回。

    :param provider: 代理出口线路，取值见 PROXY_PROVIDERS；None / 'direct' = 直连
    :return: (True, (captcha_token, 源站原始返回 dict)) 或 (False, msg)
    """
    ok, result = _run("获取注册验证码", lambda s: s.register_captcha(provider=provider))
    if not ok:
        return False, result

    token = secrets.token_urlsafe(24)
    _SESSION_CACHE.set(_SESSION_PREFIX + token, {
        'captcha_id': result.get('captcha_id'),
        'proxies': result.get('proxies'),
        # 取码会话 Cookie：验证码若与会话绑定，提交时必须复用
        'cookies': result.get('cookies'),
    }, SESSION_TTL)
    return True, (token, result)


def create_register_captcha(use_proxy=False):
    """
    取注册验证码（两步式注册的第一步）。

    :param use_proxy: 是否经代理请求（源站注册有 IP 限制）；true 时用默认代理线路
                      DEFAULT_PROXY_PROVIDER，false = 直连
    :return: (True, {captcha_token, captcha_image, expires_in, use_proxy, proxy}) 或 (False, msg)
    """
    ok, result = _fetch_one_captcha(
        DEFAULT_PROXY_PROVIDER if use_proxy else None)
    if not ok:
        return False, result
    token, raw = result
    return True, {
        'captcha_token': token,
        'captcha_image': _image_data_uri(raw.get('captcha_image') or b''),
        'expires_in': SESSION_TTL,
        'use_proxy': bool(use_proxy),
        'proxy': raw.get('proxy'),
    }


def submit_register(captcha_token, captcha_code, username, password, email):
    """
    提交注册（两步式注册的第二步）。

    走代理注册时，本方法会用第一步缓存下来的同一代理出口提交，保证与取验证码同 IP。

    :param captcha_token: 取验证码时返回的会话 token
    :param captcha_code: 人工识别的验证码
    :param username: 用户名
    :param password: 密码
    :param email: 邮箱
    :return: (True, {user_id, username, nickname, email, token}) 或 (False, msg)
    """
    cache_key = _SESSION_PREFIX + (captcha_token or '')
    session = _SESSION_CACHE.get(cache_key)
    if not session:
        return False, '参数值非法: 验证码会话不存在或已过期，请重新获取注册验证码'

    try:
        ok, result = _run("注册", lambda s: s.submit_register(
            username=username, password=password, email=email,
            captcha_id=session.get('captcha_id'), captcha_code=captcha_code,
            proxies=session.get('proxies'), cookies=session.get('cookies')))
    finally:
        # 验证码一次性：无论成功与否都作废本次会话（源站侧 captchaId 同样只能用一次）
        _SESSION_CACHE.delete(cache_key)
    if not ok:
        return False, result

    user = (result or {}).get('user') or {}
    info = {
        'user_id': user.get('id'),
        'username': user.get('username'),
        'nickname': user.get('nickname'),
        'email': user.get('email'),
        'token': (result or {}).get('token'),
    }
    _save_registered_account(info, password)
    return True, info


def _save_registered_account(info, password):
    """注册成功入库（按源站用户 ID 幂等 upsert）

    入库失败只记日志、不影响注册结果——账号已在源站创建成功，凭证不能因落库异常丢掉响应。
    """
    if not info.get('user_id'):
        return
    try:
        HaijiaoAccount.objects.update_or_create(
            user_id=str(info['user_id']),
            defaults={
                'username': info.get('username') or '',
                'password': password,
                'email': info.get('email') or '',
                'nickname': info.get('nickname') or '',
                'token': info.get('token') or '',
            })
    except Exception:       # noqa: BLE001 - 落库异常不应影响已成功的注册
        logger.exception('海角社区账号入库失败: user_id=%s', info.get('user_id'))


def register_batch(items):
    """
    批量注册（逐个提交，成功项自动入库）。

    每项为 {'captcha_token', 'captcha_code'}，用户名/密码/邮箱默认由服务端生成
    （见 generate_credentials），也可在项内显式指定覆盖。

    :param items: 列表，每项一个 dict
    :return: (True, {total, success_count, failed_count, items: [每项结果]})
    """
    results = []
    for index, item in enumerate(items):
        token = (item.get('captcha_token') or '').strip()
        code = (item.get('captcha_code') or '').strip()
        generated = generate_credentials()
        username = (item.get('username') or '').strip() or generated['username']
        password = (item.get('password') or '').strip() or generated['password']
        email = (item.get('email') or '').strip() or generated['email']

        if not token or not code:
            results.append({'index': index, 'success': False, 'username': username,
                            'msg': '参数缺失: 每项需提供 captcha_token 与 captcha_code'})
            continue

        ok, res = submit_register(token, code, username, password, email)
        if ok:
            results.append({'index': index, 'success': True, 'username': res['username'],
                            'password': password, 'email': res['email'],
                            'user_id': res['user_id'], 'token': res['token']})
        else:
            results.append({'index': index, 'success': False, 'username': username,
                            'email': email, 'msg': res})

    success_count = sum(1 for r in results if r['success'])
    return True, {
        'total': len(results),
        'success_count': success_count,
        'failed_count': len(results) - success_count,
        'items': results,
    }


# ==================== 自动注册（超级鹰打码） ====================

# 识别类型的**默认值**（按站点当前验证码形态定，控制台页面上可改，
# 取值见 SpiderServices.Chaojiying.utils.CODETYPES：1902 = 4~6 位英文数字）。
OCR_CODETYPE = '1902'

# 代理出口的**默认线路**（控制台页面上可改；直连用 'direct' 表示）。
# 生产服务器在海外，51代理 的代理 IP 从那边直连一律超时，故线上用 .env 的
# HAIJIAO_REGISTER_PROXY 把默认改成 relay（经国内中转，见 scripts/hj_relay）；
# 本地保持默认的 51daili 直连即可。
DEFAULT_PROXY_PROVIDER = (os.getenv('HAIJIAO_REGISTER_PROXY', '') or '').strip() or '51daili'

# 单个账号的验证码最多尝试几次（失败一次就换一张新图重新识别）
MAX_CAPTCHA_RETRY = 3
# 判定「源站因验证码拒绝」的关键词
CAPTCHA_ERROR_KEYWORD = '验证码'
# 报错返分的重试次数与退避基数（秒）
REFUND_RETRIES = 3
REFUND_RETRY_DELAY = 1.0
# 平台的「确定性拒绝」错误码：重试没有意义，发一次就收手，免得反复打扰平台
# （取值见 SpiderServices/Chaojiying/utils.py 的 ERROR_CODES / 官方错误码表）
_REFUND_FATAL_CODES = (-1011, -1013, -10132, -10133)


def _is_captcha_error(message) -> bool:
    """源站的失败消息是否为「验证码」类错误（即打码没打对）

    实测源站在验证码错误时返回 {"errorCode":1000,"message":"验证码错误"}，
    按关键词而非整句匹配，源站换文案也能命中。
    """
    return CAPTCHA_ERROR_KEYWORD in str(message or '')


def _report_ocr_error(pic_id):
    """调超级鹰「报错返分」退回这次识别扣掉的题分

    官方口径（https://www.chaojiying.com/api-5.html）：仅识别结果确实错误时才可调用，
    且必须在拿到 pic_id 后 3 分钟内——本流程是秒级调用，天然满足。

    失败会退避重试 REFUND_RETRIES 次（官方要求「识别错了就必须报错返分」，
    所以这里尽力而为，不能一次失败就算了）；命中平台的确定性拒绝码则不再重试。

    :return: (是否退分成功, 失败原因)
    """
    if not pic_id:
        return False, '缺少 pic_id'
    reason = ''
    for attempt in range(1, REFUND_RETRIES + 1):
        result = chaojiying_utils.report_error(pic_id)
        code = result.get('code')
        if code == 0:
            return True, ''
        reason = f'错误码 {code}: {result.get("message")}'
        logger.warning('超级鹰报错返分失败（第 %s/%s 次）: pic_id=%s %s',
                       attempt, REFUND_RETRIES, pic_id, reason)
        if code in _REFUND_FATAL_CODES or attempt == REFUND_RETRIES:
            break
        time.sleep(REFUND_RETRY_DELAY * attempt)
    return False, reason


def iter_auto_register(count, provider=DEFAULT_PROXY_PROVIDER, max_retry=MAX_CAPTCHA_RETRY,
                       codetype=OCR_CODETYPE):
    """自动注册账号（取码 → 超级鹰打码 → 提交入库），逐帧 yield 进度

    出口三选一（对应控制台页面上的「出口」下拉）：直连，或经 51代理 / 巨量代理
    （源站对注册有 IP 限制）。

    单个账号的流程：
      ① 取一张注册验证码（用户名 / 密码 / 邮箱服务端自动生成）；
      ② 上传超级鹰识别（识别类型 codetype，上传即扣题分）；
      ③ 提交注册（与取码复用同一出口 IP）。若源站回「验证码错误」——打码没打对——
         就调超级鹰「报错返分」退回这 15 题分，并换一张新验证码重试（最多 max_retry 次）；
         其它失败（网络异常 / 用户名已存在 / 密码不合规 …）**不返分**：
         那些情况超级鹰并没有识别错，恶意报错会被平台评估信用。

    **重试口径**：只有源站明确给出「非验证码」的业务性拒绝（如用户名已存在）才直接判失败；
    取码失败（源站偶尔把验证码图 302 到备用域名后 404）、打码平台失败、验证码错误
    这几种都换一张重来 —— 前两种没花题分、第三种尝试返分，重试的边际成本很低。
    每次重试都会**重新取一条代理**（换出口），坏出口不会拖死整批。

    注册成功的账号由 submit_register 自动写入账号库（密码 AES 加密落库）。

    :param count: 要注册的账号数（1 ~ MAX_BATCH_SIZE）
    :param provider: 代理出口线路（见 SpiderServices.haijiao.main.PROXY_PROVIDERS），
                     默认 DEFAULT_PROXY_PROVIDER；'direct' 或 None = 直连
    :param max_retry: 单个账号最多尝试几次验证码（含首次）
    :param codetype: 超级鹰识别类型（取值见 SpiderServices.Chaojiying.utils.CODETYPES），
                     默认 OCR_CODETYPE；不同类型单价不同，由调用方选
    :return: 生成器，逐帧 yield dict（字节由视图层序列化成 SSE 帧）：
        {'type': 'start',  'total'}
        {'type': 'log',    'index', 'total', 'text'}
        {'type': 'result', 'index', 'total', 'success', 'username', 'password',
                           'email', 'user_id', 'attempts', 'refunded', 'message'}
        {'type': 'done',   'total', 'success_count', 'failed_count', 'ocr_count',
                           'refund_count', 'refund_failed_count', 'elapsed'}
    """
    started = time.monotonic()
    success_count = ocr_count = refund_count = refund_failed = 0
    refunded = False

    def refund(pic_id):
        """报错返分并累计计数，返回给日志用的一句话

        官方要求「识别错了就必须报错返分」，故失败要如实报出来（题分是真金白银），
        不能静默吞掉；成功/失败次数都会进 done 帧的汇总。
        """
        nonlocal refunded, refund_count, refund_failed
        ok, reason = _report_ocr_error(pic_id)
        refunded = refunded or ok
        refund_count += int(ok)
        refund_failed += int(not ok)
        return f'报错返分{"成功" if ok else f"失败（{reason}）"}'

    yield {'type': 'start', 'total': count}

    for index in range(1, count + 1):
        # 凭据只生成一次：打码失败时源站并没有建号，重试沿用同一套凭据即可
        creds = generate_credentials()
        username, password, email = creds['username'], creds['password'], creds['email']
        info, message, attempts = {}, '', 0
        refunded = success = False

        for attempt in range(1, max_retry + 1):
            attempts = attempt
            yield {'type': 'log', 'index': index, 'total': count,
                   'text': f'第 {attempt} 次：获取注册验证码'}

            got, captcha = _fetch_one_captcha(provider=provider)
            if not got:
                message = str(captcha)      # 取码失败（网络 / 源站把图片 302 到备用域名后 404）
                continue
            token, raw = captcha

            yield {'type': 'log', 'index': index, 'total': count,
                   'text': f'超级鹰识别中（{codetype}）'}
            ocr = chaojiying_utils.recognize(raw.get('captcha_image') or b'', codetype)
            ocr_data = ocr.get('data') or {}
            if ocr.get('code') != 0:
                message = f"打码失败: {ocr.get('message')}"
                continue                    # 打码平台侧失败：没拿到识别结果，同样换一张重来
            ocr_count += 1

            code = (ocr_data.get('pic_str') or '').strip()
            if not code:
                # 识别成功但没回结果：等同于打码失败，同样报错返分再换一张
                tip = refund(ocr_data.get('pic_id'))
                message = f'打码结果为空（{tip}）'
                continue

            yield {'type': 'log', 'index': index, 'total': count,
                   'text': f'识别结果 {code}，提交注册'}
            ok, res = submit_register(token, code, username, password, email)
            if ok:
                success, info, message = True, res, '注册成功'
                break

            message = str(res)
            if not _is_captcha_error(message):
                break                       # 非验证码问题：不返分，也不重试
            tip = refund(ocr_data.get('pic_id'))
            yield {'type': 'log', 'index': index, 'total': count,
                   'text': f'源站回「{message}」→ {tip}，换一张验证码重试'}

        success_count += int(success)
        yield {'type': 'result', 'index': index, 'total': count, 'success': success,
               'username': username, 'password': password if success else '',
               'email': email, 'user_id': info.get('user_id') if success else None,
               'attempts': attempts, 'refunded': refunded, 'message': message}

    yield {'type': 'done', 'total': count, 'success_count': success_count,
           'failed_count': count - success_count, 'ocr_count': ocr_count,
           'refund_count': refund_count, 'refund_failed_count': refund_failed,
           'elapsed': round(time.monotonic() - started, 1)}


# ==================== 登录 ====================

def login(username=None, password=None, account_id=None):
    """
    登录（源站 POST /api/login/signin）。

    两种用法：
      - 直传 username + password，登录任意账号；
      - 传 account_id，从账号表取该账号的用户名/密码登录。

    登录成功后按源站 user_id 同步库内账号（命中才同步，不新增）：刷新 token，
    并用源站返回的用户名 / 邮箱 / 昵称覆盖本地资料。

    :return: (True, {account_id, user_id, username, nickname, email, token}) 或 (False, msg)
    """
    account = None
    if account_id:
        try:
            account = HaijiaoAccount.objects.get(id=account_id)
        except HaijiaoAccount.DoesNotExist:
            return False, f'账号不存在: account_id={account_id}'
        except Exception as e:      # noqa: BLE001 - 统一转 (False, msg)
            return False, f'查询账号失败: {e}'
        username, password = account.username, account.password
    if not username or not password:
        return False, '参数缺失: 请提供 username + password，或 account_id(库内账号ID)'

    ok, result = _run("登录", lambda s: s.login(username, password))
    if not ok:
        return False, result

    user = (result or {}).get('user') or {}
    token = (result or {}).get('token') or ''
    account = _sync_logged_in_account(user, token) or account
    return True, {
        'account_id': str(account.id) if account else None,
        'user_id': user.get('id'),
        'username': user.get('username') or username,
        'nickname': user.get('nickname') or '',
        'email': user.get('email') or '',
        'token': token,
    }


def _sync_logged_in_account(user, token):
    """登录成功后同步库内账号（按源站 user_id 匹配；库里没有则不新增）

    资料以源站返回为准，token 每次登录都会变，一并回写；同步失败只记日志、不影响登录结果。

    :return: 命中的账号对象；未命中返回 None
    """
    user_id = (user or {}).get('id')
    if not user_id:
        return None
    try:
        account = HaijiaoAccount.objects.filter(user_id=str(user_id)).first()
        if account is None:
            return None
        account.username = user.get('username') or account.username
        account.email = user.get('email') or ''
        account.nickname = user.get('nickname') or ''
        account.token = token
        account.save()
        return account
    except Exception:       # noqa: BLE001 - 同步失败不影响登录结果
        logger.exception('海角社区登录后同步账号失败: user_id=%s', user_id)
        return None


# ==================== 金币签到 ====================

def _mark_signed_today(account):
    """把账号的「最近签到日期」记为今天（本地状态，用于下次签到直接跳过源站请求）

    只更新该字段，不改写密码 / token 密文；落库失败只记日志，不影响已完成的签到结果。
    """
    try:
        account.last_sign_in_date = localdate()
        account.save(update_fields=['last_sign_in_date', 'updated_time'])
    except Exception:       # noqa: BLE001 - 记录状态失败不影响签到结果
        logger.exception('海角社区记录签到日期失败: account_id=%s', account.id)


def sign_in(account_id=None, user_id=None, user_token=None):
    """
    金币签到（源站 POST /api/user/user_sign_in）。

    两种用法：
      - 传 account_id：用账号表里该账号的登录凭据签到，结果里带上账号信息；
      - 直传 user_id + user_token：签到指定账号（不入库、不查库，无本地状态可用）。

    库内账号有双重保险（也是批量提速的关键）：
      ① 先看本地记录的「最近签到日期」，等于今天 → 今天确实已签到，直接返回、不请求源站；
      ② 否则再查源站任务状态，确认可签到（goldSignIn.status）后才真正提交签到；
      签到成功（或源站回「今天已签到」）后把本地日期写成今天，当天后续调用都走 ①。

    :return: (True, {account_id, user_id, username, state, amount, message}) 或 (False, msg)
             state: signed=本次签到成功 / already=今天已签到 / closed=任务未开放
    """
    account = None
    if account_id:
        try:
            account = HaijiaoAccount.objects.get(id=account_id)
        except HaijiaoAccount.DoesNotExist:
            return False, f'账号不存在: account_id={account_id}'
        except Exception as e:      # noqa: BLE001 - 统一转 (False, msg)
            return False, f'查询账号失败: {e}'
        if account.last_sign_in_date == localdate():
            # ① 本地已记录今天签到过：不再请求源站
            return True, {
                'account_id': str(account.id),
                'user_id': account.user_id,
                'username': account.username,
                'state': 'already',
                'amount': 0,
                'message': '今天已签到（本地记录）',
            }
        user_id, user_token = account.user_id, account.token
    if not user_id or not user_token:
        return False, '参数缺失: 请提供 user_id + user_token，或 account_id(库内账号ID)'

    # ② 查源站任务状态 + 提交签到（见 HaijiaoSpider.sign_in）
    ok, result = _run("金币签到", lambda s: s.sign_in(), user_id=user_id, user_token=user_token)
    if not ok:
        return False, result
    if account and result['state'] in ('signed', 'already'):
        _mark_signed_today(account)
    return True, {
        'account_id': str(account.id) if account else None,
        'user_id': user_id,
        'username': account.username if account else '',
        'state': result['state'],
        'amount': result['amount'],
        'message': result['message'],
    }


def sign_in_all():
    """
    批量金币签到（对账号表里全部有 token 的账号逐个签到）。

    逐个串行执行，避免触发源站风控；每条都走 sign_in 的双重保险——今天已签到的账号
    命中本地记录后**不发任何源站请求**（批量提速的关键），首次签到 / 未签到的才查询源站。
    已签到 / 任务未开放按状态计入 already_count，失败项回填原因。

    :return: (True, {total, success_count, already_count, failed_count, items})
    """
    accounts = list(HaijiaoAccount.objects.exclude(token=''))
    results = []
    for account in accounts:
        ok, res = sign_in(account_id=account.id)
        item = {
            'account_id': str(account.id),
            'user_id': account.user_id,
            'username': account.username,
        }
        if ok:
            item.update({'state': res['state'], 'amount': res['amount'], 'msg': res['message']})
        else:
            item.update({'state': 'failed', 'amount': 0, 'msg': res})
        results.append(item)

    success_count = sum(1 for r in results if r['state'] == 'signed')
    already_count = sum(1 for r in results if r['state'] == 'already')
    return True, {
        'total': len(results),
        'success_count': success_count,
        'already_count': already_count,
        'failed_count': len(results) - success_count - already_count,
        'items': results,
    }


# ==================== 发帖 ====================

def _resolve_credentials(account_id=None, user_id=None, user_token=None):
    """解析发帖 / 上传用的登录凭据（源站写操作必须带登录态）

    两种用法：account_id（取账号表里该账号的 user_id + token），或直传 user_id + user_token。

    :return: (user_id, user_token, account, 错误信息)；正常时错误信息为 None
    """
    if account_id:
        try:
            account = HaijiaoAccount.objects.get(id=account_id)
        except HaijiaoAccount.DoesNotExist:
            return None, None, None, f'账号不存在: account_id={account_id}'
        except Exception as e:      # noqa: BLE001 - 统一转 (False, msg)
            return None, None, None, f'查询账号失败: {e}'
        return account.user_id, account.token, account, None
    if user_id and user_token:
        return user_id, user_token, None, None
    return None, None, None, '参数缺失: 请提供 account_id(库内账号ID)，或 user_id + user_token'


def get_topic_nodes():
    """板块列表（含层级 children，供发帖选择板块）"""
    return _run("获取板块列表", lambda s: s.get_nodes())


def get_topic_tags(page=1):
    """标签池（分页，每页 20 条）"""
    return _run("获取标签列表", lambda s: s.get_tags(page=page))


def upload_topic_media(filename, data, content_type=None,
                       account_id=None, user_id=None, user_token=None):
    """上传发帖用的图片 / 视频，返回附件信息与可直接嵌入正文的 HTML 片段"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("上传媒体", lambda s: s.upload_media(filename, data, content_type),
                user_id=uid, user_token=token)


def create_topic(node_id, title, content, tags, topic_type=0, money_type=0, amount=0,
                 reward_hours=0, account_id=None, user_id=None, user_token=None):
    """发帖（正文可含上传得到的图片 / 视频片段）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("发帖",
                lambda s: s.create_topic(node_id, title, content, tags,
                                         topic_type=topic_type, money_type=money_type,
                                         amount=amount, reward_hours=reward_hours),
                user_id=uid, user_token=token)


def get_my_topics(status, page=1, account_id=None, user_id=None, user_token=None):
    """我的帖子（按审核状态筛选；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取我的帖子",
                lambda s: s.get_my_topics(status=status, page=page),
                user_id=uid, user_token=token)


# ==================== 礼物 / 打赏 ====================

def get_gift_list(kind='gold', page=1):
    """礼物列表（打赏时用来挑礼物，分页）"""
    return _run("获取礼物列表", lambda s: s.get_gift_list(kind=kind, page=page))


def give_topic_gift(topic_id, item_id=None, quantity=1, kind='gold',
                    account_id=None, user_id=None, user_token=None):
    """给帖子打赏（给帖子作者送礼物；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("给帖子打赏",
                lambda s: s.give_topic_gift(topic_id, item_id=item_id,
                                            quantity=quantity, kind=kind),
                user_id=uid, user_token=token)


# ==================== 关注 / 取消关注 ====================

def set_follow(target_user_id, follow=True, account_id=None, user_id=None, user_token=None):
    """关注 / 取消关注某个用户（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("关注用户" if follow else "取消关注",
                lambda s: s.set_follow(target_user_id, follow=follow),
                user_id=uid, user_token=token)


# 源站对「已经是目标状态」的回执文案：关注已关注的人 / 取关本来就没关注的人。
# 批量时按「无需操作（already）」处理，不当成失败。
FOLLOW_ALREADY_HINTS = ('已关注此用户', '并未关注')


def set_follow_batch(target_user_id, follow=True):
    """
    批量关注 / 取消关注：让账号库里**全部有 token 的账号**都对同一个目标用户执行关注 / 取关。

    稳定性处理：
    - 逐个**串行**执行（不并发），避免瞬时多请求被源站判定为异常批量行为；
    - 每个账号单独 try，**单个账号失败不影响其它账号**；
    - 关注是写操作且源站对重复关注会直接拒绝，故蜘蛛层已关闭业务与网络重试，不会重复关注；
    - 没有 token 的账号（无法登录）、目标用户恰好是该账号自己的（源站不允许关注自己）
      都**直接跳过**并注明原因，不浪费请求；
    - 账号已是目标状态（已关注 / 本来就没关注）计入 already，不算失败。

    :return: (True, {target_user_id, action, total, success_count, already_count,
                     skipped_count, failed_count, items})
    """
    accounts = list(HaijiaoAccount.objects.all().order_by('create_time'))
    results = []
    for account in accounts:
        item = {
            'account_id': str(account.id),
            'user_id': account.user_id,
            'username': account.username,
            'state': 'done',
            'message': '',
        }
        if not account.token:
            item.update(state='skipped', message='账号没有 token，无法登录')
        elif str(account.user_id) == str(target_user_id):
            item.update(state='skipped', message='目标用户就是该账号自己')
        else:
            ok, res = _run("关注用户" if follow else "取消关注",
                           lambda s: s.set_follow(target_user_id, follow=follow),
                           user_id=account.user_id, user_token=account.token)
            if ok:
                item['state'] = 'done'
            elif any(hint in res for hint in FOLLOW_ALREADY_HINTS):
                item.update(state='already', message='无需操作（已是目标状态）')
            else:
                item.update(state='failed', message=res)
        results.append(item)

    counts = {state: sum(1 for r in results if r['state'] == state)
              for state in ('done', 'already', 'skipped', 'failed')}
    return True, {
        'target_user_id': target_user_id,
        'action': 'follow' if follow else 'unfollow',
        'total': len(results),
        'success_count': counts['done'],
        'already_count': counts['already'],
        'skipped_count': counts['skipped'],
        'failed_count': counts['failed'],
        'items': results,
    }


# ==================== 排行榜 ====================

def get_ranking(key='fans', type_value='all'):
    """排行榜（首页榜单的粉丝 / 点赞 / 人气三个维度）"""
    return _run("获取排行榜", lambda s: s.get_ranking(key=key, type_value=type_value))


# ==================== 用户信息 / 钱包 / 社交 ====================

def get_user_info(target_user_id, account_id=None, user_id=None, user_token=None):
    """用户主页信息（凭据**可选**：带上才能正确返回「我是否已关注 TA」）"""
    if account_id:
        uid, token, _, err = _resolve_credentials(account_id)
        if err:
            return False, err
    else:
        uid, token = user_id, user_token
    return _run("获取用户主页信息", lambda s: s.get_user_info(target_user_id),
                user_id=uid, user_token=token)


def get_wealth(account_id=None, user_id=None, user_token=None):
    """当前账号余额（金币 / 钻石；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取余额", lambda s: s.get_wealth(), user_id=uid, user_token=token)


def get_wealth_log(kind='gold', page=1, account_id=None, user_id=None, user_token=None):
    """金币 / 钻石流水（分页；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取钱包流水", lambda s: s.get_wealth_log(kind=kind, page=page),
                user_id=uid, user_token=token)


def get_following(account_id=None, user_id=None, user_token=None):
    """我关注的人（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取关注列表", lambda s: s.get_following(), user_id=uid, user_token=token)


def get_fans(page=1, account_id=None, user_id=None, user_token=None):
    """我的粉丝（分页；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取粉丝列表", lambda s: s.get_fans(page=page), user_id=uid, user_token=token)


def get_like_state(topic_id, account_id=None, user_id=None, user_token=None):
    """查询当前账号是否已给该帖子点赞（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("查询点赞状态", lambda s: s.get_like_state(topic_id),
                user_id=uid, user_token=token)


def set_topic_like(topic_id, like=True, account_id=None, user_id=None, user_token=None):
    """给帖子点赞 / 取消点赞（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("点赞" if like else "取消点赞",
                lambda s: s.set_topic_like(topic_id, like=like),
                user_id=uid, user_token=token)


def get_liked_topics(page=1, account_id=None, user_id=None, user_token=None):
    """我点赞过的帖子（分页；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取点赞过的帖子", lambda s: s.get_liked_topics(page=page),
                user_id=uid, user_token=token)


# ==================== 收藏 ====================

# folder_id 取该值时表示「全部收藏」（跨收藏夹）；HTTP 层不传 folder_id 即用此默认值。
# 收藏夹名长度上限同样是源站规则，二者都直接取自爬虫层，避免两处各写一份。
FAVORITE_ALL_FOLDERS = spider_utils.FAVORITE_ALL_FOLDERS
FAVORITE_FOLDER_NAME_MAX = spider_utils.FAVORITE_FOLDER_NAME_MAX
FAVORITE_BATCH_MAX = spider_utils.FAVORITE_BATCH_MAX


def get_favorite_folders(account_id=None, user_id=None, user_token=None):
    """我的收藏夹列表（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取收藏夹列表", lambda s: s.get_favorite_folders(),
                user_id=uid, user_token=token)


def get_favorite_topics(page=1, folder_id=FAVORITE_ALL_FOLDERS,
                        account_id=None, user_id=None, user_token=None):
    """我收藏的帖子（分页，可按收藏夹筛选；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("获取收藏的帖子",
                lambda s: s.get_favorite_topics(page=page, folder_id=folder_id),
                user_id=uid, user_token=token)


def add_favorite(topic_id, folder_id=FAVORITE_ALL_FOLDERS,
                 account_id=None, user_id=None, user_token=None):
    """收藏帖子到指定收藏夹（folder_id 默认 0 = 默认收藏夹；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("收藏帖子",
                lambda s: s.add_favorite(topic_id, folder_id=folder_id),
                user_id=uid, user_token=token)


def remove_favorite(topic_id, account_id=None, user_id=None, user_token=None):
    """取消收藏帖子（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("取消收藏", lambda s: s.remove_favorite(topic_id),
                user_id=uid, user_token=token)


# 源站对「取消一个本来就没收藏的帖子」的回执文案（批量时归入 skipped，不当成失败）
FAVORITE_NOT_COLLECTED_HINTS = ('无法删除无效的数据',)


def remove_favorite_batch(topic_ids, account_id=None, user_id=None, user_token=None):
    """
    批量取消收藏：对同一账号**逐条串行**取消给定的帖子。

    为什么不用源站的原生批量（entityIds 逗号多值）：它是「按顺序删、遇到没收藏的就报错中止、
    **已删的不回滚**」，实测会返回「失败但其实已删掉一半」的误导结果，调用方据此重试或放弃
    都会出错。逐条串行后每条的结果都是确定的。

    稳定性处理（与「批量点赞 / 批量关注」同一套口径）：
    - 逐个**串行**执行（不并发），避免瞬时多请求被源站判定为异常批量行为；
    - 每条单独 try，**单条失败不影响其它条目**；
    - 取消收藏是写操作，爬虫层已关闭业务与网络重试，不会重复提交；
    - 本来就没收藏的帖子（源站回「无法删除无效的数据」）计入 skipped，不算失败。

    :param topic_ids: 帖子 ID 列表（调用方需保证已去重、且在 FAVORITE_BATCH_MAX 之内）
    :return: (True, {total, success_count, skipped_count, failed_count, items})
    """
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err

    results = []
    for topic_id in topic_ids:
        ok, res = _run("取消收藏",
                       lambda s, tid=topic_id: s.remove_favorite(tid),
                       user_id=uid, user_token=token)
        item = {'topic_id': topic_id, 'state': 'done', 'message': ''}
        if not ok:
            if any(hint in res for hint in FAVORITE_NOT_COLLECTED_HINTS):
                item.update(state='skipped', message='本来就没收藏')
            else:
                item.update(state='failed', message=res)
        results.append(item)

    counts = {state: sum(1 for r in results if r['state'] == state)
              for state in ('done', 'skipped', 'failed')}
    return True, {
        'total': len(results),
        'success_count': counts['done'],
        'skipped_count': counts['skipped'],
        'failed_count': counts['failed'],
        'items': results,
    }


def rename_favorite_folder(folder_id, name, account_id=None, user_id=None, user_token=None):
    """重命名收藏夹（源站复用「新建」接口；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("重命名收藏夹", lambda s: s.rename_favorite_folder(folder_id, name),
                user_id=uid, user_token=token)


def create_favorite_folder(name, account_id=None, user_id=None, user_token=None):
    """新建收藏夹（需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("新建收藏夹", lambda s: s.create_favorite_folder(name),
                user_id=uid, user_token=token)


def delete_favorite_folder(folder_id, account_id=None, user_id=None, user_token=None):
    """删除收藏夹（源站要求夹内为空；需登录态）"""
    uid, token, _, err = _resolve_credentials(account_id, user_id, user_token)
    if err:
        return False, err
    return _run("删除收藏夹", lambda s: s.delete_favorite_folder(folder_id),
                user_id=uid, user_token=token)


# 源站对「已经是目标状态」的回执文案：已点赞的人再点赞 / 没点赞的人取关。
# 批量时按「无需操作（already）」处理，不当成失败。
LIKE_ALREADY_HINTS = {'like': '已点赞', 'unlike': '未点赞'}


def set_like_batch(topic_id, like=True):
    """
    批量点赞 / 取消点赞：让账号库里**全部账号**都对同一篇帖子执行点赞（或取消）。

    稳定性处理（与「批量关注」同一套口径）：
    - 逐个**串行**执行（不并发），避免瞬时多请求被源站判定为异常批量行为；
    - 每个账号单独 try，**单个账号失败不影响其它账号**；
    - 点赞是写操作，蜘蛛层已关闭业务与网络重试，不会重复提交；
    - 没有 token 的账号（无法登录）**直接跳过**并注明原因；
    - 账号已是目标状态（已点过赞 / 本来就没点赞）计入 already，不算失败。

    :return: (True, {topic_id, action, total, success_count, already_count,
                     skipped_count, failed_count, items})
    """
    accounts = list(HaijiaoAccount.objects.all().order_by('create_time'))
    results = []
    for account in accounts:
        item = {
            'account_id': str(account.id),
            'user_id': account.user_id,
            'username': account.username,
            'state': 'done',
            'message': '',
        }
        if not account.token:
            item.update(state='skipped', message='账号没有 token，无法登录')
        else:
            ok, res = _run("点赞" if like else "取消点赞",
                           lambda s: s.set_topic_like(topic_id, like=like),
                           user_id=account.user_id, user_token=account.token)
            if ok:
                item['state'] = 'done'
            elif LIKE_ALREADY_HINTS['like' if like else 'unlike'] in res:
                item.update(state='already', message='无需操作（已是目标状态）')
            else:
                item.update(state='failed', message=res)
        results.append(item)

    counts = {state: sum(1 for r in results if r['state'] == state)
              for state in ('done', 'already', 'skipped', 'failed')}
    return True, {
        'topic_id': topic_id,
        'action': 'like' if like else 'unlike',
        'total': len(results),
        'success_count': counts['done'],
        'already_count': counts['already'],
        'skipped_count': counts['skipped'],
        'failed_count': counts['failed'],
        'items': results,
    }


# ==================== 账号表增删改查 ====================

def _account_dict(account, with_token=False, with_password=False) -> dict:
    """账号对外字段（默认不回传密码明文；token 仅在详情/创建/更新时返回，密码按需返回）"""
    data = {
        'account_id': str(account.id),
        'user_id': account.user_id,
        'username': account.username,
        'email': account.email,
        'nickname': account.nickname,
        'remark': account.remark,
        'has_password': bool(account.password),
        'has_token': bool(account.token),
        'create_time': account.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        'updated_time': account.updated_time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if with_token:
        data['token'] = account.token
    if with_password:
        data['password'] = account.password
    return data


def list_accounts(keyword='', page=1, page_size=10, with_password=False):
    """账号列表（分页；keyword 匹配用户名 / 邮箱 / 昵称 / 源站用户ID）

    with_password=True 时列表项会携带密码明文（默认不返回）。
    """
    try:
        queryset = HaijiaoAccount.objects.all()
        if keyword:
            queryset = queryset.filter(
                Q(username__icontains=keyword) | Q(email__icontains=keyword)
                | Q(nickname__icontains=keyword) | Q(user_id__icontains=keyword))
        total = queryset.count()
        start = (page - 1) * page_size
        rows = [_account_dict(a, with_password=with_password)
                for a in queryset[start:start + page_size]]
    except Exception as e:          # noqa: BLE001 - 统一转 (False, msg)
        return False, f'查询账号失败: {e}'
    return True, {'total': total, 'page': page, 'page_size': page_size, 'items': rows}


def get_account(account_id, with_password=False):
    """账号详情（含 token；with_password=True 时额外返回密码明文）"""
    try:
        account = HaijiaoAccount.objects.get(id=account_id)
    except HaijiaoAccount.DoesNotExist:
        return False, f'账号不存在: account_id={account_id}'
    except Exception as e:          # noqa: BLE001
        return False, f'查询账号失败: {e}'
    return True, _account_dict(account, with_token=True, with_password=with_password)


def create_account(data):
    """新增账号（user_id / username / password 必填）"""
    user_id = (data.get('user_id') or '').strip()
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    for name, value in (('user_id(源站用户ID)', user_id), ('username(用户名)', username),
                        ('password(密码)', password)):
        if not value:
            return False, f'参数缺失: {name}'
    try:
        if HaijiaoAccount.objects.filter(user_id=user_id).exists():
            return False, f'资源已存在: 该源站用户ID已入库（user_id={user_id}）'
        account = HaijiaoAccount.objects.create(
            user_id=user_id, username=username, password=password,
            email=(data.get('email') or '').strip(),
            nickname=(data.get('nickname') or '').strip(),
            token=(data.get('token') or '').strip(),
            remark=(data.get('remark') or '').strip())
    except Exception as e:          # noqa: BLE001
        return False, f'创建账号失败: {e}'
    return True, _account_dict(account, with_token=True)


def update_account(account_id, data):
    """更新账号（部分字段；user_id 为源站身份标识，不可修改）"""
    try:
        account = HaijiaoAccount.objects.get(id=account_id)
    except HaijiaoAccount.DoesNotExist:
        return False, f'账号不存在: account_id={account_id}'
    except Exception as e:          # noqa: BLE001
        return False, f'查询账号失败: {e}'

    for field in ('username', 'password'):
        if field in data and not (data.get(field) or '').strip():
            return False, f'参数值非法: {field} 不能为空'
    for field in ('username', 'password', 'email', 'nickname', 'token', 'remark'):
        if field in data:
            setattr(account, field, (data.get(field) or '').strip())
    try:
        account.save()
    except Exception as e:          # noqa: BLE001
        return False, f'更新账号失败: {e}'
    return True, _account_dict(account, with_token=True)


def delete_account(account_id):
    """删除账号"""
    try:
        deleted, _ = HaijiaoAccount.objects.filter(id=account_id).delete()
    except Exception as e:          # noqa: BLE001
        return False, f'删除账号失败: {e}'
    if not deleted:
        return False, f'账号不存在: account_id={account_id}'
    return True, None
