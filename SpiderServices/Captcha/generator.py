"""自研图形验证码生成引擎

用 Pillow 直接绘制 PNG 图片，不依赖任何第三方验证码服务：
    new_char_captcha(length)  - 字符图片验证码（数字 + 大写字母，剔除易混淆字符）
    new_arithmetic_captcha()  - 算术图片验证码（加减法，结果非负）

统一返回 (png_bytes, answer) 二元组：
    png_bytes - PNG 图片二进制（调用方自行 base64 编码后下发前端）
    answer    - 标准答案字符串（校验时由调用方做大小写归一后比对）

设计说明：
- 字体使用 Pillow 内置默认字体（ImageFont.load_default(size=...)），不引入外部字体文件；
- 逐字符随机颜色 / 随机旋转角度 / 随机纵向偏移，叠加干扰线与噪点，提高 OCR 识别成本；
- 无状态：每次调用独立生成，可安全并发。
"""
import colorsys
import io
import math
import random

from PIL import Image, ImageDraw, ImageFont

# 字符池：剔除易混淆字符（0/O、1/I/L 等），降低人工识别成本
CHAR_POOL = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'

# 画布尺寸与外观参数
IMAGE_WIDTH = 180
IMAGE_HEIGHT = 64

# 字符验证码长度范围（越界自动收敛）
DEFAULT_LENGTH = 4
MIN_LENGTH = 4
MAX_LENGTH = 6

# 最大字号（按字符数自动收缩，避免多字符时重叠）
MAX_FONT_SIZE = 46

# 干扰线 / 噪点数量（浅色，不盖住字符）
LINE_COUNT = 4
DOT_COUNT = 70

# 字符旋转角度范围
ROTATE_DEGREE = 28
# 字符纵向随机偏移像素
OFFSET_Y = 5

# 正弦扭曲参数：按纵向错位打散规整笔画（抗 OCR，肉眼仍可辨认）
WARP_AMPLITUDE = 4
WARP_WAVELENGTH = 110


def _random_dark_color():
    """随机深色前景：固定低亮度、较高饱和度

    之前 RGB 三通道各自独立随机，容易出现发灰、对比度不稳定的颜色；
    改用 HSV 控制亮度上限，保证每张图的字符都足够清晰。
    """
    hue = random.random()
    r, g, b = colorsys.hsv_to_rgb(
        hue, random.uniform(0.55, 0.85), random.uniform(0.30, 0.50))
    return int(r * 255), int(g * 255), int(b * 255)


def _random_light_color():
    """随机浅色（干扰元素用，避免盖住字符）"""
    return (random.randint(165, 220), random.randint(165, 220), random.randint(165, 220))


def _random_background():
    """随机浅色背景：固定底色容易被 OCR 按固定阈值二值化"""
    return (random.randint(240, 252), random.randint(242, 253), random.randint(244, 255))


def _auto_font_size(text):
    """按字符数自动计算字号：字号不超过单格宽度的 1.15 倍，避免多字符时相互压字"""
    cell_width = IMAGE_WIDTH / len(text)
    return min(MAX_FONT_SIZE, int(cell_width * 1.15))


def _draw_char(canvas, char, center_x, center_y, font_size):
    """把单个字符以随机颜色、随机角度绘制到画布指定中心位置"""
    layer_size = int(font_size * 2.2)
    layer = Image.new('RGBA', (layer_size, layer_size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(
        (layer_size / 2, layer_size / 2), char,
        font=ImageFont.load_default(size=font_size),
        anchor='mm', fill=_random_dark_color(),
    )
    layer = layer.rotate(random.uniform(-ROTATE_DEGREE, ROTATE_DEGREE), resample=Image.BICUBIC)
    canvas.paste(layer, (int(center_x - layer_size / 2), int(center_y - layer_size / 2)), layer)


def _warp(layer):
    """按正弦曲线对整层做逐列纵向错位，打散字符的规整笔画（抗 OCR）"""
    warped = Image.new('RGBA', layer.size, (0, 0, 0, 0))
    for x in range(layer.width):
        offset = int(WARP_AMPLITUDE * math.sin(2 * math.pi * x / WARP_WAVELENGTH))
        column = layer.crop((x, 0, x + 1, layer.height))
        warped.paste(column, (x, -offset))
    return warped


def _render(text):
    """把 text 渲染为带干扰的 PNG 图片字节"""
    # 1. 先在透明层上绘制字符（随机颜色 / 角度 / 纵向偏移）
    text_layer = Image.new('RGBA', (IMAGE_WIDTH, IMAGE_HEIGHT), (0, 0, 0, 0))
    font_size = _auto_font_size(text)
    cell_width = IMAGE_WIDTH / len(text)
    for index, char in enumerate(text):
        _draw_char(
            text_layer, char,
            center_x=cell_width * index + cell_width / 2,
            center_y=IMAGE_HEIGHT / 2 + random.randint(-OFFSET_Y, OFFSET_Y),
            font_size=font_size,
        )

    # 2. 字符层整体做正弦扭曲，破坏规整字形
    canvas = Image.new('RGB', (IMAGE_WIDTH, IMAGE_HEIGHT), _random_background())
    draw = ImageDraw.Draw(canvas)

    # 3. 干扰线（画在字符下层）
    for _ in range(LINE_COUNT):
        draw.line(
            [(random.randint(0, IMAGE_WIDTH), random.randint(0, IMAGE_HEIGHT)),
             (random.randint(0, IMAGE_WIDTH), random.randint(0, IMAGE_HEIGHT))],
            fill=_random_light_color(),
            width=1,
        )

    # 4. 合成扭曲后的字符层
    warped = _warp(text_layer)
    canvas.paste(warped, (0, 0), warped)

    # 5. 噪点（画在字符上层，少量不影响识别）
    for _ in range(DOT_COUNT):
        draw.point(
            (random.randint(0, IMAGE_WIDTH - 1), random.randint(0, IMAGE_HEIGHT - 1)),
            fill=_random_light_color(),
        )

    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG')
    return buffer.getvalue()


def new_char_captcha(length=DEFAULT_LENGTH):
    """生成字符图片验证码

    :param length: 字符个数，越界自动收敛到 [MIN_LENGTH, MAX_LENGTH]
    :return: (png_bytes, answer)  answer 为大小写已归一的字符答案
    """
    length = max(MIN_LENGTH, min(MAX_LENGTH, int(length)))
    answer = ''.join(random.choice(CHAR_POOL) for _ in range(length))
    return _render(answer), answer


def new_arithmetic_captcha():
    """生成算术图片验证码（加减法，减法保证被减数不小于减数、结果非负）

    :return: (png_bytes, answer)  answer 为计算结果的字符串，如 '37'
    """
    left, right = random.randint(1, 50), random.randint(1, 50)
    if random.random() < 0.5:
        text, answer = f'{left}+{right}=?', str(left + right)
    else:
        big, small = max(left, right), min(left, right)
        text, answer = f'{big}-{small}=?', str(big - small)
    return _render(text), answer
