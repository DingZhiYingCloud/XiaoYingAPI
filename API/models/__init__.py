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
    AI_RUNNING_STALE_MINUTES,
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
from API.models.Accounts.account import AccountStatus, Platform, PlatformAccount
from API.models.Docs.announcement import Announcement
from API.models.AI.provider import AiModel, AiProvider, AiSystemPrompt
from API.models.Website.appearance import SiteAppearance
from API.models.Security.audit import ConsoleAuditLog
from API.models.Security.ip_ban import BannedIP
from API.models.Security.setting import SecuritySetting
from API.models.Quota.service import QuotaService
from API.models.Quota.setting import QuotaSetting
from API.models.Payment.ledger import UserBalanceLedger
from API.models.Payment.order import PayNotifyLog, PayOrder, PayRefundRequest
from API.models.Payment.provider import PayProvider
from API.models.Payment.setting import PaySetting
from API.models.OrderMigration.blacklist import DEFAULT_BLACKLIST_WORDS, OrderMigrationBlacklist
from API.models.OrderMigration.order_migration import MigrationStatus, OrderMigration
from API.models.OrderMigration.setting import OrderMigrationSetting
from API.models.Push.log import PushLog
from API.models.Push.message import QQPrivateMessage
from API.models.Push.setting import PushSetting

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
    'AI_RUNNING_STALE_MINUTES',
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
    'PlatformAccount',
    'Platform',
    'AccountStatus',
    'Announcement',
    'AiProvider',
    'AiSystemPrompt',
    'AiModel',
    'SiteAppearance',
    'SecuritySetting',
    'ConsoleAuditLog',
    'BannedIP',
    'QuotaService',
    'QuotaSetting',
    'PaySetting',
    'PayProvider',
    'PayOrder',
    'PayNotifyLog',
    'PayRefundRequest',
    'UserBalanceLedger',
    'OrderMigration',
    'MigrationStatus',
    'OrderMigrationSetting',
    'OrderMigrationBlacklist',
    'DEFAULT_BLACKLIST_WORDS',
    'PushLog',
    'PushSetting',
    'QQPrivateMessage',
]
