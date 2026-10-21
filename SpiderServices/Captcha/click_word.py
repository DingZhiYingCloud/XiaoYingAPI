"""自研汉字点选验证码生成引擎

用 Pillow + 项目内置中文字体绘制：
    new_click_word_captcha() -> (png_bytes, targets)

targets 为「需要依次点击的目标字」列表（含每个字的中心坐标与命中半径），
只落库、不下发；前端只拿目标字文本与整张图片。

设计说明：
- 3×3 网格中随机取 8 个位置放候选汉字，每格加随机偏移 / 旋转 / 深色随机色；
- 从 8 个字里随机抽 2-4 个作为目标（顺序随机），提示用户依次点击；
- 背景为浅色渐变 + 噪点 + 干扰线，避免干扰元素盖住笔画；
- 字体优先用 `API/static/fonts/NotoSansSC-Regular.ttf`（变量字体，需把 Weight 轴设为 400）。
"""
import colorsys
import io
import os
import random
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

CANVAS_WIDTH = 360
CANVAS_HEIGHT = 200

COLUMNS = 3
ROWS = 3
CELL_WIDTH = CANVAS_WIDTH // COLUMNS
CELL_HEIGHT = CANVAS_HEIGHT // ROWS

FONT_SIZE = 36
HIT_RADIUS = 26          # 点击命中半径（画布像素）
TOTAL_CHARS = 8          # 候选字数（3×3 留一格空位）
MIN_TARGETS = 2
MAX_TARGETS = 4

# 常用、笔画清晰且彼此不易混淆的汉字
CHAR_POOL = '山水云风花月日雨石木田火土金光天海林星春夏秋冬江河湖浪沙草树鸟鱼'

FONT_FILE = 'NotoSansSC-Regular.ttf'
_FALLBACK_FONTS = (
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/System/Library/Fonts/PingFang.ttc',
)


@lru_cache(maxsize=4)
def _font(size):
    """加载中文字体（内置优先，其次系统字体）；变量字体把 Weight 轴设成 400"""
    bundled = Path(settings.BASE_DIR) / 'API' / 'static' / 'fonts' / FONT_FILE
    for candidate in (str(bundled),) + _FALLBACK_FONTS:
        if not os.path.exists(candidate):
            continue
        try:
            font = ImageFont.truetype(candidate, size)
        except OSError:
            continue
        try:
            axes = font.get_variation_axes()
            if axes:
                values = []
                for axis in axes:
                    name = axis.get('name') or ''
                    if isinstance(name, bytes):
                        name = name.decode('utf-8', 'ignore')
                    name = str(name).lower()
                    values.append(400 if ('weight' in name or 'wght' in name)
                                  else axis.get('default', 400))
                font.set_variation_by_axes(values)
        except Exception:
            pass
        return font
    return ImageFont.load_default(size=size)


def _random_dark_color():
    r, g, b = colorsys.hsv_to_rgb(
        random.random(), random.uniform(0.5, 0.85), random.uniform(0.25, 0.45))
    return int(r * 255), int(g * 255), int(b * 255)


def _random_light_color():
    return (random.randint(180, 230), random.randint(180, 230), random.randint(180, 230))


def _background():
    """浅色渐变背景 + 噪点 + 干扰线（都不压在字上）"""
    left = (random.randint(242, 252), random.randint(244, 253), random.randint(246, 255))
    right = (random.randint(238, 250), random.randint(242, 252), random.randint(244, 255))
    image = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT))
    draw = ImageDraw.Draw(image)
    for x in range(CANVAS_WIDTH):
        ratio = x / max(1, CANVAS_WIDTH - 1)
        draw.line([(x, 0), (x, CANVAS_HEIGHT)],
                  fill=tuple(int(a + (b - a) * ratio) for a, b in zip(left, right)))

    for _ in range(3):
        draw.line(
            [(random.randint(0, CANVAS_WIDTH), random.randint(0, CANVAS_HEIGHT)),
             (random.randint(0, CANVAS_WIDTH), random.randint(0, CANVAS_HEIGHT))],
            fill=_random_light_color(), width=1)
    for _ in range(320):
        draw.point((random.randrange(CANVAS_WIDTH), random.randrange(CANVAS_HEIGHT)),
                   fill=_random_light_color())
    return image


def _draw_char(canvas, char, center_x, center_y):
    """把单个汉字以随机颜色 / 随机角度画到画布中心"""
    layer_size = int(FONT_SIZE * 2.2)
    layer = Image.new('RGBA', (layer_size, layer_size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(
        (layer_size / 2, layer_size / 2), char,
        font=_font(FONT_SIZE), anchor='mm', fill=_random_dark_color())
    layer = layer.rotate(random.uniform(-12, 12), resample=Image.BICUBIC)
    canvas.paste(layer, (int(center_x - layer_size / 2), int(center_y - layer_size / 2)), layer)


def new_click_word_captcha():
    """生成一张汉字点选验证码

    :return: (png_bytes, targets)
        targets = [{'char': '山', 'x': 120, 'y': 66, 'r': 26}, ...]，顺序即点击顺序。
    """
    chars = random.sample(CHAR_POOL, TOTAL_CHARS)

    # 3×3 网格里随机留一格空位
    cells = random.sample(range(COLUMNS * ROWS), TOTAL_CHARS)
    canvas = _background()
    placed = []
    for char, cell in zip(chars, cells):
        row, column = divmod(cell, COLUMNS)
        center_x = column * CELL_WIDTH + CELL_WIDTH / 2 + random.randint(-6, 6)
        center_y = row * CELL_HEIGHT + CELL_HEIGHT / 2 + random.randint(-5, 5)
        _draw_char(canvas, char, center_x, center_y)
        placed.append({'char': char, 'x': round(center_x, 1), 'y': round(center_y, 1)})

    target_count = random.randint(MIN_TARGETS, MAX_TARGETS)
    targets = random.sample(placed, target_count)
    for target in targets:
        target['r'] = HIT_RADIUS

    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue(), targets
