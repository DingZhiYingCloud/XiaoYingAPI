"""问题反馈中心 · 开发者联系方式（平台字典 + 项目绑定）

接入反馈中心后，每个子项目都要有「查看开发者联系方式」的位置——用户在提交反馈前或
查看回复时，能一眼看到开发者怎么联系。联系方式按**项目**分别维护：同一个平台在不同
项目下可以是不同的值。

    ContactPlatform - 平台字典（QQ / QQ 邮箱 / 微信 / Telegram / WhatsApp / Discord …），
                      超管增删改；`url_template` 决定「值」能否渲染成可点击链接
    ProjectContact  - 某个项目在某平台上的联系方式（项目 × 平台 = 一条）

平台字典与项目绑定是强关联聚合（绑定离开平台无意义），故同写本文件。
"""
import uuid

from django.db import models

from API.common.base import BaseModel
from API.models.Projects.app import UserApp

# 允许的跳转协议前缀：链接会渲染成 <a href>，必须挡掉 javascript: 这类危险协议
SAFE_URL_PREFIXES = ('http://', 'https://', 'mailto:', 'tel:')


class ContactPlatform(BaseModel):
    """联系方式平台字典（超管维护，全局一套）"""

    code = models.SlugField('平台标识', max_length=30, unique=True,
                            help_text='英文小写标识，如 qq / qqmail / wechat / telegram；仅内部使用')
    name = models.CharField('平台名称', max_length=30, help_text='展示用，如「QQ」「Telegram」')
    icon = models.CharField('图标', max_length=30, blank=True,
                            help_text='lucide 图标名（如 message-circle / send），留空则只显示文字')
    value_label = models.CharField('填写项名称', max_length=30, blank=True,
                                   help_text='后台填值时的字段名，如「QQ 号」「微信号」「用户名」；留空则用「联系方式」')
    url_template = models.CharField(
        '跳转链接模板', max_length=200, blank=True,
        help_text='选填：把值拼成可点击链接，用 {value} 占位。'
                  '如 https://t.me/{value}、mailto:{value}；必须以 http://、https://、mailto: 或 tel: 开头',
    )
    enabled = models.BooleanField('启用', default=True, help_text='停用后不在前台展示（已填的值保留）')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前（前台展示顺序）')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'contact_platform'
        verbose_name = '联系方式平台'
        verbose_name_plural = '联系方式平台'
        ordering = ('sort', 'code')

    def __str__(self):
        return self.name

    @property
    def item_label(self) -> str:
        """「值」这一栏的字段名（未配置时回落为「联系方式」）"""
        return self.value_label or '联系方式'

    def build_url(self, value: str) -> str:
        """把值按模板拼成可点击链接；模板为空或协议不安全时返回空串

        协议白名单见模块常量 `SAFE_URL_PREFIXES`：模板由超管填写，这里再挡一道，
        避免 `javascript:` 之类的模板渲进 `<a href>` 造成 XSS。
        """
        template = (self.url_template or '').strip()
        value = (value or '').strip()
        if not template or not value:
            return ''
        url = template.replace('{value}', value)
        if not url.lower().startswith(SAFE_URL_PREFIXES):
            return ''
        return url


class ProjectContact(BaseModel):
    """某个接入项目在某平台上的联系方式（项目 × 平台 = 一条）"""

    app = models.ForeignKey(
        UserApp, on_delete=models.CASCADE, related_name='contacts', verbose_name='所属项目',
    )
    platform = models.ForeignKey(
        ContactPlatform, on_delete=models.PROTECT, related_name='entries', verbose_name='联系方式平台',
        help_text='平台被删除前需先清掉各项目下的绑定（PROTECT 保护，避免误删导致前台联系方式整体消失）',
    )
    value = models.CharField('联系方式', max_length=200, help_text='该平台上的具体值，如 QQ 号 / 微信号 / 用户名')
    sort = models.IntegerField('排序', default=0, help_text='数字越小越靠前（同一项目内排序）')
    remark = models.CharField('备注', max_length=255, blank=True)

    class Meta:
        db_table = 'project_contact'
        verbose_name = '项目联系方式'
        verbose_name_plural = '项目联系方式'
        ordering = ('sort', 'platform__sort')
        constraints = [
            models.UniqueConstraint(fields=['app', 'platform'], name='uniq_project_contact'),
        ]

    def __str__(self):
        return f'{self.app.name} - {self.platform.name}: {self.value}'

    @property
    def url(self) -> str:
        """可点击链接（平台未配模板则为空，前台按纯文本展示）"""
        return self.platform.build_url(self.value)
