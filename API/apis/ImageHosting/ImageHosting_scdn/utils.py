"""ImageHosting 图床服务 API 调用封装

本模块在 sys.path 中注入 SpiderServices 目录后，导入 ImageHostingService 进行包装:
- 每次调用创建新的服务实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
"""
import os
import sys

# 注入 SpiderServices 到 sys.path，使相对导入正常工作
_SPIDER_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..', 'SpiderServices'))
if _SPIDER_ROOT not in sys.path:
    sys.path.insert(0, _SPIDER_ROOT)

from ImageHosting.home import ImageHostingService


def upload_image(image=None, image_url=None, image_filename=None,
                 output_format='auto',
                 password_enabled=False, image_password=None,
                 password_type='plain', password_question=None,
                 cdn_domain=None, storage_destination=None) -> tuple:
    """上传图片到 scdn.io 图床（线路 scdn）

    :param image: 本地图片（Django UploadedFile / file-like / bytes / (文件名, bytes)）
    :param image_url: 远程图片 URL（http/https），与 image 二选一
    :param image_filename: image 为 bytes 时指定文件名（可选）
    :param output_format: 输出格式，默认 auto
    :param password_enabled: 是否加密上传
    :param image_password: 访问密码（加密时必填）
    :param password_type: 密码模式 plain/qa
    :param password_question: 问答式密码的问题（qa 时必填）
    :param cdn_domain: 指定外链 CDN 域名
    :param storage_destination: 存储位置 local/telegram/r2
    :return: (True, dict) 或 (False, error_msg)
    """
    service = ImageHostingService()
    try:
        result = service.upload_image(
            source='scdn', image=image, image_url=image_url, image_filename=image_filename,
            output_format=output_format, password_enabled=password_enabled,
            image_password=image_password, password_type=password_type,
            password_question=password_question, cdn_domain=cdn_domain,
            storage_destination=storage_destination,
        )
        return True, result
    except Exception as e:
        return False, f'upload_image 调用异常: {e}'
