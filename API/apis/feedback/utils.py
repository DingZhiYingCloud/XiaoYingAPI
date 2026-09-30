"""问题反馈中心 · 业务逻辑（对外 API 端点 + 页面 / 后台共用的工具）

反馈中心的主体能力（提交 / 查看 / 回复 / 公开区）都在**我们托管的反馈页**上，
`/api/feedback/` 只保留两个「子项目可以直接调用」的端点：

    ticket   —— 用用户 UAC Token 换一张一次性票据，交给反馈页完成登录态传递
    contacts —— 查某个接入项目的开发者联系方式（子项目想在自己页面展示时用）

两个端点都配成 `auth_mode=open`（见迁移 `0043_feedback_seed`）：它们要被**子项目前端**
直接调用，而前端不可能持有 AppSecret。安全上不亏：

- ticket 的凭证是用户自己的 UAC Token —— 调用者本来就持有它，也能用它冒充自己；
  票据 5 分钟过期且只能用一次（见 `FeedbackTicket` 模块说明）
- contacts 是公开信息 —— 同样的内容也展示在公开反馈页上

其余涉及「写」的能力一律不开放：提交与跟帖都发生在反馈页里，由本站直接处理。

`save_attachments()` 是反馈页与超管后台共用的附件落盘 + 校验逻辑（同一套上限口径）。
"""
from django.utils.translation import gettext as _

from API.apis.uploads.utils import FileUploader
from API.common import StatusCode
from API.common.credential_crypto import hash_token
from API.models import FeedbackAttachment, FeedbackTicket, ProjectContact, UserApp, UserToken
from API.models.Feedback.ticket import TICKET_TTL_SECONDS


def client_ip(request) -> str:
    """客户端 IP（优先反向代理透传头，兜底 REMOTE_ADDR）

    用于票据签发留痕与游客提交的防刷计数。
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('HTTP_X_REAL_IP', '') or request.META.get('REMOTE_ADDR', '')


def serialize_contacts(app) -> list:
    """某项目已启用的开发者联系方式（前台展示与对外接口共用同一口径）"""
    rows = (ProjectContact.objects
            .filter(app=app, platform__enabled=True)
            .select_related('platform'))
    return [{
        'platform': row.platform.code,
        'name': row.platform.name,
        'icon': row.platform.icon,
        'label': row.platform.item_label,
        'value': row.value,
        'url': row.url,
    } for row in rows]


def issue_ticket(token, ip=''):
    """用用户 UAC Token 换一张一次性反馈票据

    Token 在库里是**哈希存储**的，故直接按哈希查 `UserToken`（无需先知道是哪个项目）；
    查到后按 `UserToken.is_valid` 统一判定（未过期 + 用户启用 + 项目启用）。

    :return: (True, {ticket, expire_in, app_id, app_name}) / (False, 错误文案)
    """
    token = (token or '').strip()
    if not token:
        return False, '参数缺失: token(用户登录Token)'

    record = (UserToken.objects.select_related('app', 'user')
              .filter(token=hash_token(token)).first())
    if record is None:
        return False, 'Token 无效: 不存在'
    if not record.is_valid:
        return False, 'Token 已失效: 已过期 / 用户封禁 / 项目停用'

    ticket = FeedbackTicket.issue(record.app, record.user, ip=ip)
    return True, {
        'ticket': ticket.token,
        'expire_in': TICKET_TTL_SECONDS,
        'app_id': record.app.app_id,
        'app_name': record.app.name,
    }


def list_contacts(app_id):
    """查某个接入项目的开发者联系方式

    :return: (True, {app_id, app_name, contacts}) / (False, 错误文案)
    """
    app_id = (app_id or '').strip()
    if not app_id:
        return False, '参数缺失: app_id(接入项目APPID)'

    app = UserApp.objects.filter(app_id=app_id, status=True).first()
    if app is None:
        return False, '项目不存在或已停用'
    return True, {
        'app_id': app.app_id,
        'app_name': app.name,
        'contacts': serialize_contacts(app),
    }


def save_attachments(files, kind, max_count, max_mb) -> tuple:
    """保存一类附件（图片 / 视频）并校验数量与单文件大小

    反馈页的提交与跟帖、超管后台的回复共用这一套口径（上限取自 `FeedbackSetting`）。
    任一附件不合规都会在 `errors` 里记一条，由调用方决定后续：反馈页与后台都选择
    **整单驳回并回显原因**，避免出现「提交成功但附件被悄悄丢掉」的错觉。
    先整体校验再落盘，因此数量 / 大小不合规时不会留下写了一半的中间文件。

    :param files: 待保存的文件列表（Django UploadedFile）
    :param kind: `FeedbackAttachment.Kind.IMAGE` 或 `VIDEO`（同时用作 FileUploader 的上传类型）
    :param max_count: 数量上限；`0` 表示该类附件不允许上传
    :param max_mb: 单文件大小上限（MB）
    :return: (saved, errors) —— saved 为可直接展开传给附件模型的字段字典列表
    """
    files = [f for f in files if f]
    if not files:
        return [], []

    label = _('图片') if kind == FeedbackAttachment.Kind.IMAGE else _('视频')
    if not max_count:
        return [], [_('本项目不允许上传%(label)s') % {'label': label}]
    if len(files) > max_count:
        return [], [_('最多只能上传 %(n)d 个%(label)s') % {'n': max_count, 'label': label}]
    oversized = [f.name for f in files if f.size > max_mb * 1024 * 1024]
    if oversized:
        return [], [_('「%(name)s」超过大小上限 %(mb)dMB') % {'name': name, 'mb': max_mb}
                    for name in oversized]

    saved, errors = [], []
    for upload in files:
        ok, result = FileUploader.save_file(kind, upload)
        if not ok:
            errors.append(_('「%(name)s」上传失败：%(reason)s')
                          % {'name': upload.name, 'reason': result})
            continue
        saved.append({
            'kind': kind,
            'path': result['relative_path'],
            'original_name': (result['original_name'] or '')[:150],
            'size': result['size'],
            'ext': result['ext'],
        })
    return saved, errors


def fail_code(msg, fallback=StatusCode.PARAM_VALUE_INVALID):
    """按业务错误文案前缀映射状态码（与各 API 服务口径一致）"""
    if msg.startswith('参数缺失'):
        return StatusCode.PARAM_MISSING
    if msg.startswith('参数格式错误'):
        return StatusCode.PARAM_FORMAT_ERROR
    if msg.startswith('Token'):
        return StatusCode.UNAUTHORIZED
    return fallback
