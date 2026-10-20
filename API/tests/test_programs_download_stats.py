"""计算程序下载次数统计 回归测试

覆盖：
- 整包下载 / 单文件下载分别累加，互不串账；
- 同 IP + 同程序 + 同入口 60 秒内只计一次，换 IP 后重新计数；
- 不存在的文件 / 程序不计入；
- 前台列表页与详情页显示总次数；
- 控制台「程序下载」页仅超管可见，并展示分项计数。

全程离线：内容根目录指向临时目录，去重缓存换成 locmem（不碰真实 cache/ 目录）。
"""
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import caches
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from API.models import ProgramDownloadStat

PROGRAM_REL = 'demo/prog-a'


class ProgramDownloadStatsTests(TransactionTestCase):
    """用 TransactionTestCase：下载视图返回 FileResponse（流式响应），
    TestCase 的 atomic 包裹下关闭流式响应会触发 close_old_connections
    把连接关在半路（Cannot operate on a closed database），后续用例连锁失败。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        program = root / 'demo' / 'prog-a'
        program.mkdir(parents=True)
        (program / 'README.md').write_text('# demo', encoding='utf-8')
        (program / 'a.txt').write_text('hello', encoding='utf-8')

        caches_conf = dict(settings.CACHES)
        caches_conf['ratelimit'] = {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
        self._override = override_settings(PROGRAMS_ROOT=root, CACHES=caches_conf)
        self._override.enable()
        self.addCleanup(self._override.disable)
        caches['ratelimit'].clear()

        self.url = reverse('website:programs_download')

    def _get(self, **params):
        response = self.client.get(self.url, params)
        self.addCleanup(response.close)
        return response

    def _stat(self):
        return ProgramDownloadStat.objects.get(rel=PROGRAM_REL)

    def test_pack_and_file_counted_separately(self):
        self.assertEqual(self._get(pack=PROGRAM_REL).status_code, 200)
        self.assertEqual(self._stat().pack_count, 1)
        self.assertEqual(self._stat().file_count, 0)

        self.assertEqual(
            self._get(path=f'{PROGRAM_REL}/a.txt').status_code, 200)
        stat = self._stat()
        self.assertEqual(stat.pack_count, 1)
        self.assertEqual(stat.file_count, 1)
        self.assertEqual(stat.total_count, 2)
        self.assertIsNotNone(stat.last_download_time)

    def test_same_ip_deduped_within_window(self):
        self._get(pack=PROGRAM_REL)
        self._get(pack=PROGRAM_REL)
        self.assertEqual(self._stat().pack_count, 1)

        # 换一个来源 IP 视为另一个人，重新计数
        self.client.get(self.url, {'pack': PROGRAM_REL}, REMOTE_ADDR='203.0.113.9').close()
        self.assertEqual(self._stat().pack_count, 2)

    def test_dedupe_is_per_entry(self):
        """整包与单文件是两个入口，同一 IP 互不影响"""
        self._get(pack=PROGRAM_REL)
        self._get(path=f'{PROGRAM_REL}/a.txt')
        stat = self._stat()
        self.assertEqual((stat.pack_count, stat.file_count), (1, 1))

    def test_missing_targets_not_counted(self):
        self.assertEqual(self._get(path=f'{PROGRAM_REL}/nope.txt').status_code, 404)
        self.assertEqual(self._get(pack='demo/not-exist').status_code, 404)
        self.assertFalse(ProgramDownloadStat.objects.exists())

    def test_frontend_pages_show_total(self):
        self._get(pack=PROGRAM_REL)

        index = self.client.get(reverse('website:programs_index'))
        self.assertContains(index, '下载 1 次')

        detail = self.client.get(reverse('website:programs_detail', args=[PROGRAM_REL]))
        self.assertContains(detail, '下载 1 次')

    def test_console_page_requires_superadmin(self):
        url = reverse('website:console_program_downloads')
        self.assertIn(Client().get(url).status_code, (302, 404))

        self._get(pack=PROGRAM_REL)
        admin = User.objects.create_superuser('prog_admin', 'a@example.com', 'pw12345678')
        self.client.force_login(admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(PROGRAM_REL, body)
        self.assertIn('prog-a', body)
