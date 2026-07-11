"""
DdddocrRecognizer - 辅助工具模块（常量配置 + 工具函数）

提供统一的响应处理、图片加载/保存、路径构建等工具函数，
可被 home.py 及其他模块复用。
"""

import os
import base64
import requests
from typing import Optional


# ==================== 常量 ====================

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 15

# 常见图片 MIME 类型与扩展名映射
IMAGE_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}

# 默认保存图片的目录（相对当前文件所在目录）
DEFAULT_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "captcha_samples")


# ==================== 工具函数 ====================


def response_dict(code: int = 0, message: str = "", data: dict | list = None) -> dict:
    """统一的响应字典返回"""
    return {"code": code, "message": message, "data": data}


def load_image(image_source: str | bytes) -> bytes:
    """
    从文件路径或 URL 加载图片，统一返回 bytes。

    Args:
        image_source: 图片文件路径（本地路径）或 URL 或 bytes 对象

    Returns:
        图片的字节数据

    Raises:
        FileNotFoundError: 本地文件不存在时抛出
        requests.RequestException: 下载失败时抛出
        TypeError: 输入类型不支持时抛出
    """
    if isinstance(image_source, bytes):
        return image_source

    if not isinstance(image_source, str):
        raise TypeError(f"不支持的图片来源类型: {type(image_source)}")

    # 判断是 URL 还是本地路径
    if image_source.startswith(("http://", "https://")):
        resp = requests.get(image_source, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.content
    else:
        if not os.path.exists(image_source):
            raise FileNotFoundError(f"图片文件不存在: {image_source}")
        with open(image_source, "rb") as f:
            return f.read()


def save_image(image_bytes: bytes, save_dir: str = None, filename: str = None) -> str:
    """
    将图片字节保存到本地文件。

    Args:
        image_bytes: 图片字节数据
        save_dir: 保存目录，默认使用 DEFAULT_IMAGE_DIR
        filename: 文件名，不传则自动生成

    Returns:
        保存后的文件绝对路径
    """
    if save_dir is None:
        save_dir = DEFAULT_IMAGE_DIR
    os.makedirs(save_dir, exist_ok=True)

    if filename is None:
        # 自动生成文件名：使用图片字节的 base64 前 16 位作为标识
        import hashlib
        name_hash = hashlib.md5(image_bytes).hexdigest()[:16]
        filename = f"captcha_{name_hash}.jpg"

    filepath = os.path.join(save_dir, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    return filepath


def base64_to_image(base64_str: str) -> bytes:
    """
    将 data:image/xxx;base64,... 格式的字符串解码为图片字节码。

    Args:
        base64_str: 以 data:image/xxx;base64, 开头的 base64 编码字符串

    Returns:
        解码后的图片字节码；失败时返回 b""

    Raises:
        ValueError: 输入字符串格式不正确时抛出
    """
    try:
        if not base64_str:
            raise ValueError("base64字符串不能为空")

        prefixes = [
            "data:image/jpg;base64,",
            "data:image/jpeg;base64,",
            "data:image/png;base64,",
            "data:image/gif;base64,",
            "data:image/webp;base64,",
        ]

        content_start = -1
        for prefix in prefixes:
            if base64_str.startswith(prefix):
                content_start = len(prefix)
                break

        if content_start == -1:
            raise ValueError(
                "base64字符串格式不正确，必须以前缀开头:\n" + "\n".join(prefixes)
            )

        base64_content = base64_str[content_start:]

        # 补全 Base64 填充字符
        missing_padding = len(base64_content) % 4
        if missing_padding:
            base64_content += "=" * (4 - missing_padding)

        return base64.b64decode(base64_content)

    except (ValueError, Exception) as e:
        print(f"base64解码失败: {e}")
        return b""
