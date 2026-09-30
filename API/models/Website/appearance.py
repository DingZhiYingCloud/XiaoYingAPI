"""官网外观（单例）

超管在 `/console/appearance/` 维护官网首页与文档中心的**视觉气质**与首页头图文案：

- `preset` 决定「视觉气质」——同一套 daisyUI 主题之上再叠一层排版 / 装饰 / 卡片语言，
  取值见 PRESETS（键同时是 `<html data-feel="...">` 的值，样式在 API/static/css/input.css）；
- `hero_*` 是首页 Hero 的文案覆盖，留空即用模板内置的三语文案。

为什么是单例而不是键值表：与 `FeedbackSetting` 同一理由 —— 项目既有惯例是
「每个功能单独建表、字段即配置项」，外观配置项彼此强相关、一起读写，
单行表比零散键值更直观，也能直接用 Django 字段类型做校验。

「视觉气质」只负责**构图与装饰**，颜色一律取 daisyUI 主题变量（`--color-*`），
因此换任何一套主题（明/暗）都不会与预设打架；PRESETS 的 `theme_hint` 只是
给超管的搭配建议，不做强制绑定。
"""
from django.db import models

from API.common.base import BaseModel

# 视觉气质预设：键 = data-feel 取值 = input.css 里的样式选择器
PRESETS = {
    'aurora': {
        'label': '极光流彩',
        'desc': '柔和渐变光晕配玻璃质感卡片，现代 SaaS 的轻盈观感。',
        'theme_hint': 'light / cupcake / bumblebee',
    },
    'terminal': {
        'label': '终端极客',
        'desc': '网格底纹配等宽字体点缀与硬朗描边，开发者视角的工程感。',
        'theme_hint': 'night / dark / dracula',
    },
    'editorial': {
        'label': '编辑杂志',
        'desc': '衬线大标题配充足留白与细分隔线，内容优先的出版物质感。',
        'theme_hint': 'light / corporate / winter',
    },
    'neon': {
        'label': '霓虹赛博',
        'desc': '发光描边配扫描线与锐利几何，高对比的科技张力。',
        'theme_hint': 'dark / night / synthwave',
    },
}

DEFAULT_PRESET = 'aurora'

PRESET_CHOICES = [(key, item['label']) for key, item in PRESETS.items()]

# 文案覆盖里的占位符：{n} = 当前聚合服务数量
COUNT_PLACEHOLDER = '{n}'


class SiteAppearance(BaseModel):
    """官网外观设置（全库只有一行，pk 固定为 1）"""

    SINGLETON_PK = 1

    preset = models.CharField(
        '视觉气质', max_length=20, choices=PRESET_CHOICES, default=DEFAULT_PRESET,
        help_text='作用于官网首页与接口文档中心；颜色仍由访客选择的主题决定，二者互不冲突',
    )

    # ---------- 首页 Hero 文案覆盖（全部留空即用内置三语文案） ----------
    hero_badge = models.CharField(
        '首页徽标文案', max_length=40, blank=True,
        help_text='Hero 标题上方的小标签，留空显示「通用 API 聚合服务平台」',
    )
    hero_title = models.CharField(
        '首页主标题', max_length=60, blank=True,
        help_text='留空显示默认标题；可用 {n} 占位当前服务数量，如「一个平台，聚合 {n}+ 类能力」',
    )
    hero_subtitle = models.TextField(
        '首页副标题', blank=True,
        help_text='留空显示默认副标题；同样支持 {n} 占位',
    )

    class Meta:
        db_table = 'website_site_appearance'
        verbose_name = '官网外观'
        verbose_name_plural = '官网外观'

    def __str__(self):
        return f'官网外观（{self.get_preset_display()}）'

    def save(self, *args, **kwargs):
        """强制单例：无论从哪里保存，pk 都固定为 SINGLETON_PK"""
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'SiteAppearance':
        """取全局设置（不存在则按默认值建一行）"""
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    @property
    def preset_def(self):
        """当前预设的展示定义，未识别的取值回退到默认预设"""
        return PRESETS.get(self.preset) or PRESETS[DEFAULT_PRESET]
