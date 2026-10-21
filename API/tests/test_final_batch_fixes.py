"""最后一批修复回归测试

覆盖：
- 反馈列表用 annotate 统计回复数，模板不再逐行 COUNT；
- AI 流式上游断流：补错误帧 + [DONE]，并关闭上游响应；
- 超级鹰外链图片逐跳校验重定向，302 到内网必须被拒；
- PATCH 表单体 / DELETE JSON 纳入签名，非 GET/POST 禁止旧口径签名；
- 海角两个开放端点按 IP 限流。
"""
import hashlib
import hmac
import json
import secrets
import time
from unittest import mock

from django.core.cache import caches
from django.test import RequestFactory, TestCase
from django.urls import reverse

from API.apis.ai.BuiltInModel import request as ai_request
from API.apis.ai.BuiltInModel import utils as ai_utils
from API.apis.chaojiying import utils as chaojiying_utils
from API.apis.haijiao import request as haijiao_request
from API.apis.user_center.sign import build_sign, verify_sign
from API.common.middleware import build_sign_params
from API.models import Feedback, FeedbackReply, User, UserApp
from API.models.Projects.app import UserApp as ProjectApp


class FeedbackReplyCountTests(TestCase):
    """公开区 / 我的反馈：回复数走 annotate"""

    def setUp(self):
        self.app = ProjectApp.objects.create(name='回复数测试项目')
        self.feedback = Feedback.objects.create(
            app=self.app, content='公开区反馈', status=Feedback.Status.PROCESSING,
            ai_status=Feedback.AiStatus.SKIPPED)
        FeedbackReply.objects.create(feedback=self.feedback, content='回复一')
        FeedbackReply.objects.create(feedback=self.feedback, content='回复二', author_role='admin')

    def test_public_list_has_reply_count(self):
        response = self.client.get(reverse('website:feedback_public',
                                           args=[self.app.app_id]))
        self.assertEqual(response.status_code, 200)
        item = response.context['page_obj'][0]
        self.assertEqual(item.reply_count, 2)

    def test_mine_list_has_reply_count(self):
        user = User.objects.create(account='fb_count_user', password='x')
        self.feedback.user = user
        self.feedback.save(update_fields=['user'])

        session = self.client.session
        session['website_user'] = {
            'user_id': str(user.pk), 'account': user.account, 'username': user.username}
        session.save()

        response = self.client.get(reverse('website:feedback_mine',
                                           args=[self.app.app_id]))
        self.assertEqual(response.status_code, 200)
        item = response.context['page_obj'][0]
        self.assertEqual(item.reply_count, 2)


class AIStreamBreakTests(TestCase):
    """流式断流：必须给前端收尾帧，并关闭上游连接"""

    def test_view_sends_error_and_done_on_upstream_break(self):
        def broken_stream(*args, **kwargs):
            yield 'data: {"content": "a"}\n\n'
            # 真实实现会把 requests 断流转成 ValueError（见 utils.stream_chat_completion），
            # 这里直接模拟转换后的结果，验证视图层的收尾帧。
            raise ValueError('上游连接中断，请稍后重试')

        target = {'temperature': None, 'max_tokens': None, 'stop_list': None}
        with mock.patch.object(ai_request.utils, 'stream_chat_completion',
                               side_effect=broken_stream), \
                mock.patch.object(ai_request, '_sampling', return_value={}):
            response = ai_request._stream_response(target, [])
            # 生成器是惰性的：必须在 patch 生效期间消费，否则会走真实实现
            body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('"code"', body)
        self.assertIn('[DONE]', body)
        self.assertIn('请稍后重试', body)

    def test_upstream_response_closed_on_break(self):
        import requests

        class FakeResponse:
            status_code = 200
            closed = False

            def iter_lines(self, decode_unicode=True):
                yield 'data: {"choices":[{"delta":{"content":"x"}}]}'
                raise requests.exceptions.ChunkedEncodingError('boom')

            def close(self):
                self.closed = True

        fake = FakeResponse()
        target = {'url': 'https://example.com/v1/chat/completions',
                  'api_key': 'sk_test', 'upstream': 'test-model',
                  'temperature': None, 'max_tokens': None, 'stop_list': None}
        with mock.patch.object(ai_utils, '_request_with_retry',
                               return_value=(fake, None)):
            generator = ai_utils.stream_chat_completion(
                target, [{'role': 'user', 'content': 'hi'}])
            with self.assertRaises(ValueError):
                list(generator)

        self.assertTrue(fake.closed, '上游断流后必须关闭响应，避免连接池堆死连接')


class ChaojiyingRedirectTests(TestCase):
    """外链图片下载必须逐跳校验重定向"""

    def test_redirect_to_private_is_blocked(self):
        redirect_resp = mock.Mock(
            is_redirect=True,
            headers={'Location': 'http://127.0.0.1:9099/secret'})

        with mock.patch.object(chaojiying_utils, 'check_public_http_url',
                               side_effect=[(True, ''), (False, '禁止访问内网/保留地址段')]), \
                mock.patch.object(chaojiying_utils.requests, 'get',
                                  return_value=redirect_resp) as get:
            ok, message = chaojiying_utils.download_image('https://evil.example/a.png')

        self.assertFalse(ok)
        self.assertIn('禁止访问', message)
        self.assertEqual(get.call_count, 1, '第二跳校验失败后不得再发请求')

    def test_redirect_to_public_is_followed(self):
        redirect_resp = mock.Mock(
            is_redirect=True,
            headers={'Location': 'https://cdn.example/b.png'})
        final_resp = mock.Mock(is_redirect=False)
        final_resp.raise_for_status = mock.Mock()
        final_resp.iter_content.return_value = [b'PNG-BYTES']
        final_resp.close = mock.Mock()

        with mock.patch.object(chaojiying_utils, 'check_public_http_url',
                               return_value=(True, '')), \
                mock.patch.object(chaojiying_utils.requests, 'get',
                                  side_effect=[redirect_resp, final_resp]):
            ok, payload = chaojiying_utils.download_image('https://evil.example/a.png')

        self.assertTrue(ok)
        self.assertEqual(payload, b'PNG-BYTES')
        self.assertTrue(final_resp.close.called)


class PatchBodySignatureTests(TestCase):
    """PATCH / DELETE 的业务字段必须参与签名"""

    def setUp(self):
        self.rf = RequestFactory()

    def test_patch_form_body_merged(self):
        request = self.rf.patch(
            '/api/haijiao/accounts/x/?app_id=app_x',
            data='nickname=new&status=1',
            content_type='application/x-www-form-urlencoded')
        params, included = build_sign_params(request)
        self.assertTrue(included)
        self.assertEqual(params['app_id'], 'app_x')
        self.assertEqual(params['nickname'], 'new')
        self.assertEqual(params['status'], '1')

    def test_delete_json_body_hashed(self):
        body = json.dumps({'ip': '1.2.3.4:8080'})
        request = self.rf.delete('/api/proxy/x/?app_id=app_x', data=body,
                                 content_type='application/json')
        params, included = build_sign_params(request)
        self.assertTrue(included)
        self.assertEqual(params['body_sha256'],
                         hashlib.sha256(body.encode('utf-8')).hexdigest())

    def test_post_unchanged(self):
        request = self.rf.post('/api/x/', data={'a': '1'})
        params, included = build_sign_params(request)
        self.assertFalse(included)
        self.assertEqual(params['a'], '1')

    def test_legacy_signature_rejected_for_patch(self):
        app = UserApp.objects.create(name='PATCH 签名测试项目')

        def legacy_signed(nonce):
            params = {
                'app_id': app.app_id,
                'timestamp': str(int(time.time())),
                'nonce': nonce,
                'nickname': 'new',
            }
            items = sorted((k, str(v)) for k, v in params.items() if v not in (None, ''))
            raw = '&'.join(f'{k}={v}' for k, v in items)
            params['sign'] = hmac.new(app.app_secret.encode(), raw.encode(),
                                      hashlib.sha256).hexdigest()
            return params

        ok, _ = verify_sign(legacy_signed(secrets.token_hex(8)), 'PATCH', '/api/x/',
                            allow_legacy=False)
        self.assertFalse(ok, 'PATCH 不允许旧口径签名（body 可被篡改）')

        ok, _ = verify_sign(legacy_signed(secrets.token_hex(8)), 'PATCH', '/api/x/',
                            allow_legacy=True)
        self.assertTrue(ok, '兼容开关打开时旧口径仍可用于迁移')

    def test_body_signature_passes(self):
        app = UserApp.objects.create(name='PATCH 新签名测试项目')
        params = {
            'app_id': app.app_id,
            'timestamp': str(int(time.time())),
            'nonce': secrets.token_hex(8),
            'nickname': 'new',
        }
        params['sign'] = build_sign(params, app.app_secret, 'PATCH', '/api/x/')
        ok, _ = verify_sign(params, 'PATCH', '/api/x/', allow_legacy=False)
        self.assertTrue(ok)


class HaijiaoRateLimitTests(TestCase):
    """开放端点必须按 IP 限流"""

    def setUp(self):
        self.rf = RequestFactory()
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def test_video_m3u8_rate_limited(self):
        with mock.patch.object(haijiao_request.utils, 'get_video_playlist',
                               return_value=(True, '#EXTM3U')):
            last = None
            for _ in range(haijiao_request.VIDEO_M3U8_RATE_LIMIT + 1):
                request = self.rf.get('/api/haijiao/video/m3u8',
                                      {'topic_id': '1', 'attachment_id': '2'})
                last = haijiao_request.video_m3u8_view(request)
        self.assertEqual(last.status_code, 200)
        body = json.loads(last.content.decode('utf-8'))
        self.assertEqual(body['code'], 20040)

    def test_image_rate_limited(self):
        payload = 'data:image/png;base64,iVBORw0KGgo='
        with mock.patch.object(haijiao_request, 'check_public_http_url',
                               return_value=(True, '')), \
                mock.patch.object(haijiao_request.utils, 'fetch_image',
                                  return_value=(True, payload)):
            last = None
            for _ in range(haijiao_request.IMAGE_RATE_LIMIT + 1):
                request = self.rf.get('/api/haijiao/image',
                                      {'url': 'https://img.example/a.jpg.txt'})
                last = haijiao_request.image_view(request)
        body = json.loads(last.content.decode('utf-8'))
        self.assertEqual(body['code'], 20040)
