"""代练搬单运行设置（单例）

全库只有一行，存搬单流水线的运行参数 —— 与 `QuotaSetting` / `SecuritySetting` 同一惯例：
每个功能单独建表、字段即配置项，单行表读写直观。

这些值原本放 .env，改为后台页面可配，让管理员无需改文件即可调整「我们的 QQ、
轮询间隔、价格区间、自动运行」。
"""
from django.db import models

from API.common.base import BaseModel

# 被接单语音提醒的默认文本（由浏览器播报）
DEFAULT_NOTIFY_SOUND_TEXT = '丸子来新订单了'


class OrderMigrationSetting(BaseModel):
    """代练搬单设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    our_qq = models.CharField(
        '我们的 QQ 号', max_length=32, blank=True, default='',
        help_text='发单时填入代练丸子的账号 / 密码 / 角色名与联系方式，引导打手加好友后私下交接账号')
    interval_seconds = models.PositiveIntegerField(
        '轮询间隔(秒)', default=20, help_text='监控丸子「被接单」的轮询间隔，最小 5 秒')
    publish_limit = models.PositiveIntegerField(
        '每轮发布上限', default=1, help_text='每轮最多发布到代练丸子的订单数')
    deposit_ratio = models.PositiveSmallIntegerField(
        '双金倍数', default=2,
        help_text='丸子双金（安全保证金 + 效率保证金合计）= 发布价 × 该倍数，可设 0-5，默认 2；'
                  '两项均分，即各 = 发布价 × 倍数 ÷ 2')
    price_min = models.FloatField(
        '价格下限(元)', null=True, blank=True, help_text='只搬 >= 该价的代练通订单；留空不限')
    price_max = models.FloatField(
        '价格上限(元)', null=True, blank=True, help_text='只搬 <= 该价的代练通订单；留空不限')
    keyword = models.CharField(
        '标题关键词', max_length=64, blank=True, default='',
        help_text='只搬标题包含该关键词的代练通订单；留空则不限（用于自测时精确只搬自己发的单）')
    use_tier = models.BooleanField(
        '严选发单', default=False,
        help_text='关闭=标准（category=1，与丸子 App 默认一致，低等级打手可接）；'
                  '开启=严选（带 slicePriceCal 服务档位，category=12，要求打手 Lv2+）')
    take_level = models.SmallIntegerField(
        '接单门槛(代练师等级)', default=-1,
        help_text='丸子发单的接单门槛：-1=不限(标准，低等级打手可接) 0=Lv1以上 1=Lv2以上(严选)。'
                  '不设置会沿用平台默认（严选，打手需 Lv2+）')
    revoke_image = models.CharField(
        '撤销凭证图URL', max_length=500, blank=True, default='',
        help_text='抢接失败需「申请撤销」时的凭证图片URL（丸子强制要求至少一张）；'
                  '留空则取消不了时只告警、不自动撤销')
    notify_mail = models.BooleanField(
        '被接单邮件通知', default=False,
        help_text='代练丸子有打手接单时，发一封邮件通知')
    notify_mail_to = models.EmailField(
        '通知邮箱', blank=True, default='',
        help_text='被接单邮件的收件人；留空则用 .env 的 QQ_MAIL_ACCOUNT')
    notify_sound = models.BooleanField(
        '被接单声音提醒', default=False,
        help_text='代练丸子有打手接单时，由后台页面用浏览器语音播报提醒（页面需打开）')
    notify_sound_text = models.CharField(
        '声音文本', max_length=100, blank=True, default=DEFAULT_NOTIFY_SOUND_TEXT,
        help_text='浏览器语音播报的内容')
    auto_run = models.BooleanField(
        '自动运行', default=False,
        help_text='开启后后台线程按间隔自动执行搬单流水线（会真实发单 / 接单，谨慎开启）')
    last_run_time = models.DateTimeField('最近运行时间', null=True, blank=True)
    last_run_summary = models.CharField('最近运行结果', max_length=255, blank=True)
    last_error = models.CharField('最近错误', max_length=500, blank=True)
    run_logs = models.TextField(
        '运行日志', blank=True, default='',
        help_text='最近若干轮运行结果的滚动日志（JSON 文本），供后台页实时展示')

    class Meta:
        db_table = 'order_migration_setting'
        verbose_name = '代练搬单设置'
        verbose_name_plural = '代练搬单设置'

    def __str__(self):
        return f'代练搬单设置（QQ：{self.our_qq or "未配置"}）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'OrderMigrationSetting':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
