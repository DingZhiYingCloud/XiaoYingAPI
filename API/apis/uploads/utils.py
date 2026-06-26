"""文件上传工具模块

处理文件保存、类型校验、大小限制、唯一文件名生成等逻辑。
"""
import os
import uuid
from datetime import datetime
from django.conf import settings


class FileUploader:
    """文件上传处理器

    支持三种上传类型: image(图片) / video(视频) / file(通用文件)
    每种类型对应独立存储目录，并有独立大小限制。
    """

    TYPE_CONFIG = {
        'image': {
            'dir': 'images',
            'max_size': 20 * 1024 * 1024,
            'allowed_ext': {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff'},
        },
        'video': {
            'dir': 'videos',
            'max_size': 100 * 1024 * 1024,
            'allowed_ext': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'm4v', '3gp'},
        },
        'file': {
            'dir': 'files',
            'max_size': 100 * 1024 * 1024,
            'allowed_ext': None,
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
