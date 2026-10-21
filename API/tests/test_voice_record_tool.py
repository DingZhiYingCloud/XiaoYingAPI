"""文件上传 - 网页录音工具页（/upload/record/）回归测试

覆盖：
- 页面与上传端点都必须登录（未登录跳 /login/）；
- 页面下发时长上下限与上传地址；
- 登录后上传合格音频（3 秒）成功，返回完整在线链接；
- 过短（2 秒）/ 缺文件分别返回 20003 / 20001；
- 上传端点只接受 POST。
"""
import io
import json
import shutil
import tempfile
import unittest
import wave

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from API.apis.uploads import voice as utils
from API.models import User

SESSION_KEY = 'website_user'


def _wav_bytes(seconds, sample_rate=8000):
    """生成指定时长的静音 WAV（8kHz 单声道，体积很小）"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b'\x00\x00' * int(sample_rate * seconds))
    return buf.getvalue()


class VoiceRecordPageTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not utils._ffprobe_bin():
            raise unittest.SkipTest('环境未安装 ffprobe，跳过网页录音测试')

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='voice-record-')
        self._override = override_settings(MEDIA_ROOT=self.media_root)
        self._override.enable()
        self.user = User.objects.create(account='voiceuser', password='x')

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _login(self):
        session = self.client.session
        session[SESSION_KEY] = {'user_id': str(self.user.pk), 'account': self.user.account}
        session.save()

    def test_page_requires_login(self):
        response = self.client.get('/upload/record/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_page_renders_recorder(self):
        self._login()
        response = self.client.get('/upload/record/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-min="3"', html)
        self.assertIn('data-max="60"', html)
        self.assertIn('/upload/record/upload/', html)
        self.assertIn('csrfmiddlewaretoken', html)

    def test_upload_requires_login(self):
        response = self.client.post(
            '/upload/record/upload/',
            {'file': SimpleUploadedFile('a.wav', _wav_bytes(3), content_type='audio/wav')},
        )
        self.assertEqual(response.status_code, 302)

    def test_upload_success(self):
        self._login()
        response = self.client.post(
            '/upload/record/upload/',
            {'file': SimpleUploadedFile('a.wav', _wav_bytes(3), content_type='audio/wav')},
        )
        body = json.loads(response.content)
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['url'].startswith('http://testserver/media/uploads/voices/'))
        self.assertAlmostEqual(body['data']['duration'], 3.0, places=1)

    def test_upload_too_short(self):
        self._login()
        response = self.client.post(
            '/upload/record/upload/',
            {'file': SimpleUploadedFile('a.wav', _wav_bytes(2), content_type='audio/wav')},
        )
        self.assertEqual(json.loads(response.content)['code'], 20003)

    def test_upload_missing_file(self):
        self._login()
        response = self.client.post('/upload/record/upload/', {})
        self.assertEqual(json.loads(response.content)['code'], 20001)

    def test_upload_rejects_get(self):
        self._login()
        self.assertEqual(self.client.get('/upload/record/upload/').status_code, 405)
