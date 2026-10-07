"""消息推送 push · QQBot 事件上报入口（免签名）

路径：`/hook/qqbot/<密钥>/`（注册在站点根路由，见 `XiaoYingAPI/urls.py`）

为什么不在 `/api/` 下：`ApiAuthMiddleware` 只对 `/api/` 的**项目签名**请求放行，而 NapCat 的
HTTP 客户端上报事件时带不了我们的项目签名 —— 所以它必须挂在 `/api/` 之外。来源可信度靠
**回调地址里的随机密钥**（`PushSetting.hook_secret`，只写进 NapCat 配置、不对外暴露）自证。

处理两类事件：

- **好友私聊消息**（`post_type=message` 且 `message_type=private`）：落进 `QQPrivateMessage`，
  控制台「QQBot」页的「好友消息」面板再靠 SSE 按 id 增量拉取本表 —— 这就是「实时收到好友消息」的来源。
  （OneBot 没有「拉取新消息」的接口，只能由 NapCat 主动推。）
- **好友添加成功**（`notice.friend_add`）：交给搬单的「打手 QQ 自动接待」主动索要丸子订单号。

无论落库成功与否都回 200（上游拿不到成功回执会不停重推），失败只记 error 日志。
"""
import hmac
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from API.models import PushSetting

from . import ai_reply, utils

logger = logging.getLogger('api.push')


def _ok():
    """OneBot HTTP 上报约定的成功回执"""
    return JsonResponse({'status': 'ok', 'retcode': 0, 'data': None})


def _maybe_friend_add(event):
    """好友添加成功（OneBot `notice.friend_add`）→ 让 AI 主动索要丸子订单号

    「自动同意好友」由 QQ / NapCat 侧负责，这里只负责接手对话：
    起一个后台线程发开场白，回调照旧立刻回 200（NapCat 拿不到快速回执会反复重推）。
    """
    user_id = str(event.get('user_id') or '').strip()
    if not user_id:
        return
    from API.apis.order_migration import qq_flow       # 惰性导入：push 与搬单互不依赖加载顺序

    sender = event.get('sender') if isinstance(event.get('sender'), dict) else {}
    logger.info('QQBot 好友添加成功：QQ %s', user_id)
    qq_flow.spawn_greet(user_id, str(sender.get('nickname') or ''))


def _maybe_auto_reply(event):
    """落库成功后决定谁来接话：打手（含报单号）走搬单业务链路，其余走控制台的闲聊 AI

    两边都不命中就直接返回（零开销、对现有功能零影响）。真要做也**不等结果**：
    这里只是起一个后台线程，回调照旧立刻回 200 —— NapCat 拿不到快速回执会反复重推。
    """
    # 纯表情 / 图片 / 语音等非文本消息没有话头，不触发（消息本身照常落库、照常显示）
    if not utils.has_readable_text(event.get('message')):
        return
    sender = event.get('sender') if isinstance(event.get('sender'), dict) else {}
    user_id = str(event.get('user_id') or '')
    nickname = str(sender.get('nickname') or '')
    content = utils.flatten_message(event.get('message'))
    try:
        from API.apis.order_migration import qq_flow

        # 打手（我们开场白打过招呼的 QQ）或报单号的消息：交给搬单业务链路
        if qq_flow.should_handle(user_id, content):
            qq_flow.spawn_handle(user_id, nickname, content)
            return
        if not PushSetting.get_solo().ai_reply_enabled:
            return
    except Exception:                          # noqa: BLE001 开关读不到就当没开，绝不影响回执
        logger.exception('QQBot 读取自动回复开关失败')
        return
    ai_reply.spawn(user_id, nickname)


@csrf_exempt
@require_POST
def hook_view(request, secret):
    """接收 NapCat 事件上报：好友私聊消息落库"""
    setting = PushSetting.get_solo()
    if not setting.hook_secret or not hmac.compare_digest(str(secret), str(setting.hook_secret)):
        # 密钥不对：既不落库也不回显差异（返回与正常一致，避免被用来探测）
        logger.warning('QQBot 事件上报密钥不匹配，已忽略')
        return _ok()

    raw = request.body
    if not raw:
        # 空请求体：多半是服务器没解析 chunked（Django 自带 runserver 的坑，见 API/common/devserver.py）。
        # 这条警告就是为了让这种「上游说推了、我们回 200 但什么都没落库」的情况一眼可见。
        logger.warning('QQBot 事件上报体为空（Transfer-Encoding=%s）—— 若为 chunked，'
                       '请确认开发服务器补丁已生效（API/common/devserver.py）',
                       request.META.get('HTTP_TRANSFER_ENCODING') or '-')
        return _ok()
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning('QQBot 事件上报体不是合法 JSON，已忽略')
        return _ok()
    if not isinstance(event, dict):
        return _ok()

    # 好友添加成功：交给「打手 QQ 自动接待」主动索要丸子订单号（非消息事件，不落消息表）
    if (str(event.get('post_type') or '') == 'notice'
            and str(event.get('notice_type') or '') == 'friend_add'):
        _maybe_friend_add(event)
        return _ok()

    try:
        stored = utils.record_private_message(event)
    except Exception:                          # noqa: BLE001 落库失败也要回执，避免上游重推
        logger.exception('QQBot 好友消息落库失败')
        return _ok()
    if stored:
        logger.info('QQBot 好友消息已落库：QQ %s', event.get('user_id'))
        _maybe_auto_reply(event)
    return _ok()
