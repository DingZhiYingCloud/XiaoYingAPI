"""
DdddocrRecognizer 全功能测试脚本

生成测试图片并对项目所有功能进行验证，包括：
1. OCR 识别（数字、字母、混合）
2. 目标检测（用简单几何图形模拟）
3. 滑块验证码匹配（用图形绘制模拟）
4. 批量处理
5. 颜色过滤
"""

import os
import io
import json
import random
import string
import sys

# 确保能找到 DdddocrRecognizer 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from home import DdddocrRecognizer
from utils import response_dict

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("Pillow 未安装，正在安装...")
    os.system("pip install Pillow")
    from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ==================== 测试图片生成 ====================

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "captcha_samples")
os.makedirs(SAMPLE_DIR, exist_ok=True)


def _get_font(size=36):
    """尝试获取一个可用字体，兜底用默认字体"""
    font_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/verdana.ttf",
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def _add_noise(draw, width, height):
    """添加随机噪点和干扰线"""
    for _ in range(random.randint(20, 50)):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        ))

    for _ in range(random.randint(1, 3)):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(180, 180, 180), width=1)


def generate_digit_captcha(text=None, width=120, height=40, filename="test_digits.jpg"):
    """生成数字验证码"""
    if text is None:
        text = str(random.randint(1000, 9999))

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_font(28)

    # 绘制文字，分散排列增加难度
    total_w = 0
    for c in text:
        bbox = draw.textbbox((0, 0), c, font=font)
        total_w += bbox[2] - bbox[0]

    x_start = (width - total_w) // 2
    y_start = (height - 28) // 2
    x = x_start
    for c in text:
        color = (
            random.randint(30, 200),
            random.randint(30, 200),
            random.randint(30, 200),
        )
        draw.text((x, y_start), c, fill=color, font=font)
        bbox = draw.textbbox((0, 0), c, font=font)
        x += bbox[2] - bbox[0] + 2

    _add_noise(draw, width, height)

    # 轻微模糊增加识别难度
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    filepath = os.path.join(SAMPLE_DIR, filename)
    img.save(filepath)
    print(f"  [生成] {filepath} -> 预期内容: {text}")
    return filepath, text


def generate_letter_captcha(text=None, width=160, height=40, filename="test_letters.jpg"):
    """生成字母验证码"""
    if text is None:
        text = "".join(random.choices(string.ascii_uppercase, k=4))

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_font(28)

    total_w = 0
    for c in text:
        bbox = draw.textbbox((0, 0), c, font=font)
        total_w += bbox[2] - bbox[0]

    x_start = (width - total_w) // 2
    y_start = (height - 28) // 2
    x = x_start
    for c in text:
        color = (
            random.randint(30, 200),
            random.randint(30, 200),
            random.randint(30, 200),
        )
        draw.text((x, y_start), c, fill=color, font=font)
        bbox = draw.textbbox((0, 0), c, font=font)
        x += bbox[2] - bbox[0] + 2

    _add_noise(draw, width, height)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    filepath = os.path.join(SAMPLE_DIR, filename)
    img.save(filepath)
    print(f"  [生成] {filepath} -> 预期内容: {text}")
    return filepath, text


def generate_mixed_captcha(text=None, width=180, height=40, filename="test_mixed.jpg"):
    """生成数字+字母混合验证码"""
    if text is None:
        chars = string.ascii_uppercase + string.digits
        text = "".join(random.choices(chars, k=4))

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_font(28)

    total_w = 0
    for c in text:
        bbox = draw.textbbox((0, 0), c, font=font)
        total_w += bbox[2] - bbox[0]

    x_start = (width - total_w) // 2
    y_start = (height - 28) // 2
    x = x_start
    for c in text:
        color = (
            random.randint(30, 200),
            random.randint(30, 200),
            random.randint(30, 200),
        )
        draw.text((x, y_start), c, fill=color, font=font)
        bbox = draw.textbbox((0, 0), c, font=font)
        x += bbox[2] - bbox[0] + 2

    _add_noise(draw, width, height)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    filepath = os.path.join(SAMPLE_DIR, filename)
    img.save(filepath)
    print(f"  [生成] {filepath} -> 预期内容: {text}")
    return filepath, text


def generate_color_captcha(filename="test_colors.jpg"):
    """生成特定颜色文字验证码（用于测试颜色过滤）"""
    text = "1234"
    width, height = 140, 40

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_font(28)

    # 红色文字
    draw.text((10, 5), "12", fill=(255, 50, 50), font=font)
    # 蓝色文字
    draw.text((70, 5), "34", fill=(50, 50, 255), font=font)

    filepath = os.path.join(SAMPLE_DIR, filename)
    img.save(filepath)
    print(f"  [生成] {filepath} -> 红蓝双色: {text}")
    return filepath, text


def generate_slider_test_images(filename_bg="test_slider_bg.jpg", filename_slide="test_slider_slide.jpg"):
    """
    生成模拟滑块验证码的测试图片。
    bg: 灰色背景上有一个矩形缺口
    slide: 矩形滑块（与缺口相同尺寸）
    """
    # 背景图尺寸
    bg_w, bg_h = 300, 150
    target_x = 150  # 缺口位置
    gap_w, gap_h = 40, 40

    # 生成背景图（浅灰色，带一个深色矩形缺口）
    bg = Image.new("RGB", (bg_w, bg_h), (220, 220, 220))
    draw_bg = ImageDraw.Draw(bg)
    # 在目标位置画一个黑色矩形作为"缺口"
    draw_bg.rectangle(
        [target_x, (bg_h - gap_h) // 2, target_x + gap_w, (bg_h + gap_h) // 2],
        fill=(200, 200, 200),  # 稍微不同颜色表示缺口
        outline=(100, 100, 100),
    )
    bg_path = os.path.join(SAMPLE_DIR, filename_bg)
    bg.save(bg_path)
    print(f"  [生成] {bg_path} (预期滑块x位置: {target_x})")

    # 生成滑块图（深灰色矩形，与缺口大小一致）
    slide = Image.new("RGB", (gap_w, gap_h), (120, 120, 120))
    draw_slide = ImageDraw.Draw(slide)
    draw_slide.rectangle(
        [0, 0, gap_w - 1, gap_h - 1],
        fill=(120, 120, 120),
        outline=(80, 80, 80),
    )
    slide_path = os.path.join(SAMPLE_DIR, filename_slide)
    slide.save(slide_path)
    print(f"  [生成] {slide_path}")

    return bg_path, slide_path, target_x


def generate_detection_image(filename="test_detection.jpg"):
    """生成目标检测测试图片（白色背景上的多个彩色矩形）"""
    width, height = 200, 150
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 画三个不同位置和大小的矩形
    boxes = [
        ((20, 20), (60, 60), (255, 0, 0)),     # 红色
        ((100, 30), (150, 80), (0, 255, 0)),   # 绿色
        ((50, 90), (120, 130), (0, 0, 255)),   # 蓝色
    ]
    for (x1, y1), (x2, y2), color in boxes:
        draw.rectangle([x1, y1, x2, y2], fill=color, outline=(0, 0, 0))

    filepath = os.path.join(SAMPLE_DIR, filename)
    img.save(filepath)
    print(f"  [生成] {filepath} (含3个矩形)")
    return filepath


# ==================== 测试执行 ====================


def test_ocr():
    """测试 OCR 识别功能"""
    print("\n" + "=" * 60)
    print("测试1: OCR 文字识别")
    print("=" * 60)

    recognizer = DdddocrRecognizer(show_ad=False)

    # 1.1 数字验证码
    print("\n--- 1.1 数字验证码 ---")
    fp, expected = generate_digit_captcha()
    result = recognizer.ocr(fp)
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 识别: {result['data']} | 预期: {expected}")

    # 1.2 字母验证码
    print("\n--- 1.2 字母验证码 ---")
    fp, expected = generate_letter_captcha()
    result = recognizer.ocr(fp)
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 识别: {result['data']} | 预期: {expected}")

    # 1.3 混合验证码
    print("\n--- 1.3 混合验证码 ---")
    fp, expected = generate_mixed_captcha()
    result = recognizer.ocr(fp)
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 识别: {result['data']} | 预期: {expected}")

    # 1.4 限定数字范围
    print("\n--- 1.4 限定数字范围 ---")
    recognizer.set_ranges(0)
    fp, expected = generate_digit_captcha(text="5678")
    result = recognizer.ocr(fp)
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 数字模式: {result['data']} | 预期: {expected}")
    recognizer.set_ranges(7)  # 恢复默认

    # 1.5 概率输出
    print("\n--- 1.5 概率输出 ---")
    result = recognizer.ocr(fp, probability=True)
    status = "✓" if result["code"] == 0 and "probability" in str(type(result["data"])) else "✗"
    if isinstance(result["data"], dict) and "text" in result["data"]:
        print(f"  {status} 概率模式文本: {result['data']['text']}")
    else:
        print(f"  {status} 概率模式结果: {result}")

    # 1.6 颜色过滤
    print("\n--- 1.6 颜色过滤 ---")
    fp, expected = generate_color_captcha()
    result = recognizer.ocr(fp, colors=["red", "blue"])
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 颜色过滤: {result['data']} | 预期: {expected}")

    # 1.7 URL 读取测试
    print("\n--- 1.7 URL 读取测试 ---")
    # 使用一个在线的简单验证码图片
    url = "https://httpbin.org/image/jpeg"
    try:
        result = recognizer.ocr(url)
        status = "✓" if result["code"] == 0 else "✗"
        print(f"  {status} URL识别: {result}")
    except Exception as e:
        print(f"  - URL测试跳过（网络可能不可达: {e}）")

    # 1.8 bytes 输入测试
    print("\n--- 1.8 bytes 输入测试 ---")
    with open(fp, "rb") as f:
        img_bytes = f.read()
    result = recognizer.ocr(img_bytes)
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} bytes输入: {result['data']}")

    return recognizer


def test_detection():
    """测试目标检测功能"""
    print("\n" + "=" * 60)
    print("测试2: 目标检测")
    print("=" * 60)

    det_recognizer = DdddocrRecognizer(ocr=False, det=True, show_ad=False)
    fp = generate_detection_image()
    result = det_recognizer.detect(fp)
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 检测结果: {len(result.get('data', []))} 个目标")
    for i, box in enumerate(result.get("data", []), 1):
        print(f"    目标{i}: {box}")


def test_slider():
    """测试滑块验证码匹配"""
    print("\n" + "=" * 60)
    print("测试3: 滑块验证码匹配")
    print("=" * 60)

    slider_recognizer = DdddocrRecognizer(ocr=False, det=False, show_ad=False)
    bg_path, slide_path, expected_x = generate_slider_test_images()

    # 3.1 slide_match（算法1）
    print("\n--- 3.1 边缘匹配法 (slide_match) ---")
    result = slider_recognizer.slide_match(slide_path, bg_path)
    if result["code"] == 0:
        actual_x = (result.get("data") or {}).get("target_x", 0)
        status = "✓" if abs(actual_x - expected_x) < 20 else "△"
        print(f"  {status} 匹配位置: x={actual_x} | 预期: x≈{expected_x}")
    else:
        print(f"  ✗ 匹配失败: {result['message']}")

    # 3.2 slide_comparison（算法2）
    print("\n--- 3.2 图像差异比较法 (slide_comparison) ---")
    result = slider_recognizer.slide_comparison(slide_path, bg_path)
    if result["code"] == 0:
        actual_x = (result.get("data") or {}).get("target_x", 0)
        status = "✓" if abs(actual_x - expected_x) < 20 else "△"
        print(f"  {status} 匹配位置: x={actual_x} | 预期: x≈{expected_x}")
    else:
        print(f"  ✗ 匹配失败: {result['message']}")


def test_batch(recognizer):
    """测试批量处理"""
    print("\n" + "=" * 60)
    print("测试4: 批量 OCR 识别")
    print("=" * 60)

    # 再生成几张测试图片确保够用
    generate_digit_captcha(text="2024")
    generate_digit_captcha(text="8888")

    result = recognizer.batch_ocr(SAMPLE_DIR, pattern="*.jpg;*.png")
    status = "✓" if result["code"] == 0 else "✗"
    print(f"  {status} 批量结果: ")
    data = result.get("data", {})
    if data:
        print(f"    总数: {data.get('total', 0)}, 成功: {data.get('success', 0)}, 失败: {data.get('failed', 0)}")
        for item in data.get("results", [])[:5]:
            r = item.get("result", item.get("error", "?"))
            if isinstance(r, dict):
                r = r.get("text", str(r))
            print(f"    - {item['filename']}: {r}")


def test_save_debug(recognizer):
    """测试保存调试图片"""
    print("\n" + "=" * 60)
    print("测试5: 保存调试图片")
    print("=" * 60)

    fp = os.path.join(SAMPLE_DIR, "test_digits.jpg")
    result = recognizer.save_debug_image(fp, filename="debug_test.jpg")
    status = "✓" if result["code"] == 0 else "✗"
    if result["code"] == 0:
        print(f"  {status} 保存至: {result['data']['filepath']}")
    else:
        print(f"  {status} 失败: {result['message']}")


def test_error_handling():
    """测试异常处理"""
    print("\n" + "=" * 60)
    print("测试6: 异常处理")
    print("=" * 60)

    recognizer = DdddocrRecognizer(show_ad=False)

    # 6.1 不存在的文件
    print("\n--- 6.1 不存在的文件 ---")
    result = recognizer.ocr("nonexistent_file.jpg")
    status = "✓" if result["code"] == 1 else "✗"
    print(f"  {status} 错误消息: {result['message']}")

    # 6.2 空的 bytes
    print("\n--- 6.2 空的 bytes ---")
    result = recognizer.ocr(b"")
    status = "✓" if result["code"] == 1 else "✗"
    print(f"  {status} 错误消息: {result['message']}")

    # 6.3 不存在的目录批量识别
    print("\n--- 6.3 不存在的目录批量识别 ---")
    result = recognizer.batch_ocr("C:/nonexistent_dir_12345")
    status = "✓" if result["code"] == 1 else "✗"
    print(f"  {status} 错误消息: {result['message']}")

    # 6.4 检测模式未启用时调用 detect
    print("\n--- 6.4 检测模式未启用时调用 detect ---")
    try:
        recognizer.detect("test.jpg")
        print("  ✗ 应该抛出 ValueError 但未抛出")
    except ValueError as e:
        print(f"  ✓ 正确抛出 ValueError: {e}")


# ==================== 主入口 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("DdddocrRecognizer 全功能测试")
    print("=" * 60)
    print(f"测试图片目录: {SAMPLE_DIR}")

    # 清理旧的测试图片（保留目录）
    for f in os.listdir(SAMPLE_DIR):
        fp = os.path.join(SAMPLE_DIR, f)
        if os.path.isfile(fp) and f.endswith((".jpg", ".png")):
            os.remove(fp)

    try:
        # 执行测试
        recognizer = test_ocr()
        test_detection()
        test_slider()
        test_batch(recognizer)
        test_save_debug(recognizer)
        test_error_handling()

        print("\n" + "=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        print(f"\n生成的测试图片保存在: {SAMPLE_DIR}")
        files = [f for f in os.listdir(SAMPLE_DIR) if f.endswith((".jpg", ".png"))]
        for f in sorted(files):
            print(f"  - {f}")

    except Exception as e:
        print(f"\n✗ 测试过程出现异常: {e}")
        import traceback
        traceback.print_exc()
