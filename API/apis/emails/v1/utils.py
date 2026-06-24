"""邮箱发送工具模块

封装基于 Django 邮件后端的发送逻辑,使用项目 settings 中配置的 QQ 邮箱。
"""
from django.core.mail import EmailMessage


def send_email(subject, body, recipients):
    """
    发送邮件(使用 settings 中配置的 QQ 邮箱作为发件人)

    :param subject: str  邮件标题
    :param body:    str  邮件正文内容(纯文本)
    :param recipients: list[str]  收件人邮箱地址列表
    :return: tuple[bool, str]  (是否发送成功, 描述信息)
    """
    try:
        # 构建邮件对象:发件人默认使用 settings.DEFAULT_FROM_EMAIL
        email = EmailMessage(
            subject=subject,
            body=body,
            to=recipients,
        )
        # fail_silently=False:发送失败时抛出异常,便于上层捕获
        email.send(fail_silently=False)
        return True, '邮件发送成功'
    except Exception as e:
        # 捕获所有异常(SMTP连接失败、认证失败、网络错误等)
        return False, f'邮件发送失败: {e}'
