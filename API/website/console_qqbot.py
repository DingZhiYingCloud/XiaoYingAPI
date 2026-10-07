"""超管控制台 · QQBot 操作台

`/console/qqbot/`：QQBot（NapCat）相关的运行配置、一键部署与**好友消息**都在这一个页面 ——

    1. 连接配置：HTTP 地址 / token / 超时 / 机器人 QQ 号 / 安装目录；
    2. 事件回调：回调地址（实时接收好友消息用）与基址；
    3. 一键部署：自动下载 / 配置 / 启动 / 回填，配实时日志（SSE）；
    4. 好友消息：好友私聊机器人的消息（NapCat 事件上报落库），按主键增量拉取实时展示。

鉴权：仅 Django is_superuser（见 admin_auth.py），写操作自动进控制台操作日志（ConsoleAuditLog）。
凭据（token）加密落库、页面不回显，编辑时留空 = 保持原值。

好友消息为什么读库：OneBot 没有「拉取新消息」的接口，消息只能由 NapCat 主动推 ——
一键部署会在 NapCat 里写好 HTTP 客户端，把 `message` 事件 POST 到 `/hook/qqbot/<密钥>/`，
由 `API/apis/push/qqbot/hook.py` 落库；本页再按 `id > cursor` 增量拉取。启用之前的历史消息无法补录。
"""
import json
import time
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from API.apis.push.qqbot import setup as qqbot_setup
from API.apis.push.qqbot import utils as qqbot_utils
from API.models import PushSetting, QQPrivateMessage

from .admin_auth import notify_success, superadmin_required

#: QQBot 页地址（保存 / 出错后回跳）
QQBOT_REDIRECT = 'website:console_qqbot'

#: 一键部署状态 -> 展示名
STATE_LABELS = {
    qqbot_setup.STATE_IDLE: '空闲',
    qqbot_setup.STATE_RUNNING: '进行中',
    qqbot_setup.STATE_SUCCESS: '成功',
    qqbot_setup.STATE_FAILED: '失败',
}

#: 日志级别 -> 文本色（与模板里 JS 的映射同源，避免两处各写一份）
LOG_LEVEL_CSS = {
    'step': 'text-info', 'ok': 'text-success', 'warn': 'text-warning',
    'error': 'text-error', 'cmd': 'text-accent',
}

#: 单行日志超过这个长度就折叠显示（安装器输出常是超长行）
LOG_PREVIEW_LEN = 400

#: 好友消息面板：单个会话最多展示多少条（更早的已落库）
MSG_THREAD_SIZE = 200

#: 会话列表最多回溯多少条消息来提取「出现过的好友」与其昵称
MSG_CHAT_SCAN = 500

#: 「好友消息」里的表情面板：QQ 经典表情表（id 即 QQ 表情编号，name 为官方名称）
#: 发送时插成 `[CQ:face,id=<id>]`；label 只是便于扫视的近似 emoji（真正的表情由 id 决定）
MSG_FACES = [
    {'id': 0, 'name': '微笑', 'label': '🙂'}, {'id': 1, 'name': '撇嘴', 'label': '😒'},
    {'id': 2, 'name': '色', 'label': '😍'}, {'id': 3, 'name': '发呆', 'label': '😳'},
    {'id': 4, 'name': '得意', 'label': '😎'}, {'id': 5, 'name': '流泪', 'label': '😭'},
    {'id': 6, 'name': '害羞', 'label': '😊'}, {'id': 7, 'name': '闭嘴', 'label': '🤐'},
    {'id': 8, 'name': '睡', 'label': '😴'}, {'id': 9, 'name': '大哭', 'label': '😢'},
    {'id': 10, 'name': '尴尬', 'label': '😅'}, {'id': 11, 'name': '发怒', 'label': '😡'},
    {'id': 12, 'name': '调皮', 'label': '😜'}, {'id': 13, 'name': '呲牙', 'label': '😁'},
    {'id': 14, 'name': '惊讶', 'label': '😲'}, {'id': 15, 'name': '难过', 'label': '😔'},
    {'id': 16, 'name': '酷', 'label': '🕶'}, {'id': 17, 'name': '冷汗', 'label': '😰'},
    {'id': 18, 'name': '抓狂', 'label': '😫'}, {'id': 19, 'name': '吐', 'label': '🤮'},
    {'id': 20, 'name': '偷笑', 'label': '🤭'}, {'id': 21, 'name': '可爱', 'label': '😚'},
    {'id': 22, 'name': '白眼', 'label': '🙄'}, {'id': 23, 'name': '傲慢', 'label': '😤'},
    {'id': 24, 'name': '饥饿', 'label': '🤤'}, {'id': 25, 'name': '困', 'label': '😪'},
    {'id': 26, 'name': '惊恐', 'label': '😱'}, {'id': 27, 'name': '流汗', 'label': '😓'},
    {'id': 28, 'name': '憨笑', 'label': '😄'}, {'id': 29, 'name': '大兵', 'label': '🎖'},
    {'id': 30, 'name': '奋斗', 'label': '💪'}, {'id': 31, 'name': '咒骂', 'label': '🤬'},
    {'id': 32, 'name': '疑问', 'label': '❓'}, {'id': 33, 'name': '嘘', 'label': '🤫'},
    {'id': 34, 'name': '晕', 'label': '😵'}, {'id': 35, 'name': '折磨', 'label': '😖'},
    {'id': 36, 'name': '衰', 'label': '😞'}, {'id': 37, 'name': '骷髅', 'label': '💀'},
    {'id': 38, 'name': '敲打', 'label': '🔨'}, {'id': 39, 'name': '再见', 'label': '👋'},
    {'id': 40, 'name': '擦汗', 'label': '😅'}, {'id': 41, 'name': '抠鼻', 'label': '👃'},
    {'id': 42, 'name': '鼓掌', 'label': '👏'}, {'id': 43, 'name': '糗大了', 'label': '😳'},
    {'id': 44, 'name': '坏笑', 'label': '😏'}, {'id': 45, 'name': '左哼哼', 'label': '😤'},
    {'id': 46, 'name': '右哼哼', 'label': '😤'}, {'id': 47, 'name': '哈欠', 'label': '🥱'},
    {'id': 48, 'name': '鄙视', 'label': '😒'}, {'id': 49, 'name': '委屈', 'label': '🥺'},
    {'id': 50, 'name': '快哭了', 'label': '😢'}, {'id': 51, 'name': '阴险', 'label': '😈'},
    {'id': 52, 'name': '亲亲', 'label': '😘'}, {'id': 53, 'name': '吓', 'label': '😨'},
    {'id': 54, 'name': '可怜', 'label': '🥺'}, {'id': 55, 'name': '菜刀', 'label': '🔪'},
    {'id': 56, 'name': '西瓜', 'label': '🍉'}, {'id': 57, 'name': '啤酒', 'label': '🍺'},
    {'id': 58, 'name': '篮球', 'label': '🏀'}, {'id': 59, 'name': '乒乓', 'label': '🏓'},
    {'id': 60, 'name': '咖啡', 'label': '☕'}, {'id': 61, 'name': '饭', 'label': '🍚'},
    {'id': 62, 'name': '猪头', 'label': '🐷'}, {'id': 63, 'name': '玫瑰', 'label': '🌹'},
    {'id': 64, 'name': '凋谢', 'label': '🥀'}, {'id': 65, 'name': '示爱', 'label': '😍'},
    {'id': 66, 'name': '爱心', 'label': '❤️'}, {'id': 67, 'name': '心碎', 'label': '💔'},
    {'id': 68, 'name': '蛋糕', 'label': '🎂'}, {'id': 69, 'name': '闪电', 'label': '⚡'},
    {'id': 70, 'name': '炸弹', 'label': '💣'}, {'id': 71, 'name': '刀', 'label': '🔪'},
    {'id': 72, 'name': '足球', 'label': '⚽'}, {'id': 73, 'name': '瓢虫', 'label': '🐞'},
    {'id': 74, 'name': '便便', 'label': '💩'}, {'id': 75, 'name': '月亮', 'label': '🌙'},
    {'id': 76, 'name': '太阳', 'label': '☀️'}, {'id': 77, 'name': '礼物', 'label': '🎁'},
    {'id': 78, 'name': '拥抱', 'label': '🤗'}, {'id': 79, 'name': '强', 'label': '👍'},
    {'id': 80, 'name': '弱', 'label': '👎'}, {'id': 81, 'name': '握手', 'label': '🤝'},
    {'id': 82, 'name': '胜利', 'label': '✌️'}, {'id': 83, 'name': '抱拳', 'label': '🙏'},
    {'id': 84, 'name': '勾引', 'label': '😏'}, {'id': 85, 'name': '拳头', 'label': '👊'},
    {'id': 86, 'name': '差劲', 'label': '👎'}, {'id': 87, 'name': '爱你', 'label': '😘'},
    {'id': 88, 'name': 'NO', 'label': '🙅'}, {'id': 89, 'name': 'OK', 'label': '👌'},
    {'id': 90, 'name': '爱情', 'label': '💑'}, {'id': 91, 'name': '飞吻', 'label': '😘'},
    {'id': 92, 'name': '跳跳', 'label': '🕺'}, {'id': 93, 'name': '发抖', 'label': '🥶'},
    {'id': 94, 'name': '怄火', 'label': '😡'}, {'id': 95, 'name': '转圈', 'label': '🌀'},
    {'id': 96, 'name': '磕头', 'label': '🙇'}, {'id': 97, 'name': '回头', 'label': '🔙'},
    {'id': 98, 'name': '跳绳', 'label': '🤸'}, {'id': 99, 'name': '挥手', 'label': '🙋'},
    {'id': 100, 'name': '激动', 'label': '🎉'}, {'id': 101, 'name': '街舞', 'label': '🕺'},
    {'id': 102, 'name': '献吻', 'label': '😘'}, {'id': 103, 'name': '左太极', 'label': '☯️'},
    {'id': 104, 'name': '右太极', 'label': '☯️'}, {'id': 105, 'name': '双喜', 'label': '🎊'},
    {'id': 106, 'name': '鞭炮', 'label': '🧨'}, {'id': 107, 'name': '灯笼', 'label': '🏮'},
    {'id': 108, 'name': '发财', 'label': '🧧'},
]


def _origin(request):
    """当前访问站点源（scheme + host），用于推断事件回调基址"""
    return request.build_absolute_uri('/').rstrip('/')


def _local_time(value):
    """带时区的时间 -> 站点本地时间字符串"""
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M:%S') if value else ''


def _short_time(value):
    """带时区的时间 -> 会话列表用的短时间（月-日 时:分）"""
    return timezone.localtime(value).strftime('%m-%d %H:%M') if value else ''


@superadmin_required
def legacy_settings_redirect(request):
    """旧「推送设置」地址：配置已并入 QQBot 操作台，保留跳转

    同样经 `superadmin_required`（而不是裸 RedirectView），以保持后台「入口隐身」口径：
    非超管访问时按安全设置返回 404 / 跳登录，不会因为一个 302 暴露后台目录的存在。
    """
    return redirect(QQBOT_REDIRECT)


@superadmin_required
def qqbot_view(request):
    """QQBot 操作台：连接配置 + 一键部署 + 好友消息"""
    setting = PushSetting.get_solo()
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save':
            return _save_settings(request, setting)
        if action == 'test':
            return _test_qqbot(request)
        if action == 'deploy':
            return _deploy_qqbot(request)
        if action == 'stop':
            return _stop_qqbot(request)
        if action == 'clear_log':
            return _clear_log(request)
        if action == 'reply':
            return _reply_message(request)
        messages.error(request, _('不支持的操作'))
        return redirect(QQBOT_REDIRECT)

    lines = _log_lines()
    return render(request, 'console/qqbot.html', {
        'setting': setting,
        'probe': qqbot_setup.probe(),
        'hook_url': setting.hook_callback_url(),
        'deploy_lines': lines,
        'last_seq': lines[-1]['seq'] if lines else 0,
        'state_labels': {key: _(label) for key, label in STATE_LABELS.items()},
        'log_level_css_json': json.dumps(LOG_LEVEL_CSS),
        'log_preview_len': LOG_PREVIEW_LEN,
        'msg_faces': MSG_FACES,
        'ai_personas': PushSetting.Persona.choices,
        **_messages_context(request),
    })


# ==================== 连接配置 ====================

def _save_settings(request, setting):
    """保存 QQBot 连接配置（token 留空表示保持原值）"""
    base = (request.POST.get('qqbot_api_base') or '').strip().rstrip('/')
    token = (request.POST.get('qqbot_token') or '').strip()
    timeout_raw = (request.POST.get('qqbot_timeout') or '').strip()
    qq = (request.POST.get('napcat_qq') or '').strip()
    napcat_path = (request.POST.get('napcat_dir') or '').strip()
    hook_base = (request.POST.get('hook_base') or '').strip().rstrip('/')
    # AI 自动回复：开关按复选框约定（勾上才在 POST 里），人格必须是内置三种之一
    ai_enabled = request.POST.get('ai_reply_enabled') == 'on'
    ai_persona = (request.POST.get('ai_persona') or '').strip()

    if ai_persona not in PushSetting.Persona.values:
        messages.error(request, _('AI 人格取值非法，请从内置的三种里选择'))
        return redirect(QQBOT_REDIRECT)

    if base and not base.startswith(('http://', 'https://')):
        messages.error(request, _('QQBot HTTP 地址必须以 http:// 或 https:// 开头'))
        return redirect(QQBOT_REDIRECT)
    if hook_base and not hook_base.startswith(('http://', 'https://')):
        messages.error(request, _('事件回调基址必须以 http:// 或 https:// 开头'))
        return redirect(QQBOT_REDIRECT)
    if qq and not qq.isdigit():
        messages.error(request, _('机器人 QQ 号必须是数字'))
        return redirect(QQBOT_REDIRECT)
    try:
        timeout = int(timeout_raw)
    except (TypeError, ValueError):
        messages.error(request, _('超时必须填整数（秒）'))
        return redirect(QQBOT_REDIRECT)
    if timeout < 1:
        messages.error(request, _('超时至少 1 秒'))
        return redirect(QQBOT_REDIRECT)

    setting.qqbot_api_base = base
    setting.qqbot_timeout = timeout
    setting.napcat_qq = qq
    setting.napcat_dir = napcat_path
    setting.hook_base = hook_base
    setting.ai_reply_enabled = ai_enabled
    setting.ai_persona = ai_persona
    if token:
        setting.qqbot_token = token
    setting.save()

    notify_success(request, _('QQBot 配置已保存'))
    return redirect(QQBOT_REDIRECT)


def _test_qqbot(request):
    """测试连接：调 NapCat /get_login_info 校验地址与 token（用**已保存**的配置）"""
    ok, info = qqbot_utils.get_login_info()
    if ok:
        notify_success(request, _('连接成功：当前登录的 QQ 为 %(nick)s（%(qq)s）')
                       % {'nick': info['nickname'] or '—', 'qq': info['user_id'] or '—'})
    else:
        messages.error(request, _('连接失败：%(msg)s') % {'msg': info})
    return redirect(QQBOT_REDIRECT)


# ==================== 一键部署 ====================

def _deploy_qqbot(request):
    """一键部署：先确保回调基址已确定（默认取当前访问域名），再启动后台流水线"""
    setting = PushSetting.get_solo()
    if not (setting.hook_base or '').strip():
        setting.hook_base = _origin(request)
        setting.save(update_fields=['hook_base', 'updated_time'])
    ok, message = qqbot_setup.start_pipeline()
    if ok:
        notify_success(request, _('已开始一键部署，下方「实时日志」会显示每一步进度'))
    else:
        messages.error(request, _(message))
    return redirect(QQBOT_REDIRECT)


def _stop_qqbot(request):
    """停止 NapCat"""
    ok, message = qqbot_setup.stop()
    (notify_success if ok else messages.warning)(request, _(message))
    return redirect(QQBOT_REDIRECT)


def _sse(payload):
    """SSE 帧（与海角自动注册、AI 流式对话同一格式）"""
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


@superadmin_required
def qqbot_stream_view(request):
    """QQBot 部署实时日志流（SSE）

    先把「已有行」推完（断线重连 / 刷新页面都不会丢），再尾随到流程结束；
    为避免长期占用 worker，最长 15 分钟后主动收尾（流程本身仍在后台跑，刷新即可继续看）。
    """
    try:
        since = int(request.GET.get('from') or 0)
    except ValueError:
        since = 0

    def gen():
        cursor = since
        deadline = time.time() + 900
        while True:
            frames, state = qqbot_setup.next_frames(cursor)
            for frame in frames:
                cursor = frame['seq']
                yield _sse({'type': 'line', **frame})
            if state != qqbot_setup.STATE_RUNNING and not frames:
                break
            if time.time() > deadline:
                yield _sse({'type': 'error',
                            'msg': '日志流超时结束（流程可能仍在后台运行，刷新页面可继续查看）'})
                break
            time.sleep(0.4)
        yield _sse({'type': 'state', 'state': state, 'label': _(STATE_LABELS.get(state, ''))})
        yield 'data: [DONE]\n\n'

    response = StreamingHttpResponse(gen(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'       # 禁用 nginx 缓冲，保证逐块推送
    return response


def _log_lines():
    """把已落库的部署日志规范化成模板好渲染的结构（时间戳 / 级别配色 / 超长行折叠）"""
    lines = []
    for line in qqbot_setup.stored_lines():
        text = str(line.get('text') or '')
        level = str(line.get('level') or 'info')
        lines.append({
            'seq': line.get('seq') or 0,
            'level': level,
            'ts': str(line.get('ts') or ''),
            'css': LOG_LEVEL_CSS.get(level, ''),
            'long': len(text) > LOG_PREVIEW_LEN,
            'preview': text[:LOG_PREVIEW_LEN],
            'text': text,
        })
    return lines


def _clear_log(request):
    """清屏：清空部署日志（内存 + 落库）；部署进行中会被拒绝"""
    ok, message = qqbot_setup.clear_logs()
    (notify_success if ok else messages.warning)(request, _(message))
    return redirect(QQBOT_REDIRECT)


# ==================== 好友消息（双栏聊天：会话列表 + 对话流 + 回复） ====================

def _messages_context(request):
    """「好友消息」面板上下文：会话列表（含未读）+ 当前会话的对话流

    用 `?chat=<QQ>` 选中会话；打开即把该会话「收到的」消息标记为已读（未读角标只在会话列表里用）。
    """
    chat = (request.GET.get('chat') or '').strip()
    chats = _chat_summaries()
    thread = []
    if chat:
        QQPrivateMessage.objects.filter(
            user_id=chat, direction=QQPrivateMessage.Direction.IN, is_read=False
        ).update(is_read=True)
        thread = list(QQPrivateMessage.objects.filter(user_id=chat)
                      .order_by('-id')[:MSG_THREAD_SIZE])
        thread.reverse()                       # 面板里按时间正序（老的在上、新的在下）
        for row in thread:
            row.display_time = _local_time(row.received_at or row.create_time)

    return {
        'msg_chats': chats,
        'msg_chat': chat,
        'msg_chat_name': _chat_title(chat) if chat else '',
        'msg_thread': thread,
        'msg_max': MSG_THREAD_SIZE,
        'msg_unread_total': QQPrivateMessage.objects.filter(
            direction=QQPrivateMessage.Direction.IN, is_read=False).count(),
        'msg_last_id': QQPrivateMessage.objects.order_by('-id')
                       .values_list('id', flat=True).first() or 0,
    }


def _chat_title(user_id):
    """会话标题：最近一条带昵称的消息里的昵称，没有就退回 QQ 号"""
    name = (QQPrivateMessage.objects.filter(user_id=user_id).exclude(nickname='')
            .order_by('-id').values_list('nickname', flat=True).first())
    return name or user_id


def _chat_summaries():
    """会话列表：每个私聊过机器人的好友一行（最近一条消息 + 未读数），按最近消息倒序

    只回溯最近 MSG_CHAT_SCAN 条来提取「出现过的好友」，避免消息多起来后每次全表扫。
    """
    latest, names = {}, {}
    for row in QQPrivateMessage.objects.order_by('-id')[:MSG_CHAT_SCAN]:
        if row.user_id not in latest:
            latest[row.user_id] = row
        if row.user_id not in names and row.nickname:
            names[row.user_id] = row.nickname          # 昵称取最近一条带昵称的

    unread = dict(
        QQPrivateMessage.objects.filter(direction=QQPrivateMessage.Direction.IN, is_read=False)
        .values('user_id').annotate(n=Count('id')).values_list('user_id', 'n')
    )
    starred = dict(
        QQPrivateMessage.objects.filter(is_starred=True)
        .values('user_id').annotate(n=Count('id')).values_list('user_id', 'n')
    )
    return [{
        'user_id': user_id,
        'nickname': names.get(user_id, ''),
        'last_content': row.content,
        'last_time': _short_time(row.received_at or row.create_time),
        'last_direction': row.direction,
        'unread': unread.get(user_id, 0),
        'starred': starred.get(user_id, 0),
    } for user_id, row in latest.items()]


def _send_reply(to_user, text, images=()):
    """把内容以私聊发给该好友，并在对话流里记一条「发出」

    正文支持 CQ 码（表情/图片等）；图片由前端读成 dataURL 传上来，转成
    `[CQ:image,file=base64://…]` 直发（NapCat 支持 base64 图源，不落盘、不需要公网可访问）。
    :return: (ok, 说明, QQPrivateMessage or None)；失败时说明是失败原因
    """
    try:
        outgoing, display = qqbot_utils.build_reply(text, images)
    except ValueError as exc:
        return False, str(exc), None
    if not outgoing:
        return False, _('请输入要发送的内容'), None

    ok, result = qqbot_utils.send(outgoing, qqbot_utils.TARGET_PRIVATE, to_user)
    if not ok:
        return False, result['message'], None
    row = qqbot_utils.record_outgoing_message(
        to_user, display, message_id=str(result.get('message_id') or ''))
    return True, '', row


def _message_payload(row):
    """消息实体 -> 前端渲染用的字典

    `user_id` / `nickname` 必给：前端「发出后本地直接上屏」会用它去更新会话列表项，
    缺了会走进「新建会话项」分支并对 undefined 取首字母报错（表现为发送成功却提示失败）。
    """
    return {'id': row.id, 'user_id': row.user_id, 'nickname': row.nickname,
            'direction': row.direction, 'content': row.content,
            'starred': row.is_starred,
            'can_recall': (row.direction == QQPrivateMessage.Direction.OUT
                           and bool(row.message_id)),
            'time': _local_time(row.received_at or row.create_time)}


def _reply_message(request):
    """表单方式的回复（无 JS 时的兜底）：成功后整页回到该会话"""
    to_user = (request.POST.get('to_user') or '').strip()
    content = (request.POST.get('content') or '').strip()
    if not to_user.isdigit():
        messages.error(request, _('请先选择要回复的好友'))
        return redirect(QQBOT_REDIRECT)
    if not content:
        messages.error(request, _('请输入要发送的内容'))
        return redirect(_chat_url(to_user))

    ok, reason, _row = _send_reply(to_user, content)
    if ok:
        notify_success(request, _('已发送给 QQ %(qq)s') % {'qq': to_user})
    else:
        messages.error(request, _('发送失败：%(msg)s') % {'msg': reason})
    return redirect(_chat_url(to_user))


@superadmin_required
def qqbot_messages_thread_view(request):
    """切换会话（无刷新）：返回该会话的对话流，并把它标记为已读

    用 GET 而不是 POST：切换会话是「读」操作，而 `superadmin_required` 会把所有 POST 记进
    控制台操作日志 —— 走 POST 的话每点一次会话都会塞一条审计，把真正的操作淹没。
    """
    chat = (request.GET.get('chat') or '').strip()
    if not chat.isdigit():
        return JsonResponse({'ok': False, 'message': _('会话不合法')})

    QQPrivateMessage.objects.filter(
        user_id=chat, direction=QQPrivateMessage.Direction.IN, is_read=False
    ).update(is_read=True)
    rows = list(QQPrivateMessage.objects.filter(user_id=chat)
                .order_by('-id')[:MSG_THREAD_SIZE])
    rows.reverse()
    return JsonResponse({
        'ok': True, 'chat': chat, 'title': _chat_title(chat),
        'messages': [_message_payload(row) for row in rows],
    })


@superadmin_required
@require_POST
def qqbot_messages_reply_view(request):
    """发送回复（无刷新）：JSON 进出，成功时把这条「发出」消息回给前端直接上屏

    支持 CQ 码正文（表情等）与图片：图片由前端读成 dataURL 放在 `images[]` 里。
    """
    to_user = (request.POST.get('to_user') or '').strip()
    text = (request.POST.get('content') or '').strip()
    images = request.POST.getlist('images')
    if not to_user.isdigit():
        return JsonResponse({'ok': False, 'message': _('请先选择要回复的好友')})

    ok, reason, row = _send_reply(to_user, text, images)
    if not ok:
        return JsonResponse({'ok': False, 'message': reason})
    return JsonResponse({'ok': True, 'message': _('已发送给 QQ %(qq)s') % {'qq': to_user},
                         'item': _message_payload(row)})


@superadmin_required
@require_POST
def qqbot_messages_star_view(request):
    """星标 / 取消星标某条消息（无刷新）；星标不随「已读」变化，便于事后回看"""
    row = _message_by_id(request)
    if row is None:
        return JsonResponse({'ok': False, 'message': _('消息不存在，可能已被清理')})
    row.is_starred = not row.is_starred
    row.save(update_fields=['is_starred', 'updated_time'])
    return JsonResponse({'ok': True, 'starred': row.is_starred})


@superadmin_required
@require_POST
def qqbot_messages_delete_view(request):
    """删除一条消息记录；`mode=recall` 时先在 QQ 侧撤回（只有自己发出的能撤回）

    :param mode: 'local'（只删本地记录）/'recall'（撤回 + 删本地记录）
    """
    row = _message_by_id(request)
    if row is None:
        return JsonResponse({'ok': False, 'message': _('消息不存在，可能已被清理')})

    if request.POST.get('mode') == 'recall':
        if row.direction != QQPrivateMessage.Direction.OUT:
            return JsonResponse({'ok': False, 'message': _('只能撤回自己发出的消息')})
        ok, reason = qqbot_utils.recall_message(row.message_id)
        if not ok:
            # 撤回失败常见原因是超过 QQ 的时限；如实回传，让管理员改选「仅删除本地记录」
            return JsonResponse({'ok': False, 'message': _('撤回失败：%(msg)s') % {'msg': reason}})

    row.delete()
    return JsonResponse({'ok': True})


def _message_by_id(request):
    """按 POST 里的 id 取消息（非法 id 直接当作不存在）"""
    raw = (request.POST.get('id') or '').strip()
    if not raw.isdigit():
        return None
    return QQPrivateMessage.objects.filter(pk=int(raw)).first()


def _chat_url(user_id):
    """回到指定会话的地址（消息面板用 ?chat=<QQ> 选中会话）"""
    return f'{reverse(QQBOT_REDIRECT)}?chat={quote(str(user_id))}'


@superadmin_required
def qqbot_messages_stream_view(request):
    """好友消息实时流（SSE）：按主键增量推送新消息（收到 / 后台回复发出都推）

    参数：`from=<已收到的最大 id>`（断线重连时只推之后的）。
    为不长期占用 worker，最长 15 分钟后主动收尾（前端会带最新 cursor 重连，不会丢消息）。
    """
    try:
        since = int(request.GET.get('from') or 0)
    except ValueError:
        since = 0

    def gen():
        from django.db import close_old_connections

        cursor = since
        deadline = time.time() + 900
        while time.time() < deadline:
            close_old_connections()            # 长连接里别攥着旧连接
            rows = list(QQPrivateMessage.objects.filter(id__gt=cursor).order_by('id')[:50])
            for row in rows:
                cursor = row.id
                yield _sse({
                    'type': 'message', 'id': row.id, 'user_id': row.user_id,
                    'nickname': row.nickname, 'content': row.content,
                    'direction': row.direction,
                    'time': _local_time(row.received_at or row.create_time),
                })
            time.sleep(0.2 if rows else 1.0)
        yield 'data: [DONE]\n\n'

    response = StreamingHttpResponse(gen(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'       # 禁用 nginx 缓冲，保证逐块推送
    return response
