"""消息推送 push · 邮件线路 业务层（发送邮件）

原「邮箱服务」(`API/apis/emails/v1/`) 的发送邮件能力已并入「消息推送服务」，
本模块是**唯一实现**：API 端点（`/api/push/email/send`）与站内各内部通知
（验证邮件、余量告警、图床容量告警、代练搬单被接单通知）都复用这里。

发信走 Django 邮件后端（settings 里配置的邮箱），支持纯文本或 HTML 正文。
每次发信（无论成功失败）都会落一条 `PushLog`（渠道 `email`），与 Server酱 推送共用
控制台「推送日志」页；内部通知的 app_id 为空，日志里「项目」列为空。
"""
import logging

from django.core.mail import EmailMessage

logger = logging.getLogger('api.push')

# 推送渠道标识（PushLog.channel）
CHANNEL = 'email'


def _log(subject, body, recipients, ok, message='', app_id=''):
    """落一条推送日志（写库失败不影响发信结果，只记异常）"""
    from API.models import PushLog

    try:
        PushLog.objects.create(
            channel=CHANNEL, app_id=app_id or '', title=(subject or '')[:255],
            content=body or '', recipients=','.join(recipients or [])[:1000],
            ok=ok, message=(message or '')[:500])
    except Exception:                       # noqa: BLE001 发信已发生，日志失败不应改变对外结果
        logger.exception('推送日志写入失败')


def send_email(subject, body, recipients, html_body=None, app_id=''):
    """
    发送邮件(使用 settings 中配置的 QQ 邮箱作为发件人)

    :param subject: str  邮件标题
    :param body:    str  邮件正文内容(纯文本)
    :param recipients: list[str]  收件人邮箱地址列表
    :param html_body: str | None  HTML 正文(可选)；提供时按 HTML 邮件发送
    :param app_id: str  发起调用的接入项目 APPID（仅用于推送日志，可空）
    :return: tuple[bool, str]  (是否发送成功, 描述信息)
    """
    try:
        # 构建邮件对象:发件人默认使用 settings.DEFAULT_FROM_EMAIL
        email = EmailMessage(
            subject=subject,
            body=body,
            to=recipients,
        )
        # 提供 HTML 正文时切换为 HTML 邮件（body 作为纯文本回退）
        if html_body:
            email.content_subtype = 'html'
            email.body = html_body
        # fail_silently=False:发送失败时抛出异常,便于上层捕获
        email.send(fail_silently=False)
    except Exception as e:
        # 捕获所有异常(SMTP连接失败、认证错误、网络错误等)
        message = f'邮件发送失败: {e}'
        _log(subject, body, recipients, ok=False, message=message, app_id=app_id)
        return False, message

    _log(subject, body, recipients, ok=True, message='邮件发送成功', app_id=app_id)
    return True, '邮件发送成功'
