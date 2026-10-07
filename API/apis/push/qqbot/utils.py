"""消息推送 push · QQBot 线路 业务层（NapCat / OneBot 11 HTTP）

NapCat 按 **OneBot 11** 协议对外提供 HTTP 服务（在 WebUI「网络配置」里启用 HTTP 服务端），
发送走 `POST {base}/send_msg`：请求体 `{message_type, group_id|user_id, message, auto_escape}`，
配置了 token 时请求头带 `Authorization: Bearer <token>`。
响应形如 `{"status": "ok", "retcode": 0, "data": {"message_id": 123}}`，`retcode == 0` 即成功。

配置（HTTP 地址 / token / 超时）在控制台「QQBot」页维护（单例 `PushSetting`），
调用方只传 target_type + target_id + message，不接触地址与 token；token 全程不写日志。
控制台「QQBot」页的「测试连接」用 `get_login_info()` 校验地址与 token；
文档在线调试的「目标号码」下拉用 `list_groups()` 列出机器人已加入的群。

好友私聊消息（后台实时接收）：OneBot 没有「拉取新消息」的接口，只能由 NapCat 主动推 ——
`record_private_message()` 把上报的 `message` 事件写进 `QQPrivateMessage`，
控制台「QQBot」页的「好友消息」面板按主键增量拉取，见 `hook.py`。

每次发送（无论成功失败）都会落一条 `PushLog`（渠道 `qqbot`），供控制台「推送日志」页查看。
"""
import logging
import re
from datetime import datetime, timezone as dt_timezone

import requests
from django.utils.translation import gettext as _

from API.models import PushSetting, QQPrivateMessage

logger = logging.getLogger('api.push')

# 推送渠道标识（PushLog.channel）
CHANNEL = 'qqbot'

# 目标类型（取值同 OneBot 的 message_type）
TARGET_GROUP = 'group'
TARGET_PRIVATE = 'private'
TARGET_TYPES = (TARGET_GROUP, TARGET_PRIVATE)

# OneBot 11 接口
SEND_PATH = '/send_msg'
DELETE_PATH = '/delete_msg'
LOGIN_INFO_PATH = '/get_login_info'
GROUP_LIST_PATH = '/get_group_list'

# 目标类型的展示名（日志用）
_TARGET_LABELS = {TARGET_GROUP: '群', TARGET_PRIVATE: '私聊'}

# 非文本消息段 -> 中文占位符（取值见 NapCat 消息格式文档 develop/msg；未列出的按 [type] 兜底）
_SEGMENT_LABELS = {
    'face': '[表情]', 'image': '[图片]', 'record': '[语音]', 'video': '[视频]',
    'file': '[文件]', 'poke': '[戳一戳]', 'reply': '[回复]', 'forward': '[转发消息]',
    'json': '[卡片消息]', 'markdown': '[Markdown]', 'location': '[位置]',
    'share': '[链接分享]', 'music': '[音乐]', 'contact': '[推荐]',
    'rps': '[猜拳]', 'dice': '[骰子]',
}


def target_label(target_type, target_id):
    """目标的展示名：群 123456 / 私聊 123456"""
    return f'{_TARGET_LABELS.get(target_type, target_type)} {target_id}'


def _config():
    """读取推送设置：(地址, token, 超时秒)"""
    setting = PushSetting.get_solo()
    return ((setting.qqbot_api_base or '').strip().rstrip('/'),
            (setting.qqbot_token or '').strip(),
            max(1, int(setting.qqbot_timeout)))


def _call(path, payload=None, timeout=None):
    """调用 NapCat HTTP 接口

    payload 为 None 时用 GET（查询类接口，如 /get_login_info、/get_group_list），
    否则用 POST（业务接口，如 /send_msg）。
    :return: (True, 响应 JSON) 或 (False, 错误说明)
    """
    base, token, default_timeout = _config()
    if not base:
        return False, '未配置 QQBot HTTP 地址'
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    wait = timeout or default_timeout
    try:
        if payload is None:
            resp = requests.get(f'{base}{path}', headers=headers, timeout=wait)
        else:
            resp = requests.post(f'{base}{path}', json=payload, headers=headers, timeout=wait)
        resp.raise_for_status()
    except requests.RequestException as e:
        return False, f'请求失败: {e}'
    try:
        return True, resp.json()
    except ValueError:
        return False, '响应不是合法 JSON'


def _failed(result):
    """上游返回里取失败原因（message / wording 兜底）"""
    return (str(result.get('message') or '').strip()
            or str(result.get('wording') or '').strip()
            or '上游返回失败')


def get_login_info(timeout=None):
    """取机器人自身信息，用于校验 HTTP 地址与 token 是否可用

    :return: (True, {'user_id', 'nickname'}) 或 (False, 错误说明)
    """
    ok, result = _call(LOGIN_INFO_PATH, timeout=timeout)
    if not ok:
        return False, result
    if result.get('status') == 'ok' and result.get('retcode') == 0:
        inner = result.get('data') or {}
        return True, {'user_id': str(inner.get('user_id') or ''),
                      'nickname': str(inner.get('nickname') or '')}
    return False, _failed(result)


def list_groups(timeout=None):
    """取机器人已加入的群，供文档在线调试的「目标号码」下拉使用

    :return: (True, [{'group_id', 'group_name'}, ...]) 或 (False, 错误说明)
    """
    ok, result = _call(GROUP_LIST_PATH, timeout=timeout)
    if not ok:
        return False, result
    if result.get('status') == 'ok' and result.get('retcode') == 0:
        data = result.get('data')
        return True, list(data) if isinstance(data, list) else []
    return False, _failed(result)


def flatten_message(message):
    """把 OneBot 消息段（数组）拍平成可读文本

    NapCat 按 `messagePostFormat=json` 上报时 message 是数组，例如
    `[{"type":"text","data":{"text":"你好"}}, {"type":"image","data":{…}}]`；
    文本直接取，其它类型给一个占位符（[图片] / [语音] / [表情] …），让聊天里看得出发生了什么。
    上游若直接给字符串，则原样返回。
    """
    if isinstance(message, str):
        return message
    if not isinstance(message, list):
        return str(message or '')
    parts = []
    for seg in message:
        if not isinstance(seg, dict):
            continue
        kind = str(seg.get('type') or '')
        data = seg.get('data') if isinstance(seg.get('data'), dict) else {}
        if kind == 'text':
            parts.append(str(data.get('text') or ''))
        elif kind == 'at':
            parts.append(f"@{data.get('qq') or ''}")
        elif kind:
            parts.append(_SEGMENT_LABELS.get(kind) or f'[{kind}]')
    return ''.join(parts)


def _event_time(raw):
    """事件里的时间戳（unix 秒）-> 带时区的 datetime；缺失 / 非法则为 None"""
    try:
        ts = int(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc) if ts > 0 else None


# 一次回复最多带几张图（与 QQ 单条消息的图片上限一致）
MAX_REPLY_IMAGES = 9

# CQ 码：`[CQ:kind,key=value,...]`
_CQ_RE = re.compile(r'\[CQ:([a-z_]+)((?:,[^\[\]]*)?)\]')


def cq_display(text):
    """把 CQ 码换成可读占位符，**仅供展示**（真正发出去的仍是原始 CQ 码）

    QQ 侧发出 `[CQ:image,file=base64://…]` 这种长串没法直接摆在对话气泡里，
    展示时统一换成 `[图片]` / `[表情]` / `@10001`，与「收到的消息」的展示口径一致。
    """
    def _replace(match):
        kind, params = match.group(1), match.group(2)
        if kind == 'at':
            qq = next((p[3:] for p in params.split(',') if p.startswith('qq=')), '')
            return f'@{qq}' if qq else '@'
        return _SEGMENT_LABELS.get(kind) or f'[{kind}]'

    return _CQ_RE.sub(_replace, text or '')


def has_readable_text(message):
    """消息里有没有「人能读的文字」——纯表情 / 图片 / 语音 / 文件等非文本消息返回 False

    用途：AI 自动回复只对文本消息触发（纯表情、图片、语音这类没有话头，交给 AI 也只能瞎猜）。
    入参口径与 `flatten_message` 保持一致：数组按消息段判断，字符串则先剥掉 CQ 码再看剩下什么。
    """
    if isinstance(message, list):
        for seg in message:
            if not isinstance(seg, dict) or str(seg.get('type') or '') != 'text':
                continue
            data = seg.get('data') if isinstance(seg.get('data'), dict) else {}
            if str(data.get('text') or '').strip():
                return True
        return False
    if isinstance(message, str):
        return bool(_CQ_RE.sub('', message).strip())
    return False


def build_reply(text, images):
    """把「文本 + 图片(dataURL 列表)」组合成 (发给上游的消息, 展示用文本)

    · 发给上游：文本原样 + 每张图一个 `[CQ:image,file=base64://…]`
      （NapCat 支持 `base64://` 作为图片来源，见其 API 文档；也省去落盘与公网可访问）
    · 展示用：CQ 码换成 `[图片]` / `[表情]` 等占位符。

    :raises ValueError: 图片过多 / 不是合法的 dataURL
    """
    if len(images) > MAX_REPLY_IMAGES:
        raise ValueError(_('一次最多发送 %(n)s 张图片') % {'n': MAX_REPLY_IMAGES})

    upstream_parts, display_parts = [], []
    if text:
        upstream_parts.append(text)
        display_parts.append(cq_display(text))
    for data_url in images:
        data_url = str(data_url or '')
        if not data_url.startswith('data:image/') or ',' not in data_url:
            raise ValueError(_('图片格式不正确（只支持浏览器读取的 data:image/…）'))
        upstream_parts.append(f'[CQ:image,file=base64://{data_url.split(",", 1)[1]}]')
        display_parts.append(_SEGMENT_LABELS['image'])
    return ' '.join(upstream_parts), ' '.join(display_parts)


def record_private_message(event):
    """把 NapCat 上报的「好友私聊消息」事件落库（direction=in）

    事件形如 `{"post_type":"message","message_type":"private","sub_type":"friend",
    "user_id":123,"message":[…],"sender":{"nickname":"…"},"time":…}`。
    只收 `message_type=private`（不落群消息），并按上游 `message_id` 幂等。
    :return: True 表示已入库（False = 不是私聊 / 重复 / 缺字段）
    """
    if str(event.get('post_type') or '') != 'message':
        return False
    if str(event.get('message_type') or '') != 'private':
        return False
    user_id = str(event.get('user_id') or '').strip()
    if not user_id:
        return False

    message_id = str(event.get('message_id') or '').strip()
    if message_id and QQPrivateMessage.objects.filter(
            message_id=message_id, direction=QQPrivateMessage.Direction.IN).exists():
        return False                                       # 上游重推同一条

    sender = event.get('sender') if isinstance(event.get('sender'), dict) else {}
    QQPrivateMessage.objects.create(
        message_id=message_id[:64],
        user_id=user_id[:20],
        nickname=str(sender.get('nickname') or '')[:100],
        content=flatten_message(event.get('message')),
        sub_type=str(event.get('sub_type') or '')[:16],
        direction=QQPrivateMessage.Direction.IN,
        received_at=_event_time(event.get('time')),
    )
    return True


def record_outgoing_message(user_id, content, message_id='', is_greeting=False):
    """记录一条「后台回复发出」的消息（direction=out），与收到的消息拼成完整对话

    :param is_greeting: True=代练搬单给刚加好友的打手发的**主动开场白**，
        用于把该 QQ 认作来交接的打手（见 order_migration/qq_flow.py）
    """
    return QQPrivateMessage.objects.create(
        message_id=str(message_id or '')[:64],
        user_id=str(user_id)[:20],
        content=content or '',
        direction=QQPrivateMessage.Direction.OUT,
        is_read=True,
        is_greeting=bool(is_greeting),
    )


def _log(title, content, recipients, ok, code=None, message='', pushid='', app_id=''):
    """落一条推送日志（写库失败不影响发送结果，只记异常）"""
    from API.models import PushLog

    try:
        PushLog.objects.create(
            channel=CHANNEL, app_id=app_id or '', title=(title or '')[:255], content=content or '',
            recipients=(recipients or '')[:1000], ok=ok, code=code,
            message=(message or '')[:500], pushid=(pushid or '')[:64])
    except Exception:                       # noqa: BLE001 发送已发生，日志失败不应改变对外结果
        logger.exception('推送日志写入失败')


def send(message, target_type, target_id, app_id='', auto_escape=None):
    """通过 QQBot（NapCat）发送一条消息，并记录推送日志

    :param message: 消息正文；**纯文本**或**CQ 码**（如 `[CQ:image,file=…]`）都支持
    :param target_type: 'group'（群聊）或 'private'（私聊）
    :param target_id: 群号 / 好友 QQ 号
    :param app_id: 发起调用的接入项目 APPID（仅用于日志，可空）
    :param auto_escape: 是否把消息当纯文本（true=不解析 CQ 码）。
        默认 None 表示**自动判断**：正文里出现 `[CQ:` 就按 CQ 码发（auto_escape=False），
        否则按纯文本发（auto_escape=True）—— 否则 `[CQ:image,…]` 会被当成普通文字发出去。
    :return: (True, {'message_id': ...}) 或 (False, {'code', 'message'})
    """
    title = target_label(target_type, target_id)
    if auto_escape is None:
        auto_escape = '[CQ:' not in (message or '')
    base, _token, _timeout = _config()
    if not base:
        text = '未配置 QQBot HTTP 地址：请到控制台「QQBot」页填写 NapCat HTTP 服务端地址'
        _log(title, message, target_id, ok=False, message=text, app_id=app_id)
        return False, {'code': None, 'message': text}

    payload = {'message_type': target_type, 'message': message, 'auto_escape': auto_escape}
    payload['group_id' if target_type == TARGET_GROUP else 'user_id'] = target_id

    ok, result = _call(SEND_PATH, payload)
    if not ok:
        _log(title, message, target_id, ok=False, message=result, app_id=app_id)
        return False, {'code': None, 'message': result}

    retcode = result.get('retcode')
    if result.get('status') == 'ok' and retcode == 0:
        message_id = (result.get('data') or {}).get('message_id')
        _log(title, message, target_id, ok=True, code=0, message='发送成功',
             pushid=str(message_id or ''), app_id=app_id)
        return True, {'message_id': message_id}

    text = _failed(result)
    _log(title, message, target_id, ok=False, code=retcode, message=text, app_id=app_id)
    return False, {'code': retcode, 'message': text}


def recall_message(message_id, timeout=None):
    """撤回一条消息（OneBot `delete_msg`）

    注意：QQ 对可撤回时限有要求（好友消息通常是发出后 2 分钟内），超期会由上游返回原因，
    这里如实回传，不做兜底猜测。
    :return: (True, '') 或 (False, 错误说明)
    """
    message_id = str(message_id or '').strip()
    if not message_id:
        return False, _('这条消息没有上游消息ID，无法撤回（只能删除本地记录）')
    payload = {'message_id': int(message_id) if message_id.isdigit() else message_id}
    ok, result = _call(DELETE_PATH, payload, timeout=timeout)
    if not ok:
        return False, result
    if result.get('status') == 'ok' and result.get('retcode') == 0:
        return True, ''
    return False, _failed(result)
