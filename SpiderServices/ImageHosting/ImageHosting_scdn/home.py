"""
scdn.io 图床线路 - ImageHostingScdn

对接 https://img.scdn.io/api_docs.php 的图片上传接口:
    POST https://img.scdn.io/api/v1.php
    文件字段 image（本地文件，multipart）或 image_url（远程拉图），二者二选一。

能力: 仅上传图片（本线路暂不提供元数据查询）。
鉴权: 接口不要求 API Key。
去重: 服务端按 SHA-256 秒传，命中时 message 为「图片已存在，秒传成功！」。

使用示例:
    line = ImageHostingScdn()

    # 1) 本地文件
    with open("a.jpg", "rb") as f:
        result = line.upload_image(image=f)

    # 2) 远程图片（服务端代理拉取）
    result = line.upload_image(image_url="https://example.com/a.jpg")

    # 3) 指定输出格式 / 存储位置 / CDN 域名
    result = line.upload_image(image=f, output_format="webp",
                               storage_destination="r2", cdn_domain="img.scdn.io")

    # 4) 加密上传（普通密码）
    result = line.upload_image(image=f, password_enabled=True, image_password="secret")
"""
import os

import requests

from .utils import (OUTPUT_FORMATS, PASSWORD_TYPES, REQUEST_TIMEOUT,
                    STORAGE_DESTINATIONS, UPLOAD_URL)
from ..utils import get_desktop_headers, response_dict


class ImageHostingScdn:
    """scdn.io 图床 - 图片上传"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def upload_image(self, image=None, image_url=None, image_filename=None,
                     output_format="auto",
                     password_enabled=False, image_password=None,
                     password_type="plain", password_question=None,
                     cdn_domain=None, storage_destination=None) -> dict:
        """
        上传一张图片（或 ≤10 秒短视频）到 scdn.io。

        :param image: 本地图片，支持 文件对象(file-like) / bytes / (文件名, bytes) 元组
        :param image_url: 远程图片 URL（http/https），服务端经代理拉取；与 image 二选一
        :param image_filename: 当 image 为 bytes 时指定文件名（可选）
        :param output_format: 输出格式，见 utils.OUTPUT_FORMATS，默认 auto
        :param password_enabled: 是否启用密码保护（加密上传永不参与秒传）
        :param image_password: 访问密码/答案；password_enabled=True 时必填
        :param password_type: 密码模式 plain(默认) / qa(问答式)
        :param password_question: 问答式密码的问题文本；password_type=qa 时必填
        :param cdn_domain: 指定外链 CDN 域名，见 utils.CDN_DOMAINS；不传使用系统默认
        :param storage_destination: 存储位置 local(默认) / telegram / r2
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息（秒传命中时为「图片已存在，秒传成功！」）
            - data: 成功时含 url / filename / storage_backend / original_size /
                    compressed_size / compression_ratio / deduped / password_protected；
                    失败时为 None
        """
        # ---------- 1. 参数校验 ----------
        if image is None and not image_url:
            return response_dict(1, "参数缺失: image(本地图片) 或 image_url(远程图片URL) 二选一", None)
        if image is not None and image_url:
            return response_dict(1, "image 与 image_url 不能同时使用", None)

        if image_url is not None:
            image_url = str(image_url).strip()
            if not image_url.lower().startswith(("http://", "https://")):
                return response_dict(1, "参数格式错误: image_url 必须为 http/https 地址", None)

        output_format = (output_format or "auto").strip().lower()
        if output_format not in OUTPUT_FORMATS:
            return response_dict(1, f"参数值非法: output_format 仅支持 {'/'.join(OUTPUT_FORMATS)}", None)

        if storage_destination:
            storage_destination = storage_destination.strip().lower()
            if storage_destination not in STORAGE_DESTINATIONS:
                return response_dict(
                    1, f"参数值非法: storage_destination 仅支持 {'/'.join(STORAGE_DESTINATIONS)}", None)

        password_type = (password_type or "plain").strip().lower()
        if password_type not in PASSWORD_TYPES:
            return response_dict(1, f"参数值非法: password_type 仅支持 {'/'.join(PASSWORD_TYPES)}", None)
        password_enabled = self._to_bool(password_enabled)
        if password_enabled and not (image_password or "").strip():
            return response_dict(1, "参数缺失: password_enabled=true 时必须提供 image_password", None)
        if password_enabled and password_type == "qa" and not (password_question or "").strip():
            return response_dict(1, "参数缺失: password_type=qa 时必须提供 password_question", None)

        # ---------- 2. 组装请求表单 ----------
        data = {"outputFormat": output_format}
        files = None
        if image_url is not None:
            data["image_url"] = image_url
        else:
            files, err = self._build_files(image, image_filename)
            if err:
                return response_dict(1, err, None)

        if password_enabled:
            data["password_enabled"] = "true"
            data["image_password"] = image_password.strip()
            data["password_type"] = password_type
            if password_type == "qa":
                data["password_question"] = password_question.strip()
        if cdn_domain:
            data["cdn_domain"] = cdn_domain.strip()
        if storage_destination:
            data["storage_destination"] = storage_destination

        # ---------- 3. 发起上传 ----------
        try:
            resp = self.session.post(UPLOAD_URL, data=data, files=files, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            return response_dict(1, f"上传请求失败: {e}", None)

        try:
            payload = resp.json()
        except ValueError:
            return response_dict(1, f"上传失败: 接口返回状态码 {resp.status_code}，非 JSON 响应", None)

        if resp.status_code != 200 or not payload.get("success"):
            msg = payload.get("error") or payload.get("message") or f"上传失败，状态码 {resp.status_code}"
            return response_dict(1, msg, None)

        inner = payload.get("data") or {}
        message = payload.get("message") or inner.get("message") or "上传成功"
        return response_dict(0, message, {
            "url": payload.get("url") or inner.get("url"),
            "filename": inner.get("filename"),
            "storage_backend": inner.get("storage_backend"),
            "original_size": inner.get("original_size", inner.get("originalSize")),
            "compressed_size": inner.get("compressed_size", inner.get("compressedSize")),
            "compression_ratio": inner.get("compression_ratio"),
            "deduped": "秒传" in message,
            "password_protected": bool(password_enabled),
        })

    @staticmethod
    def _build_files(image, image_filename) -> tuple:
        """把多种入参归一为 requests 的 files 结构

        :return: (files 字典, None) 或 (None, 错误消息)
        """
        if hasattr(image, "read"):
            name = image_filename or os.path.basename(getattr(image, "name", "") or "") or "image"
            return {"image": (name, image)}, None
        if isinstance(image, (bytes, bytearray)):
            return {"image": (image_filename or "image", bytes(image))}, None
        if isinstance(image, (tuple, list)) and len(image) == 2:
            name, content = image
            return {"image": (name or "image", content)}, None
        return None, "参数格式错误: image 仅支持 文件对象 / bytes / (文件名, bytes) 元组"

    @staticmethod
    def _to_bool(value) -> bool:
        """宽松解析布尔值，支持 bool / 字符串 / 数字"""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in ("true", "1", "yes", "on")
