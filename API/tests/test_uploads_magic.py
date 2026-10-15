"""上传魔数校验测试（补齐 video 类型）

原先 video 只校验扩展名白名单，把任意文件改名成 .mp4 就能通过；本测试锁住补齐后的行为，
同时确认图片与文本的既有规则没有被改坏。
"""
from django.test import SimpleTestCase

from API.apis.uploads.utils import FileUploader


def _head(data: bytes) -> bytes:
    """补齐到 512 字节（与上传时读取的文件头长度一致）"""
    return data + b'\x00' * (512 - len(data))


class UploadMagicTests(SimpleTestCase):
    """魔数校验：真容器放行、改名文件拒绝"""

    def test_accepts_real_video_containers(self):
        cases = {
            'mp4': b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom',
            'm4v': b'\x00\x00\x00\x18ftypM4V \x00\x00\x00\x00',
            '3gp': b'\x00\x00\x00\x18ftyp3gp5\x00\x00\x00\x00',
            'mov': b'\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00',
            'avi': b'RIFF\x24\x00\x00\x00AVI LIST',
            'flv': b'FLV\x01\x05\x00\x00\x00\x09',
            'mkv': b'\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f',
            'webm': b'\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f',
            'wmv': b'\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa',
        }
        for ext, head in cases.items():
            ok, reason = FileUploader._check_magic(ext, _head(head))
            self.assertTrue(ok, f'{ext} 被误拒：{reason}')

    def test_rejects_renamed_non_video(self):
        for ext in ('mp4', 'mov', 'avi', 'flv', 'mkv', 'webm', 'wmv', 'm4v', '3gp'):
            ok, reason = FileUploader._check_magic(ext, _head(b'this is not a video at all'))
            self.assertFalse(ok, f'{ext} 应被拒绝')
            self.assertIn('魔数', reason)

    def test_image_and_text_rules_unchanged(self):
        ok, _ = FileUploader._check_magic('png', _head(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue(ok)
        ok, _ = FileUploader._check_magic('png', _head(b'not a png'))
        self.assertFalse(ok)
        ok, _ = FileUploader._check_magic('txt', _head(b'<html><body>x</body></html>'))
        self.assertFalse(ok)
        ok, _ = FileUploader._check_magic('txt', _head(b'hello world'))
        self.assertTrue(ok)
