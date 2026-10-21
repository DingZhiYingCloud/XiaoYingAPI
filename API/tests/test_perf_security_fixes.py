"""下一批优化回归测试

覆盖：
- 页面级上下文缓存（友链 / 外观 / 页脚联系方式）：命中缓存、保存后失效；
- 计算程序目录扫描缓存：只扫一次，手动失效后重扫；
- 签名 nonce 文件判重：同 nonce 重放被拒、不同 nonce / 不同 app 互不影响；
- 接入项目缓存：命中后零查询，保存后失效；
- 反馈附件受控下载：匿名 404、本人 / 超管可读、Range 206，/media 直读被拒。
"""
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User as AuthUser
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from API.apis.user_center import sign
from API.common.security_guard import nonce_replayed
from API.models import Feedback, FeedbackAttachment, User, UserApp
from API.website import context, programs
from API.apis.seo.friend_links.models import FriendLink


class ContextCacheTests(TestCase):
    """全站 context processor 不应每页重复查库"""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(WEBSITE_CONTEXT_CACHE_TTL=60)
    def test_friend_links_cached_and_invalidated(self):
        FriendLink.objects.create(name='A', url='https://a.example')

        with self.assertNumQueries(1):
            first = context.friend_links(None)['footer_friend_links']
        self.assertEqual(len(first), 1)

        with self.assertNumQueries(0):
            second = context.friend_links(None)['footer_friend_links']
        self.assertEqual(len(second), 1)

        # post_save 信号应立刻清缓存：新增后下一次必须重新查库
        FriendLink.objects.create(name='B', url='https://b.example')
        with self.assertNumQueries(1):
            third = context.friend_links(None)['footer_friend_links']
        self.assertEqual(len(third), 2)

    @override_settings(WEBSITE_CONTEXT_CACHE_TTL=60)
    def test_appearance_cached(self):
        context.site_appearance(None)
        with self.assertNumQueries(0):
            context.site_appearance(None)

    @override_settings(WEBSITE_CONTEXT_CACHE_TTL=60)
    def test_footer_contacts_cached(self):
        context.footer_contacts(None)
        with self.assertNumQueries(0):
            context.footer_contacts(None)

    @override_settings(WEBSITE_CONTEXT_CACHE_TTL=0)
    def test_ttl_zero_disables_cache(self):
        FriendLink.objects.create(name='A', url='https://a.example')
        with self.assertNumQueries(1):
            context.friend_links(None)
        with self.assertNumQueries(1):
            context.friend_links(None)


class ProgramsCatalogCacheTests(SimpleTestCase):
    """目录扫描结果缓存"""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        program = self.root / 'demo' / 'prog-a'
        program.mkdir(parents=True)
        (program / 'README.md').write_text('# demo', encoding='utf-8')
        (program / 'a.txt').write_text('hello', encoding='utf-8')

    def test_scan_once_then_cache(self):
        with override_settings(PROGRAMS_ROOT=self.root), \
                mock.patch.object(programs, '_scan_catalog',
                                  wraps=programs._scan_catalog) as scan:
            first = programs.load_catalog()
            second = programs.load_catalog()
            self.assertEqual(scan.call_count, 1)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)

            programs.invalidate_catalog(self.root)
            programs.load_catalog()
            self.assertEqual(scan.call_count, 2)


class NonceFileStoreTests(SimpleTestCase):
    """nonce 判重改为文件占位，不再每请求写库"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(XYAPI_CACHE_ROOT=Path(self.tmp.name))
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_replay_detected(self):
        self.assertFalse(nonce_replayed('app_x', 'nonce-1'))
        self.assertTrue(nonce_replayed('app_x', 'nonce-1'))

    def test_different_nonce_or_app_is_not_replay(self):
        self.assertFalse(nonce_replayed('app_x', 'nonce-1'))
        self.assertFalse(nonce_replayed('app_x', 'nonce-2'))
        self.assertFalse(nonce_replayed('app_y', 'nonce-1'))

    def test_expired_placeholder_is_reused(self):
        self.assertFalse(nonce_replayed('app_x', 'nonce-old'))
        files = list((Path(self.tmp.name) / 'nonce').iterdir())
        self.assertEqual(len(files), 1)
        old = time.time() - 400       # 超过 300 秒 nonce 窗口
        os.utime(files[0], (old, old))
        self.assertFalse(nonce_replayed('app_x', 'nonce-old'))


class SignAppCacheTests(TestCase):
    """接入项目查询缓存"""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_cached_and_invalidated_on_save(self):
        app = UserApp.objects.create(name='签名缓存测试项目')
        cache.clear()

        with self.assertNumQueries(1):
            first = sign._get_app(app.app_id)
        with self.assertNumQueries(0):
            second = sign._get_app(app.app_id)
        self.assertEqual(first.pk, second.pk)

        app.status = False
        app.save()
        with self.assertNumQueries(1):
            third = sign._get_app(app.app_id)
        self.assertFalse(third.status)


class FeedbackAttachmentAccessTests(TransactionTestCase):
    """反馈附件只能通过受控视图读取

    用 TransactionTestCase：响应是 FileResponse / 流式 Range，请求结束会触发
    close_old_connections；TestCase 的外层事务下连接被关在半路，后续用例会连锁报
    「Cannot operate on a closed database」（与程序下载统计测试同一原因）。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        override = override_settings(MEDIA_ROOT=Path(self.tmp.name))
        override.enable()
        self.addCleanup(override.disable)

        self.app = UserApp.objects.create(name='附件权限测试项目')
        self.user = User.objects.create(account='fb_owner', password='x')
        self.feedback = Feedback.objects.create(
            app=self.app, user=self.user, content='带附件的反馈',
            status=Feedback.Status.PROCESSING)
        rel_path = 'uploads/feedback/20260101/test.png'
        full_path = Path(self.tmp.name) / rel_path
        full_path.parent.mkdir(parents=True)
        self.payload = b'\x89PNG\r\n\x1a\n0123456789'
        full_path.write_bytes(self.payload)
        self.attachment = FeedbackAttachment.objects.create(
            feedback=self.feedback, kind=FeedbackAttachment.Kind.IMAGE,
            path=rel_path, original_name='截图.png', size=len(self.payload), ext='png')
        self.url = reverse('website:feedback_attachment', args=[self.attachment.pk])

    def test_anonymous_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_owner_allowed(self):
        session = self.client.session
        session['website_user'] = {'user_id': str(self.user.pk)}
        session.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), self.payload)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('private', response['Cache-Control'])
        response.close()

    def test_superadmin_allowed(self):
        admin = AuthUser.objects.create_superuser('fb_admin', 'fb@example.com', 'pw12345678')
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # 必须读完并关闭流式响应，否则 Windows 上临时目录里的文件句柄不会释放
        self.assertEqual(b''.join(response.streaming_content), self.payload)
        response.close()

    def test_range_request(self):
        session = self.client.session
        session['website_user'] = {'user_id': str(self.user.pk)}
        session.save()
        response = self.client.get(self.url, HTTP_RANGE='bytes=0-3')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b''.join(response.streaming_content), self.payload[:4])
        self.assertEqual(response['Content-Range'], f'bytes 0-3/{len(self.payload)}')
        response.close()

    def test_media_direct_read_denied(self):
        response = self.client.get('/media/uploads/feedback/20260101/test.png')
        self.assertEqual(response.status_code, 404)

    def test_signed_token_allows_anonymous(self):
        from API.apis.feedback.utils import attachment_token

        response = self.client.get(self.url, {'token': attachment_token(self.attachment.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), self.payload)
        response.close()

    def test_bad_token_denied(self):
        response = self.client.get(self.url, {'token': 'not-a-valid-token'})
        self.assertEqual(response.status_code, 404)

    def test_url_property_points_to_controlled_view(self):
        self.assertEqual(self.attachment.url, self.url)

    @override_settings(SITE_URL='https://example.com')
    def test_ai_fallback_url_is_signed(self):
        from API.apis.feedback.ai import _media_absolute_url

        url = _media_absolute_url(self.attachment)
        self.assertTrue(url.startswith('https://example.com/feedback/attachment/'))
        self.assertIn('?token=', url)
