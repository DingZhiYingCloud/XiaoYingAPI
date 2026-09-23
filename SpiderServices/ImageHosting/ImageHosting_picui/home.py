"""
PicUI 图床线路 - ImageHostingPicui

对接 PicUI 图片上传接口（https://picui.apifox.cn/471310694e0）:
    POST https://v2.picui.cn/api/v1/upload
    Header: Authorization: Bearer <账号Token>（不传=游客上传）
    Body(multipart/form-data): file（必需）+ 可选字段

能力: 仅上传图片（本线路不提供图片列表 / 相册等其它接口）。
鉴权: 账号 Token 由调用方（小影API 的 Token 池）提供；不传则按游客上传。

使用示例:
    line = ImageHostingPicui()

    # 1) 本地文件（使用账号 Token）
    with open("a.jpg", "rb") as f:
        result = line.upload_image(image=f, auth_token="657|xxxx")

    # 2) 指定公开/私有与储存策略
    result = line.upload_image(image=f, auth_token="657|xxxx",
                               permission="0", strategy_id="1")

    # 3) 指定过期时间
    result = line.upload_image(image=f, auth_token="657|xxxx",
                               expired_at="2026-12-31 23:59:59")
"""
import datetime
import os

import requests

from .utils import (EXPIRED_AT_FORMAT, PERMISSIONS, REQUEST_TIMEOUT,
                    SIZE_UNIT_BYTES, UPLOAD_URL)
from ..utils import get_desktop_headers, response_dict


class ImageHostingPicui:
    """PicUI 图床 - 图片上传"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def upload_image(self, image=None, image_filename=None, auth_token=None,
                     upload_token=None, permission=None, strategy_id=None,
                     album_id=None, expired_at=None) -> dict:
        """
        上传一张图片到 PicUI。

        :param image: 本地图片，支持 文件对象(file-like) / bytes / (文件名, bytes) 元组
        :param image_filename: 当 image 为 bytes 时指定文件名（可选）
        :param auth_token: 账号 Token（Authorization: Bearer），不传则按游客上传
        :param upload_token: 临时上传 Token（Body 字段 token），一般不传
        :param permission: 图片权限，"1"=公开，"0"=私有；不传则使用 PicUI 默认值
        :param strategy_id: 储存策略 ID（字符串，如 "1"）
        :param album_id: 相册 ID（字符串）
        :param expired_at: 图片过期时间，格式 yyyy-MM-dd HH:mm:ss
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息（如「上传成功」）
            - data: 成功时含 url / name / pathname / size_kb / size_bytes /
                    mimetype / extension / md5 / sha1 / links（html/bbcode/markdown 等）；
                    失败时为 None
        """
        # ---------- 1. 参数校验 ----------
        if image is None:
            return response_dict(1, "参数缺失: image(本地图片)", None)

        if permission is not None:
            permission = str(permission).strip()
            if permission not in PERMISSIONS:
                return response_dict(1, "参数值非法: permission 仅支持 0(私有)/1(公开)", None)
        if expired_at:
            expired_at = str(expired_at).strip()
            try:
                datetime.datetime.strptime(expired_at, EXPIRED_AT_FORMAT)
            except ValueError:
                return response_dict(1, "参数格式错误: expired_at 需为 yyyy-MM-dd HH:mm:ss", None)

        files, err = self._build_files(image, image_filename)
        if err:
            return response_dict(1, err, None)

        # ---------- 2. 组装请求表单（仅透传调用方显式提供的可选参数） ----------
        data = {}
        if upload_token:
            data["token"] = str(upload_token).strip()
        if permission is not None:
            data["permission"] = permission
        if strategy_id:
            data["strategy_id"] = str(strategy_id).strip()
        if album_id:
            data["album_id"] = str(album_id).strip()
        if expired_at:
            data["expired_at"] = expired_at

        headers = {"Accept": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {str(auth_token).strip()}"

        # ---------- 3. 发起上传 ----------
        try:
            resp = self.session.post(UPLOAD_URL, data=data, files=files,
                                     headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            return response_dict(1, f"上传请求失败: {e}", None)

        try:
            payload = resp.json()
        except ValueError:
            return response_dict(1, f"上传失败: 接口返回状态码 {resp.status_code}，非 JSON 响应", None)

        if resp.status_code != 200 or not payload.get("status"):
            msg = payload.get("message") or f"上传失败，状态码 {resp.status_code}"
            return response_dict(1, msg, None)

        inner = payload.get("data") or {}
        links = inner.get("links") or {}
        size_kb = inner.get("size")
        return response_dict(0, payload.get("message") or "上传成功", {
            "url": links.get("url"),
            "name": inner.get("name"),
            "pathname": inner.get("pathname"),
            "origin_name": inner.get("origin_name"),
            "size_kb": size_kb,
            "size_bytes": self._to_bytes(size_kb),
            "mimetype": inner.get("mimetype"),
            "extension": inner.get("extension"),
            "md5": inner.get("md5"),
            "sha1": inner.get("sha1"),
            "links": links,
        })

    @staticmethod
    def _to_bytes(size_kb) -> int:
        """PicUI 返回的大小单位为 KB，换算为字节"""
        try:
            return int(float(size_kb) * SIZE_UNIT_BYTES)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _build_files(image, image_filename) -> tuple:
        """把多种入参归一为 requests 的 files 结构（字段名 file）

        :return: (files 字典, None) 或 (None, 错误消息)
        """
        if hasattr(image, "read"):
            name = image_filename or os.path.basename(getattr(image, "name", "") or "") or "image"
            return {"file": (name, image)}, None
        if isinstance(image, (bytes, bytearray)):
            return {"file": (image_filename or "image", bytes(image))}, None
        if isinstance(image, (tuple, list)) and len(image) == 2:
            name, content = image
            return {"file": (name or "image", content)}, None
        return None, "参数格式错误: image 仅支持 文件对象 / bytes / (文件名, bytes) 元组"
