"""媒体文件响应：HTTP Range（206）支持

`/media/` 与「反馈附件受控下载」共用这一套解析逻辑，避免两处各写一遍 Range 处理：
Safari / 微信内置浏览器播放音视频前会先发 Range 探测，服务端不回 206 就会直接播放失败。

只支持最常见的单段 Range：`bytes=start-end` / `bytes=start-` / `bytes=-suffix`。
"""
import mimetypes
import os
import re

from django.http import HttpResponse, StreamingHttpResponse
from django.utils.http import content_disposition_header

# 单段 Range
_RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')
_RANGE_CHUNK = 64 * 1024


def parse_range(header, size):
    """解析 Range 头

    :return: (start, end) / 'invalid'（越界或语法不支持需 416）/ None（不支持，按全量返回）
    """
    match = _RANGE_RE.match((header or '').strip())
    if not match:
        return None
    start_raw, end_raw = match.group(1), match.group(2)
    if not start_raw and not end_raw:
        return None
    if start_raw:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    else:
        suffix = int(end_raw)
        if suffix == 0:
            return 'invalid'
        start = max(size - suffix, 0)
        end = size - 1
    if start >= size or start > end:
        return 'invalid'
    return start, min(end, size - 1)


def file_chunks(path, start, length):
    """按段读取文件（生成器结束时自动关闭句柄）"""
    with open(path, 'rb') as fp:
        fp.seek(start)
        remaining = length
        while remaining > 0:
            data = fp.read(min(_RANGE_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def range_response(request, full_path, filename=None):
    """有 Range 请求时返回 206 分段响应；无 Range 或无法解析时返回 None

    :param request: 用于读取 HTTP_RANGE
    :param full_path: 已确认存在的文件绝对路径
    :param filename: Content-Disposition 里的文件名，默认取 basename
    """
    header = request.META.get('HTTP_RANGE', '')
    if not header:
        return None

    size = os.path.getsize(full_path)
    content_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
    parsed = parse_range(header, size)
    if parsed is None:
        return None
    if parsed == 'invalid':
        response = HttpResponse(status=416, content_type=content_type)
        response['Content-Range'] = f'bytes */{size}'
        response['Accept-Ranges'] = 'bytes'
        return response

    start, end = parsed
    length = end - start + 1
    response = StreamingHttpResponse(file_chunks(full_path, start, length),
                                     status=206, content_type=content_type)
    response['Content-Range'] = f'bytes {start}-{end}/{size}'
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    response['Content-Disposition'] = content_disposition_header(
        False, filename or os.path.basename(full_path))
    return response
