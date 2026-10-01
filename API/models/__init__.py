from API.common.base import BaseModel
from API.apis.seo.friend_links.models import FriendLink
from API.models.Music.music import Music, MusicSource
from API.models.Users.user import User, UserLoginLog, UserToken, UserVerifyRecord
from API.models.Users.auth_method import AuthMethod
from API.models.Projects.app import UserApp
from API.models.Auth.policy import ApiServicePolicy
from API.models.Email.email_template import EmailTemplate
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
from API.models.Captcha.captcha import CaptchaChallenge
from API.models.Statistics.api_call_stat import ApiCallStat, ApiCallStatHour
from API.models.ImageHosting.image_hosting_token import ImageHostingToken
from API.models.Haijiao.account import HaijiaoAccount
from API.models.Docs.announcement import Announcement
from API.models.AI.provider import AiModel, AiProvider, AiSystemPrompt
from API.models.Website.appearance import SiteAppearance
from API.models.Security.setting import SecuritySetting

__all__ = [
    'BaseModel',
    'FriendLink',
    'Music',
    'MusicSource',
    'User',
    'UserToken',
    'UserVerifyRecord',
    'UserLoginLog',
    'AuthMethod',
    'UserApp',
    'ApiServicePolicy',
    'EmailTemplate',
    'Feedback',
    'FeedbackType',
    'FeedbackReply',
    'FeedbackAttachment',
    'FeedbackReplyAttachment',
    'FeedbackAuditLog',
    'FeedbackSetting',
    'FeedbackTicket',
    'ContactPlatform',
    'ProjectContact',
    'CaptchaChallenge',
    'ApiCallStat',
    'ApiCallStatHour',
    'ImageHostingToken',
    'HaijiaoAccount',
    'Announcement',
    'AiProvider',
    'AiSystemPrompt',
    'AiModel',
    'SiteAppearance',
    'SecuritySetting',
]
