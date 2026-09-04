"""文件上传工具模块

处理文件保存、类型校验、大小限制、唯一文件名生成等逻辑。

安全约束（S-02 整改）:
    1. image 类型移除 svg（svg 可内嵌脚本，禁止直接上传直服）；
    2. file 类型从"无扩展名限制"收敛为白名单（zip/pdf/docx/xlsx/txt），
       拒绝 html/htm/svg/xml/js/mht 等可执行/可渲染类型；
    3. 新增文件头(magic bytes)校验，防止"HTML 改名 .jpg"等仅靠扩展名绕过。
"""
import os
import uuid
from datetime import datetime
from django.conf import settings


# 文件头(magic bytes)签名表：扩展名 -> 校验片段
# 每个条目为 (offset, bytes) 或 [(offset, bytes), ...]（任一命中即通过）
_MAGIC_SIGNATURES = {
    'jpg': [(0, b'\xff\xd8\xff')],
    'jpeg': [(0, b'\xff\xd8\xff')],
    'png': [(0, b'\x89PNG')],
    'gif': [(0, b'GIF8')],
    'bmp': [(0, b'BM')],
    'webp': [(0, b'RIFF'), (8, b'WEBP')],
    'ico': [(0, b'\x00\x00\x01\x00')],
    'tiff': [(0, b'II*\x00'), (0, b'MM\x00*')],
    # docx/xlsx 本质为 zip 容器，与 zip 同用 PK 头校验
    'zip': [(0, b'PK\x03\x04'), (0, b'PK\x05\x06')],
    'docx': [(0, b'PK\x03\x04'), (0, b'PK\x05\x06')],
    'xlsx': [(0, b'PK\x03\x04'), (0, b'PK\x05\x06')],
    'pdf': [(0, b'%PDF')],
}

# 无固定魔数的类型（txt）：仅做内容前缀黑名单，拒绝 HTML/XML/SVG 等可渲染内容
_TXT_FORBIDDEN_PREFIX = (
    b'<html', b'<!doctype', b'<head', b'<body', b'<?xml', b'<svg',
    b'<script', b'<iframe', b'<style', b'<!entity', b'<a ',
)

# 读取文件头用于魔数校验的字节数
_MAGIC_HEAD_SIZE = 512


class FileUploader:
    """文件上传处理器

    支持三种上传类型: image(图片) / video(视频) / file(通用文件)
    每种类型对应独立存储目录，并有独立大小限制。
    """

    TYPE_CONFIG = {
        'image': {
            'dir': 'images',
            'max_size': 20 * 1024 * 1024,
            # 注：svg 已移除（S-02），可内嵌脚本且 /media/ 直服时存在 XSS 风险
            'allowed_ext': {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'ico', 'tiff'},
        },
        'video': {
            'dir': 'videos',
            'max_size': 100 * 1024 * 1024,
            'allowed_ext': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'm4v', '3gp'},
        },
        'file': {
            'dir': 'files',
            'max_size': 100 * 1024 * 1024,
            # S-02: 从"无扩展名限制"收敛为安全白名单，拒绝可执行/可渲染类型
            'allowed_ext': {'zip', 'pdf', 'docx', 'xlsx', 'txt'},
        },
    }

    @classmethod
    def _get_ext(cls, filename):
        """获取文件扩展名（小写，不带点）。"""
        ext = os.path.splitext(filename)[1].lower()
        return ext[1:] if ext.startswith('.') else ext

    @classmethod
    def _generate_unique_filename(cls, original_filename):
        """生成唯一文件名，格式: {uuid}_{timestamp}.{ext}

        使用 uuid4 + 时间戳双重保证唯一性，避免文件覆盖。
        """
        ext = cls._get_ext(original_filename)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        return f"{unique_id}_{timestamp}.{ext}" if ext else f"{unique_id}_{timestamp}"

    @classmethod
    def _check_magic(cls, ext, head):
        """魔数校验：文件内容开头是否与扩展名声称的类型一致。

        :param ext: 小写扩展名
        :param head: 文件头字节
        :return: (ok, reason) - ok=True 通过；ok=False 时 reason 为拒绝原因
        """
        # 无扩展名需求时已在上层白名单拦截，这里只处理已知类型
        if ext == 'txt':
            stripped = head.lstrip(b'\xef\xbb\xbf \t\r\n')  # 容忍 UTF-8 BOM 与空白
            lowered = stripped.lower()
            for prefix in _TXT_FORBIDDEN_PREFIX:
                if lowered.startswith(prefix):
                    return False, '文本文件内容疑似 HTML/XML/SVG 等可渲染内容，已拒绝'
            return True, ''

        signatures = _MAGIC_SIGNATURES.get(ext)
        if not signatures:
            return True, ''

        for offset, magic in signatures:
            if head[offset:offset + len(magic)] == magic:
                return True, ''
        return False, f'文件内容与扩展名 .{ext} 不符（魔数校验失败），已拒绝'

    @classmethod
    def save_file(cls, upload_type, uploaded_file):
        """
        保存上传的文件。

        :param upload_type: 上传类型，'image' / 'video' / 'file'
        :param uploaded_file: Django UploadedFile 对象 (request.FILES 中的文件)
        :return: tuple[bool, dict|str]
            - 成功: (True, {
                'filename': 存储后的文件名,
                'original_name': 原始文件名,
                'size': 文件大小(字节),
                'ext': 扩展名,
                'type': 上传类型,
                'relative_path': 相对 media 目录的路径,
                'url': 访问 URL,
              })
            - 失败: (False, 错误信息字符串)
        """
        if upload_type not in cls.TYPE_CONFIG:
            return False, f'不支持的上传类型: {upload_type}'

        config = cls.TYPE_CONFIG[upload_type]

        original_name = uploaded_file.name or ''
        ext = cls._get_ext(original_name)
        file_size = uploaded_file.size

        if not original_name:
            return False, '文件名为空'

        if file_size == 0:
            return False, '文件大小为0'

        if file_size > config['max_size']:
            max_mb = config['max_size'] // (1024 * 1024)
            return False, f'文件大小超过限制，最大允许 {max_mb}MB'

        if config['allowed_ext'] is not None and ext not in config['allowed_ext']:
            allowed = ', '.join(sorted(config['allowed_ext']))
            return False, f'不支持的文件扩展名 .{ext}，允许类型: {allowed}'

        # S-02: 文件头魔数校验（先读头部再回绕，防止"改后缀"绕过扩展名白名单）
        uploaded_file.seek(0)
        head = uploaded_file.read(_MAGIC_HEAD_SIZE)
        uploaded_file.seek(0)
        magic_ok, magic_reason = cls._check_magic(ext, head)
        if not magic_ok:
            return False, magic_reason

        save_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', config['dir'])
        os.makedirs(save_dir, exist_ok=True)

        filename = cls._generate_unique_filename(original_name)
        save_path = os.path.join(save_dir, filename)

        try:
            with open(save_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
        except Exception as e:
            return False, f'文件写入失败: {str(e)}'

        relative_path = os.path.join('uploads', config['dir'], filename).replace('\\', '/')
        file_url = f"{settings.MEDIA_URL}{relative_path}"

        return True, {
            'filename': filename,
            'original_name': original_name,
            'size': file_size,
            'size_mb': round(file_size / (1024 * 1024), 2),
            'ext': ext,
            'type': upload_type,
            'relative_path': relative_path,
            'url': file_url,
        }
