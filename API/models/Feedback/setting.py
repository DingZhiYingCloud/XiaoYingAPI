"""问题反馈中心 · 全局设置（单例）

反馈中心的全部可调项集中在这一张单行表里，超管在 `/console/feedback/settings/` 维护：
功能总开关、AI 审核开关与两套提示词、审核专用模型、附件数量上限、游客防刷（验证码 + 频率）、
AI 驳回说明图开关、回复邮件通知开关。

为什么是单行表而不是键值表：项目既有惯例是「每个功能单独建表、字段即配置项」
（见服务策略 / 接口公告 / AI 模型），没有统一的键值配置表；反馈中心的配置项彼此强相关、
一起读写，单行表比零散键值更直观，也能直接用 Django 字段类型做校验。
"""
from django.db import models

from API.common.base import BaseModel
from API.models.AI.provider import AiModel


class FeedbackSetting(BaseModel):
    """反馈中心全局设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    enabled = models.BooleanField('启用反馈中心', default=True,
                                  help_text='关闭后前台反馈页停止服务（历史数据与后台仍可访问）')

    # ---------- AI 审核 ----------
    ai_review_enabled = models.BooleanField(
        '提交时先过 AI 审核', default=True,
        help_text='关闭后提交直接进入「待处理」；开启但平台未配置可用模型时同样跳过审核',
    )
    review_model = models.ForeignKey(
        AiModel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='审核专用模型',
        help_text='用于内容审核与回复审查；留空则使用平台默认模型。审核很吃调用量，建议单独指定一个便宜的模型',
    )
    submit_prompt = models.TextField(
        '提交内容审核提示词', blank=True,
        help_text='审核用户提交内容所用的规则。与问题正文、用户信息一起发给 AI，由 AI 判定是否驳回；'
                  '留空则使用内置的通用审核规则（见文档中心「问题反馈中心」章节）',
    )
    reply_prompt = models.TextField(
        '回复语气审查提示词', blank=True,
        help_text='管理员回复前审查所用规则（语气是否得体、是否有攻击性表述等）；'
                  '留空则使用内置的通用审查规则。AI 只提醒，管理员仍可强制发送',
    )
    ai_reject_image = models.BooleanField(
        'AI 驳回时生成说明图', default=True,
        help_text='开启后 AI 只给驳回理由的要点，由本地绘图引擎渲染成中文说明图附在驳回内容里',
    )

    # ---------- 附件上限（全局一套） ----------
    max_images = models.PositiveSmallIntegerField('图片张数上限', default=3,
                                                  help_text='单条反馈 / 单条回复可携带的图片数量上限')
    max_videos = models.PositiveSmallIntegerField('视频个数上限', default=1,
                                                  help_text='单条反馈 / 单条回复可携带的视频数量上限')
    max_image_mb = models.PositiveSmallIntegerField('单张图片大小上限(MB)', default=10)
    max_video_mb = models.PositiveSmallIntegerField('单个视频大小上限(MB)', default=50)

    # ---------- 游客防刷 ----------
    captcha_required = models.BooleanField(
        '游客提交需图形验证码', default=True,
        help_text='登录用户不受影响（身份可追溯）；关闭后游客可无验证码提交，仅靠频率限制兜底',
    )
    rate_limit_hour = models.PositiveIntegerField('同 IP 每小时上限', default=5,
                                                  help_text='同一 IP 每小时最多提交多少条（防刷）')
    rate_limit_day = models.PositiveIntegerField('同 IP 每天上限', default=20,
                                                 help_text='同一 IP 每天最多提交多少条（防刷）')

    # ---------- 通知 ----------
    email_notify = models.BooleanField(
        '回复时发邮件通知', default=True,
        help_text='管理员回复后，给提交时填了邮箱的那条发一封通知邮件（没填邮箱则不通知）',
    )

    class Meta:
        db_table = 'feedback_setting'
        verbose_name = '反馈中心设置'
        verbose_name_plural = '反馈中心设置'

    def __str__(self):
        return '反馈中心设置'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'FeedbackSetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
