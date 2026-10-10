"""消息推送业务域模型导出"""
from API.models.Push.email_task import EmailTask
from API.models.Push.log import PushLog

__all__ = ['PushLog', 'EmailTask']
