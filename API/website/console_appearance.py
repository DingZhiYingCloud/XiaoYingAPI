"""超管控制台 · 官网外观

`/console/appearance/`：切换官网首页与接口文档中心的**视觉气质**，并覆盖首页 Hero 文案。

视觉气质（preset）只是一层构图 / 装饰 / 卡片的语言，颜色仍由访客选择的 daisyUI 主题决定，
因此这里不提供任何颜色输入 —— 预设与 35 套主题互不冲突（见 `API/models/Website/appearance.py`）。

保存走普通 POST + `action` 分发（与 `console_feedback.py` 的设置页同一套路）。
鉴权：仅 Django is_superuser（见 admin_auth.superadmin_required）。
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.models import SiteAppearance
from API.models.Website.appearance import PRESETS

from .admin_auth import notify_success, superadmin_required

# 文案覆盖的长度上限（与模型字段 max_length 保持一致）
MAX_BADGE_LEN = 40
MAX_TITLE_LEN = 60
MAX_SUBTITLE_LEN = 300


@superadmin_required
def appearance_view(request):
    if request.method == 'POST':
        return _save(request)

    appearance = SiteAppearance.get_solo()
    return render(request, 'console/appearance.html', {
        'appearance': appearance,
        # 预设列表按声明顺序给出，模板直接遍历渲染预览卡（不在模板里写死任何预设）
        'presets': [{'key': key, **item} for key, item in PRESETS.items()],
    })


def _save(request):
    appearance = SiteAppearance.get_solo()
    back = redirect('website:console_appearance')

    preset = (request.POST.get('preset') or '').strip()
    if preset not in PRESETS:
        messages.error(request, _('请选择一种视觉气质'))
        return back

    badge = (request.POST.get('hero_badge') or '').strip()
    title = (request.POST.get('hero_title') or '').strip()
    subtitle = (request.POST.get('hero_subtitle') or '').strip()
    for value, limit, label in ((badge, MAX_BADGE_LEN, _('首页徽标文案')),
                                (title, MAX_TITLE_LEN, _('首页主标题')),
                                (subtitle, MAX_SUBTITLE_LEN, _('首页副标题'))):
        if len(value) > limit:
            messages.error(request, _('%(label)s最多 %(limit)d 个字符')
                           % {'label': label, 'limit': limit})
            return back

    appearance.preset = preset
    appearance.hero_badge = badge
    appearance.hero_title = title
    appearance.hero_subtitle = subtitle
    appearance.save()
    notify_success(request, _('官网外观已保存，前台刷新即可看到新气质'))
    return back
