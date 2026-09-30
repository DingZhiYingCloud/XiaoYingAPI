"""问题反馈业务域

统一问题反馈调度中心的一组模型：
    feedback.py - 反馈类型 / 反馈主表 / 回复 / 附件 / AI 审核留痕
    contact.py  - 开发者联系方式（平台字典 + 项目绑定）
    setting.py  - 反馈中心全局设置（单例）
"""
from API.models.Feedback.contact import ContactPlatform, ProjectContact
from API.models.Feedback.feedback import (
    Feedback,
    FeedbackAttachment,
    FeedbackAuditLog,
    FeedbackReply,
    FeedbackReplyAttachment,
    FeedbackType,
)
from API.models.Feedback.setting import FeedbackSetting
from API.models.Feedback.ticket import FeedbackTicket

__all__ = [
    'ContactPlatform',
    'Feedback',
    'FeedbackAttachment',
    'FeedbackAuditLog',
    'FeedbackReply',
    'FeedbackReplyAttachment',
    'FeedbackSetting',
    'FeedbackTicket',
    'FeedbackType',
    'ProjectContact',
]
