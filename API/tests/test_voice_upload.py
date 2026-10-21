"""文件上传服务 - 声音上传端点（/api/upload/voice）回归测试

覆盖：
- 合格音频（3 秒）上传成功，返回真实时长与完整在线链接；
- 过短（2 秒）/ 过长（61 秒）被拒，且不留下残留文件；
- 非音频内容改名（魔数校验）被拒；
- 缺文件返回 20001；
- 配置 SITE_URL 时链接使用该域名；
- 文档注册表已登记该端点（服务策略页能识别）。
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

from API.apis.uploads import voice as utils
from API.apis.uploads.request import voice_upload_view as upload_view
from API.website.docs import ALL_ENDPOINTS


def _wav_bytes(seconds, sample_rate=8000):
    """生成指定时长的静音 WAV（8kHz 单声道，体积很小）"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b'\x00\x00' * int(sample_rate * seconds))
    return buf.getvalue()


def _webm_bytes(seconds=4, live=False):
    """用 ffmpeg 生成 WebM/Opus 样本

    live=True 时不写 Duration / SeekHead，模拟浏览器 MediaRecorder 的产物。
    """
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return None
    fd, path = tempfile.mkstemp(suffix='.webm')
    os.close(fd)
    cmd = [
        ffmpeg, '-y', '-v', 'error', '-f', 'lavfi',
        '-i', f'sine=frequency=440:duration={seconds}', '-c:a', 'libopus',
    ]
    if live:
        cmd += ['-live', '1']
    cmd.append(path)
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        with open(path, 'rb') as fp:
            return fp.read()
    finally:
        os.remove(path)


class VoiceUploadTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not utils._ffprobe_bin():
            raise unittest.SkipTest('环境未安装 ffprobe，跳过声音上传测试')

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='voice-test-')
        self._override = override_settings(MEDIA_ROOT=self.media_root)
        self._override.enable()
        self.rf = RequestFactory()

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _post(self, filename, content):
        upload = SimpleUploadedFile(filename, content, content_type='audio/wav')
        request = self.rf.post('/api/upload/voice', {'file': upload})
        return json.loads(upload_view(request).content.decode())

    def _voice_dir(self):
        return os.path.join(self.media_root, 'uploads', 'voices')

    def test_upload_three_seconds(self):
        body = self._post('my_voice.wav', _wav_bytes(3))
        self.assertEqual(body['code'], 10000)
        data = body['data']
        self.assertEqual(data['type'], 'audio')
        self.assertAlmostEqual(data['duration'], 3.0, places=1)
        self.assertTrue(data['url'].startswith('http://testserver/media/uploads/voices/'))
        self.assertTrue(os.path.isfile(
            os.path.join(self.media_root, data['relative_path'].replace('/', os.sep))))

    def test_reject_too_short_and_remove_file(self):
        body = self._post('short.wav', _wav_bytes(2))
        self.assertEqual(body['code'], 20003)
        self.assertIn('少于最短 3 秒', body['msg'])
        self.assertFalse(os.path.isdir(self._voice_dir()) and os.listdir(self._voice_dir()))

    def test_reject_too_long_and_remove_file(self):
        body = self._post('long.wav', _wav_bytes(61))
        self.assertEqual(body['code'], 20003)
        self.assertIn('超过最长 60 秒', body['msg'])
        self.assertFalse(os.path.isdir(self._voice_dir()) and os.listdir(self._voice_dir()))

    def test_reject_fake_audio(self):
        body = self._post('fake.mp3', b'\x89PNG\r\n\x1a\n' + b'0' * 128)
        self.assertEqual(body['code'], 20003)
        self.assertIn('魔数校验失败', body['msg'])

    def test_missing_file(self):
        request = self.rf.post('/api/upload/voice', {})
        body = json.loads(upload_view(request).content.decode())
        self.assertEqual(body['code'], 20001)

    @override_settings(SITE_URL='https://xiaoying.example')
    def test_site_url_used_for_absolute_link(self):
        body = self._post('voice.wav', _wav_bytes(3))
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['url'].startswith(
            'https://xiaoying.example/media/uploads/voices/'))

    def test_endpoint_registered_in_docs(self):
        self.assertIn('/api/upload/voice', ALL_ENDPOINTS)
        self.assertIn('POST', ALL_ENDPOINTS['/api/upload/voice'])

    @unittest.skipUnless(shutil.which('ffmpeg'), '需要 ffmpeg 生成 WebM 样本')
    def test_webm_transcoded_to_mp3(self):
        """浏览器录音常用 WebM：必须转成 mp3，保证微信 / Safari 能直接播放"""
        body = self._post('voice.webm', _webm_bytes(4))
        self.assertEqual(body['code'], 10000)
        data = body['data']
        self.assertEqual(data['ext'], 'mp3')
        self.assertTrue(data['url'].endswith('.mp3'))
        self.assertAlmostEqual(data['duration'], 4.0, places=1)
        self.assertTrue(os.path.isfile(
            os.path.join(self.media_root, data['relative_path'].replace('/', os.sep))))
        self.assertEqual([n for n in os.listdir(self._voice_dir()) if n.endswith('.webm')], [])

    @unittest.skipUnless(shutil.which('ffmpeg'), '需要 ffmpeg 生成 WebM 样本')
    def test_webm_without_duration_transcoded(self):
        """MediaRecorder 产物通常没有 Duration：靠包时间戳算时长后仍应成功转码"""
        body = self._post('live.webm', _webm_bytes(4, live=True))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['ext'], 'mp3')
        self.assertAlmostEqual(body['data']['duration'], 4.0, places=1)


class MediaRangeTests(TestCase):
    """在线链接必须支持 Range（Safari / 微信播放音频的前置条件）"""

    def setUp(self):
        # 注意：urls.py 的 media 路由在导入时就把 MEDIA_ROOT 固定成了 document_root，
        # 故这里直接写到真实 media 下的临时子目录（用完即删），不能靠 override_settings。
        self.dir = os.path.join(settings.MEDIA_ROOT, 'uploads', '_range_test')
        os.makedirs(self.dir, exist_ok=True)
        self.url = '/media/uploads/_range_test/sample.wav'
        self.payload = bytes(range(256)) * 4  # 1024 字节
        with open(os.path.join(self.dir, 'sample.wav'), 'wb') as fp:
            fp.write(self.payload)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_partial_content(self):
        response = self.client.get(self.url, HTTP_RANGE='bytes=0-99')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 0-99/1024')
        self.assertEqual(response['Content-Length'], '100')
        self.assertEqual(b''.join(response.streaming_content), self.payload[:100])

    def test_suffix_range(self):
        response = self.client.get(self.url, HTTP_RANGE='bytes=-10')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b''.join(response.streaming_content), self.payload[-10:])

    def test_unsatisfiable_range(self):
        response = self.client.get(self.url, HTTP_RANGE='bytes=2048-')
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response['Content-Range'], 'bytes */1024')

    def test_full_request_advertises_range(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
