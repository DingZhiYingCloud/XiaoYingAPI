"""自研滑块验证码生成引擎

用 Pillow 在本地合成「背景图 + 拼图块」，不依赖第三方服务：
    new_slider_captcha() -> (background_jpeg, piece_png, answer_x, piece_y)

设计说明：
- 背景为随机渐变 + 半透明色块 / 线条 + 噪点，避免纯色导致模板匹配过于容易；
- 拼图块从同一张背景上裁剪（纹理一致），带圆角与白色描边，前端拖动它去对齐缺口；
- 缺口位置横坐标 answer_x 就是答案，只存服务端摘要，不下发；
- 只返回拼图块的纵坐标 piece_y（前端定位用），横坐标必须由用户拖出来。
"""
import colorsys
import io
import random

from PIL import Image, ImageDraw

CANVAS_WIDTH = 320
CANVAS_HEIGHT = 160
PIECE_SIZE = 52          # 拼图块边长
PIECE_RADIUS = 10        # 圆角半径
EDGE_MARGIN = 12         # 缺口与画布边缘的最小距离

# 校验容差（像素）：320 宽的画布上，8px 对正常拖动足够友好，又不会大到可以瞎猜
TOLERANCE = 8


def _random_color(saturation, value):
    """按 HSV 生成指定饱和 / 亮度区间的颜色"""
    r, g, b = colorsys.hsv_to_rgb(
        random.random(), random.uniform(*saturation), random.uniform(*value))
    return int(r * 255), int(g * 255), int(b * 255)


def _background():
    """随机渐变背景 + 柔和色块 / 线条 + 噪点"""
    left = _random_color((0.25, 0.60), (0.62, 0.86))
    right = _random_color((0.25, 0.60), (0.62, 0.86))

    image = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT))
    draw = ImageDraw.Draw(image)
    for x in range(CANVAS_WIDTH):
        ratio = x / max(1, CANVAS_WIDTH - 1)
        draw.line(
            [(x, 0), (x, CANVAS_HEIGHT)],
            fill=tuple(int(a + (b - a) * ratio) for a, b in zip(left, right)),
        )

    overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    brush = ImageDraw.Draw(overlay)
    for _ in range(8):
        radius = random.randint(14, 48)
        cx = random.randint(0, CANVAS_WIDTH)
        cy = random.randint(0, CANVAS_HEIGHT)
        brush.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=_random_color((0.2, 0.6), (0.55, 0.9)) + (random.randint(28, 64),),
        )
    for _ in range(6):
        brush.line(
            [(random.randint(0, CANVAS_WIDTH), random.randint(0, CANVAS_HEIGHT)),
             (random.randint(0, CANVAS_WIDTH), random.randint(0, CANVAS_HEIGHT))],
            fill=_random_color((0.2, 0.6), (0.55, 0.9)) + (random.randint(40, 80),),
            width=random.randint(1, 2),
        )
    image = Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')

    draw = ImageDraw.Draw(image)
    for _ in range(280):
        draw.point(
            (random.randrange(CANVAS_WIDTH), random.randrange(CANVAS_HEIGHT)),
            fill=_random_color((0.0, 0.4), (0.5, 0.85)),
        )
    return image


def _piece_mask():
    """拼图块遮罩（圆角方块）"""
    mask = Image.new('L', (PIECE_SIZE, PIECE_SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, PIECE_SIZE - 1, PIECE_SIZE - 1], radius=PIECE_RADIUS, fill=255)
    return mask


def _to_jpeg(image):
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=85, optimize=True)
    return buffer.getvalue()


def _to_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def new_slider_captcha():
    """生成一张滑块验证码

    :return: (background_jpeg, piece_png, answer_x, piece_y)
        answer_x 为缺口左上角横坐标（答案），piece_y 为纵坐标（下发前端定位）。
    """
    background = _background()
    answer_x = random.randint(PIECE_SIZE + EDGE_MARGIN,
                              CANVAS_WIDTH - PIECE_SIZE - EDGE_MARGIN)
    piece_y = random.randint(EDGE_MARGIN, CANVAS_HEIGHT - PIECE_SIZE - EDGE_MARGIN)
    box = (answer_x, piece_y, answer_x + PIECE_SIZE, piece_y + PIECE_SIZE)

    # 拼图块从「未挖洞」的背景裁剪，保证与缺口周围纹理连续
    piece = background.crop(box).convert('RGBA')
    piece.putalpha(_piece_mask())
    border = Image.new('RGBA', (PIECE_SIZE, PIECE_SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        [0, 0, PIECE_SIZE - 1, PIECE_SIZE - 1],
        radius=PIECE_RADIUS, outline=(255, 255, 255, 235), width=2)
    piece = Image.alpha_composite(piece, border)

    # 背景上挖出半透明缺口（带白色描边），指引用户对齐位置
    hole = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    hole_draw = ImageDraw.Draw(hole)
    hole_draw.rounded_rectangle(
        [answer_x, piece_y, answer_x + PIECE_SIZE - 1, piece_y + PIECE_SIZE - 1],
        radius=PIECE_RADIUS, fill=(0, 0, 0, 120),
        outline=(255, 255, 255, 160), width=1)
    background = Image.alpha_composite(background.convert('RGBA'), hole).convert('RGB')

    return _to_jpeg(background), _to_png(piece), answer_x, piece_y
