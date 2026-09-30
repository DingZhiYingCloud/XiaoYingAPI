"""问题反馈中心 · 驳回说明图（本地绘图引擎）

AI **不参与画图**：它只输出「理由要点」文本，图由这里的纯 Pillow 引擎渲染。
版式思路参考本机 `P:\\wordpress\\xiaoyingemails\\_seo_tmp\\artlib.py`（圆角卡片 + 渐变底 +
像素级测量换行），但重写了本项目真正需要的两点：

1. **中文字体与中文换行**：artlib 只用 Segoe UI 且按空格分词，画不了中文
   （中文没有空格，按空格分词会整段溢出）。这里按**字符宽度**贪心换行，
   并在字体支持变量轴时调字重做标题层次。
2. **无进程级全局状态**：artlib 用模块级 `OUT` / `WARNINGS` 单例，多请求并发会互相污染；
   这里所有状态都是函数局部变量，线程安全。

字体来源（按顺序取第一个存在的）：
    API/static/fonts/NotoSansSC-Regular.ttf  ← 项目内置（OFL 协议，随代码入库）
    系统常见中文字体                          ← 本地开发未放内置字体时的兜底
都没有时退回 Pillow 内置位图字体（中文会显示为方块，但不会抛异常）。
"""
import os
import uuid
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ==================== 版式常量 ====================
CARD_W, CARD_H = 1200, 800
"""说明图尺寸：固定 1200×800，与参考项目的正文插图同规格"""

MARGIN = 60
CARD_RADIUS = 24
PAD_X = 72
"""卡片内左右留白"""

# 配色：生成的是静态 PNG，拿不到 daisyUI 主题变量，故直接写死一套对比度足够的中性色
COLOR_BG_TOP = (244, 245, 247)
COLOR_BG_BOTTOM = (232, 234, 238)
COLOR_CARD = (255, 255, 255)
COLOR_ACCENT = (229, 72, 77)
COLOR_TITLE = (31, 35, 40)
COLOR_MUTED = (107, 114, 128)
COLOR_LINE = (229, 231, 235)
COLOR_BODY = (55, 65, 81)

FONT_FILE = 'NotoSansSC-Regular.ttf'
_FALLBACK_FONTS = (
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/msyhl.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/System/Library/Fonts/PingFang.ttc',
)

MAX_POINT_LINES = 3
"""单条理由最多占几行（超出截断加省略号），保证整张卡不溢出版心"""


def _font_path():
    """定位可用的中文字体文件（内置优先，其次系统字体），找不到返回 None"""
    bundled = Path(settings.BASE_DIR) / 'API' / 'static' / 'fonts' / FONT_FILE
    for candidate in (str(bundled),) + _FALLBACK_FONTS:
        if os.path.exists(candidate):
            return candidate
    return None


def _apply_weight(font, weight):
    """变量字体调字重

    Noto Sans SC 的变量轴名是 `Weight`（100~900，默认 100 = Thin），所以**必须显式设成
    400**，否则正文会以极细的字重渲染。静态字体或旧版 FreeType 不支持变量轴时静默跳过。
    """
    try:
        axes = font.get_variation_axes()
    except Exception:
        return font
    if not axes:
        return font
    values = []
    for axis in axes:
        name = axis.get('name') or ''
        if isinstance(name, bytes):
            name = name.decode('utf-8', 'ignore')
        name = str(name).lower()
        if 'weight' in name or 'wght' in name:
            values.append(min(max(weight, axis.get('minimum', weight)),
                              axis.get('maximum', weight)))
        else:
            values.append(axis.get('default', 400))
    try:
        font.set_variation_by_axes(values)
    except Exception:
        pass
    return font


@lru_cache(maxsize=96)
def _font(size: int, bold: bool = False):
    """按字号取字体（带缓存；同一进程内反复画图不必重复加载近 18MB 的字体）"""
    path = _font_path()
    if path is None:
        return ImageFont.load_default()
    try:
        font = ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()
    return _apply_weight(font, 700 if bold else 400)


def _wrap(text, font, max_width):
    """按字符宽度贪心换行（中文没有空格，不能按空格分词）

    遇到显式换行符强制断行；单个字符超宽时也不丢字（`not cur` 分支保证至少放一个字符）。
    """
    lines, current = [], ''
    for ch in (text or ''):
        if ch == '\n':
            lines.append(current)
            current = ''
            continue
        if not current or font.getlength(current + ch) <= max_width:
            current += ch
        else:
            lines.append(current)
            current = ch
    lines.append(current)
    return lines


def _ellipsize(lines, max_lines):
    """超出行数上限时截断并在末行加省略号"""
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = kept[-1][:-1] + '…'
    return kept


def _gradient_background():
    """竖直渐变底（先画小图再放大，比逐像素快得多）"""
    strip = Image.new('RGB', (1, CARD_H))
    for y in range(CARD_H):
        ratio = y / max(CARD_H - 1, 1)
        strip.putpixel((0, y), tuple(
            round(COLOR_BG_TOP[i] + (COLOR_BG_BOTTOM[i] - COLOR_BG_TOP[i]) * ratio)
            for i in range(3)
        ))
    return strip.resize((CARD_W, CARD_H), Image.BILINEAR)


def _shadow(canvas, box, radius, blur=18, offset=8, alpha=26):
    """卡片投影：单独一层 RGBA 做高斯模糊后合成"""
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (box[0], box[1] + offset, box[2], box[3] + offset),
        radius=radius, fill=(15, 23, 42, alpha),
    )
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def render_reject_card(app_name, submitter, submit_time, reason, points):
    """渲染「反馈被 AI 驳回」说明图

    :param app_name:     接入项目名（页脚与会话信息）
    :param submitter:    提交者展示名（游客为「匿名用户」）
    :param submit_time:  提交时间字符串
    :param reason:       驳回理由（一句话）
    :param points:       理由要点列表（AI 给出，逐条渲染为圆点条目）
    :return: (相对 MEDIA_ROOT 的路径, 文件字节数)
    """
    bullets = [p for p in (points or []) if str(p).strip()] or [reason]
    bullets = [str(b).strip() for b in bullets if str(b).strip()]

    canvas = _gradient_background().convert('RGBA')

    card_box = (MARGIN, MARGIN, CARD_W - MARGIN, CARD_H - MARGIN)
    _shadow(canvas, card_box, CARD_RADIUS)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(card_box, radius=CARD_RADIUS, fill=COLOR_CARD)
    # 顶部强调色条（与站点公告条同一语言：一条级别色区分「这是驳回」）
    draw.rounded_rectangle(
        (card_box[0], card_box[1], card_box[2], card_box[1] + 10),
        radius=CARD_RADIUS, fill=COLOR_ACCENT,
    )

    left = card_box[0] + PAD_X
    right = card_box[2] - PAD_X
    content_w = right - left
    y = card_box[1] + 56

    # 徽标
    badge_font = _font(26, bold=True)
    badge_text = 'AI 审核未通过'
    badge_w = badge_font.getlength(badge_text) + 44
    draw.rounded_rectangle((left, y, left + badge_w, y + 52), radius=26, fill=COLOR_ACCENT)
    draw.text((left + 22, y + 11), badge_text, font=badge_font, fill=(255, 255, 255))
    y += 84

    # 标题
    draw.text((left, y), '本条反馈已被驳回', font=_font(46, bold=True), fill=COLOR_TITLE)
    y += 74

    # 会话信息
    meta = f'项目：{app_name}    提交者：{submitter}    提交时间：{submit_time}'
    draw.text((left, y), meta, font=_font(24), fill=COLOR_MUTED)
    y += 52
    draw.line((left, y, right, y), fill=COLOR_LINE, width=2)
    y += 40

    # 理由
    draw.text((left, y), '驳回理由', font=_font(30, bold=True), fill=COLOR_TITLE)
    y += 56
    reason_lines = _wrap(reason or '内容不符合平台规范', _font(28), content_w)
    for line in _ellipsize(reason_lines, 2):
        draw.text((left, y), line, font=_font(28), fill=COLOR_BODY)
        y += 44
    y += 16

    # 要点（圆点条目）
    body_font = _font(28)
    for bullet in bullets[:4]:
        lines = _ellipsize(_wrap(bullet, body_font, content_w - 34), MAX_POINT_LINES)
        draw.ellipse((left + 6, y + 12, left + 20, y + 26), fill=COLOR_ACCENT)
        for line in lines:
            draw.text((left + 34, y), line, font=body_font, fill=COLOR_BODY)
            y += 44
        y += 14

    # 页脚
    footer = '小影API · 问题反馈中心'
    draw.text((left, card_box[3] - 76), footer, font=_font(24), fill=COLOR_MUTED)

    rel_dir = 'uploads/feedback/ai'
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    rel_path = f'{rel_dir}/{uuid.uuid4().hex}.png'
    abs_path = abs_dir / Path(rel_path).name
    canvas.convert('RGB').save(abs_path, 'PNG', optimize=True)
    return rel_path, abs_path.stat().st_size
