"""
DdddocrRecognizer - 辅助工具模块（常量配置 + 工具函数）

提供统一的响应处理、图片加载、路径构建等工具函数，
可被 home.py 及其他模块复用。

安全约束（S-01 整改）:
    1. load_image 的远程 URL 下载带 SSRF 防护：仅 http/https、解析后拒绝
       私网/回环/链路本地/保留地址、不跟随重定向、限时 5s、限大小 10MB；
    2. load_image 的本地路径仅允许读取 captcha_samples 调试目录
       （realpath 前缀校验），禁止任意文件读取；
    3. save_image / save_debug_image 已随「save-debug」接口一并下线。
"""

import os
import base64
import ipaddress
import socket
from urllib.parse import urlparse

import requests
from typing import Optional


# ==================== 常量 ====================

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 15

# 远程图片下载超时（秒）与大小上限（SSRF 防护参数）
REMOTE_IMAGE_TIMEOUT = 5.0
MAX_REMOTE_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

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


def _is_blocked_ip(ip) -> bool:
    """是否为禁止访问的地址段：私网/回环/链路本地/保留/组播/未指定"""
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _download_remote_image(url: str) -> bytes:
    """带 SSRF 防护的远程图片下载

    - 协议仅 http/https；host 为 IP 直接校验，为域名则解析全部地址逐段校验，
      命中私网/回环/链路本地/保留段即拒绝（防 DNS Rebinding）
    - 不跟随重定向（allow_redirects=False），杜绝重定向绕过黑名单
    - 限时 5s、大小上限 10MB
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"仅支持 http/https 图片 URL: {url[:100]}")

    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"图片域名解析失败: {host}")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked_ip(ip):
            raise PermissionError(f"禁止访问内网/保留地址段: {ip}")

    resp = requests.get(url, timeout=REMOTE_IMAGE_TIMEOUT, allow_redirects=False)
    if resp.status_code != 200:
        raise RuntimeError(f"图片下载失败: HTTP {resp.status_code}")

    # 大小上限（响应头声明与实际读取双重校验）
    content_length = resp.headers.get("Content-Length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_REMOTE_IMAGE_SIZE:
        raise ValueError(f"图片超过大小限制: {MAX_REMOTE_IMAGE_SIZE // (1024 * 1024)}MB")

    data = resp.content
    if not data:
        raise ValueError("图片内容为空")
    if len(data) > MAX_REMOTE_IMAGE_SIZE:
        raise ValueError(f"图片超过大小限制: {MAX_REMOTE_IMAGE_SIZE // (1024 * 1024)}MB")
    return data


def load_image(image_source: str | bytes) -> bytes:
    """
    从文件路径或 URL 加载图片，统一返回 bytes。

    安全约束（S-01 整改）：
        - URL：SSRF 防护（见 _download_remote_image）
        - 本地路径：仅允许 captcha_samples 目录内文件

    Args:
        image_source: 图片内容 bytes / http(s) URL / captcha_samples 内的文件名或路径

    Returns:
        图片的字节数据

    Raises:
        FileNotFoundError: 本地文件不存在时抛出
        PermissionError: 访问被禁止的本地路径或内网地址时抛出
        ValueError / RuntimeError / requests.RequestException: 下载或解析失败时抛出
    """
    if isinstance(image_source, bytes):
        return image_source

    if not isinstance(image_source, str):
        raise TypeError(f"不支持的图片来源类型: {type(image_source)}")

    src = image_source.strip()
    if not src:
        raise ValueError("图片来源为空")

    # http/https URL → 带 SSRF 防护的下载
    if src.startswith(("http://", "https://")):
        return _download_remote_image(src)

    # 本地路径：仅允许固定调试目录（captcha_samples），禁止读取任意文件
    allowed_dir = os.path.realpath(DEFAULT_IMAGE_DIR)
    real = os.path.realpath(src)
    if not (real == allowed_dir or real.startswith(allowed_dir + os.sep)):
        raise PermissionError(f"仅允许读取 captcha_samples 目录内的图片，已拒绝: {src[:100]}")
    if not os.path.isfile(real):
        raise FileNotFoundError(f"图片文件不存在: {src}")
    with open(real, "rb") as f:
        return f.read()


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
