"""消息推送 push 业务层 —— Server酱（ServerChan）线路

上游接口（官方文档 https://sct.ftqq.com/；登录后「Key&API」页有完整参数说明）：
    POST https://sctapi.ftqq.com/<SendKey>.send
    参数：title（必填，≤32 字符、不含换行）、desp（正文，可选，支持 Markdown）
          以及可选 channel / short / tags / openid / noip / encoded
    成功返回：{"code": 0, "message": "", "data": {"pushid": ..., "readkey": ...}}
    SendKey 以 sctp 开头时改用 https://<uid>.push.ft07.com/send/<SendKey>.send
    查询送达状态：GET https://sctapi.ftqq.com/push?id={pushid}&readkey={readkey}

SendKey 由服务端托管：取自控制台「账号管理」(/console/accounts/) 里 platform=serverchan 的账号
（凭据字段即 SendKey，落库 AES 加密）。调用方无需、也不应传 SendKey；SendKey 全程不写日志。

每次推送尝试都会落一条 `PushLog`（成功 / 失败均记），供控制台「推送日志」页查看；
端对端加密的推送记录的是**实际发出的密文**，不是明文正文。
"""
import base64
import hashlib
import logging
import re

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from API.common import platform_accounts

logger = logging.getLogger('api.push')

# 平台账号标识：Server酱 SendKey 在控制台「账号管理」维护（platform=serverchan）
PLATFORM = 'serverchan'
# 推送渠道标识（PushLog.channel）
CHANNEL = 'serverchan'

# 上游送达状态查询地址（pushid 用 id 参数传递）
STATUS_URL = 'https://sctapi.ftqq.com/push'

# 上游接口超时（秒）
TIMEOUT = 15
# 官方限制：title 最长 32 个字符
TITLE_MAX_LEN = 32

_SCTP_PATTERN = re.compile(r'^sctp(\d+)t')
_SCT_PATTERN = re.compile(r'^SCT(\d+)')


def sendkey():
    """取服务端托管的 Server酱 SendKey；未配置返回空串（不落日志、不回显）"""
    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        return ''
    return platform_accounts.credential_of(account)


def _endpoint(key):
    """按 SendKey 前缀拼出上游发送地址

    SCT 开头 → https://sctapi.ftqq.com/<key>.send
    sctp 开头 → https://<uid>.push.ft07.com/send/<key>.send（uid 为 sctp 与 t 之间的数字）
    """
    match = _SCTP_PATTERN.match(key)
    if match:
        return f'https://{match.group(1)}.push.ft07.com/send/{key}.send'
    return f'https://sctapi.ftqq.com/{key}.send'


def uid_of(key):
    """从 SendKey 取 UID：SCT433147… → 433147；sctp433147t… → 433147；取不到返回空串"""
    for pattern in (_SCT_PATTERN, _SCTP_PATTERN):
        match = pattern.match(key)
        if match:
            return match.group(1)
    return ''


def encrypt_desp(content, password, key):
    """按 Server酱 端对端加密算法加密正文（官方 PHP 示例 sc_encode 的等价实现）

    算法：key = md5(密码)[:16]、iv = md5('SCT' + UID)[:16]（均取 hex 前 16 位当字节用），
    正文先 base64，再 AES-128-CBC / PKCS7，最后整体 base64 输出。
    收件人在 Server酱 消息详情页输入同一密码即可在浏览器端解密查看。

    :return: 密文字符串；SendKey 取不到 UID 时返回空串
    """
    uid = uid_of(key)
    if not uid:
        return ''

    def digest(text):
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:16].encode('ascii')

    cipher = AES.new(digest(password), AES.MODE_CBC, digest('SCT' + uid))
    raw = base64.b64encode(content.encode('utf-8'))
    return base64.b64encode(cipher.encrypt(pad(raw, AES.block_size))).decode('ascii')


def _log(title, content, ok, code=None, message='', pushid='', app_id=''):
    """落一条推送日志（日志写入失败不影响推送结果，只记异常）"""
    from API.models import PushLog

    try:
        PushLog.objects.create(
            channel=CHANNEL, app_id=app_id or '', title=title[:255], content=content or '',
            ok=ok, code=code, message=(message or '')[:500], pushid=(pushid or '')[:64])
    except Exception:                       # noqa: BLE001 推送已发生，日志失败不应改变对外结果
        logger.exception('推送日志写入失败')


def send(title, desp='', channel='', short='', tags='', openid='', noip=False,
         encrypt_password='', app_id=''):
    """发送一条消息到 Server酱，并记录推送日志

    :param title: 消息标题（必填，≤32 字符、不含换行；视图层已校验）
    :param desp:  消息正文（可选，支持 Markdown）
    :param channel / short / tags / openid: 上游可选参数（留空则不传）
    :param noip:  是否隐藏调用方 IP（True 时上游记录里不记来源 IP）
    :param encrypt_password: 阅读密码；填了即对 desp 做端对端加密并传 encoded=1
    :param app_id: 发起调用的接入项目 APPID（仅用于日志，可空）
    :return: (True, {'pushid', 'readkey', 'encrypted'}) 或 (False, {'code', 'message'})
    """
    key = sendkey()
    if not key:
        message = ('未配置 Server酱 SendKey：请到控制台「账号管理」新增一个 platform=serverchan 的账号，'
                   '凭据填入 SendKey')
        _log(title, desp, ok=False, message=message, app_id=app_id)
        return False, {'code': None, 'message': message}

    encoded = bool(encrypt_password)
    sent = desp or ''
    if encoded:
        sent = encrypt_desp(sent, encrypt_password, key)
        if not sent:
            message = '当前 SendKey 无法识别 UID，暂不支持端对端加密'
            _log(title, desp, ok=False, message=message, app_id=app_id)
            return False, {'code': None, 'message': message}

    payload = {'title': title, 'desp': sent}
    if encoded:
        payload['encoded'] = 1
    if noip:
        payload['noip'] = 1
    for name, value in (('channel', channel), ('short', short), ('tags', tags), ('openid', openid)):
        if value:
            payload[name] = value

    try:
        resp = requests.post(_endpoint(key), data=payload, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        message = f'推送请求失败: {e}'
        _log(title, sent, ok=False, message=message, app_id=app_id)
        return False, {'code': None, 'message': message}

    try:
        result = resp.json()
    except ValueError:
        message = '推送响应不是合法 JSON'
        _log(title, sent, ok=False, message=message, app_id=app_id)
        return False, {'code': None, 'message': message}

    code = result.get('code')
    inner = result.get('data') or {}
    if code == 0:
        pushid = str(inner.get('pushid') or '')
        readkey = str(inner.get('readkey') or '')
        _log(title, sent, ok=True, code=0, message=result.get('message') or '成功',
             pushid=pushid, app_id=app_id)
        return True, {'pushid': pushid, 'readkey': readkey, 'encrypted': encoded}

    message = (str(result.get('message') or '').strip()
               or str(inner.get('error') or '').strip()
               or '推送失败')
    _log(title, sent, ok=False, code=code, message=message, app_id=app_id)
    return False, {'code': code, 'message': message}


def query_status(pushid, readkey):
    """查询一条推送的送达状态

    Server酱 的发送是异步入队：发送接口返回成功只代表「已入队」，实际是否送达要看
    返回里的 wxstatus（微信接口的原始返回；为空表示任务可能尚未执行）。

    :return: (True, 上游 data 字典) 或 (False, {'code', 'message'})
    """
    try:
        resp = requests.get(STATUS_URL, params={'id': pushid, 'readkey': readkey}, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        return False, {'code': None, 'message': f'状态查询请求失败: {e}'}

    try:
        result = resp.json()
    except ValueError:
        return False, {'code': None, 'message': '状态查询响应不是合法 JSON'}

    code = result.get('code')
    if code == 0:
        return True, result.get('data') or {}
    message = str(result.get('message') or '').strip() or '状态查询失败'
    return False, {'code': code, 'message': message}
