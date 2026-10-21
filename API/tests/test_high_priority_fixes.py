"""高优先级修复回归测试

覆盖：
- 红果转码：取流 / 解包阶段抛异常时，每集锁与全局槽位都必须释放（旧实现会漏锁 30 分钟）；
- 邮件定时任务：发送失败不再静默丢任务（租约 + 重试；一次性任务失败 3 次才停用）；
- 超管登录：连续失败会锁定，锁定期间即使密码正确也拒绝；
- 后台线程 leader：落选进程会低频重试，抢到锁后启动常驻线程。
"""
import json
import os
import tempfile
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User as AuthUser
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from API import apps as api_apps
from API.apis.push.email_task import utils as email_task_utils
from API.common import StatusCode
from API.models import EmailTask
from API.website import views as website_views
from SpiderServices.dramas.hongguo import transcode


class TranscodeLockReleaseTests(SimpleTestCase):
    """转码线程必须在任何失败路径释放自己占的锁与槽位"""

    def test_early_failure_releases_lock_and_slot(self):
        series, ep, width = 'test-lock-release', 4, 720
        key = transcode._job_key(series, ep, width)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(transcode, '_STREAM_DIR', tmp), \
                    mock.patch.object(transcode.app_api, 'get_episode_vids',
                                      side_effect=RuntimeError('取流失败: 模拟')):
                # 必须在 patch 之后再算路径：_lock_path 依赖 _STREAM_DIR
                lock_path = transcode._lock_path(series, ep, width)
                os.makedirs(os.path.dirname(lock_path), exist_ok=True)
                slot = transcode._acquire_slot()
                self.assertIsNotNone(slot)
                self.assertTrue(transcode._acquire_lock_file(lock_path))

                transcode._start(series, ep, width, key, slot)

                deadline = time.time() + 3
                while os.path.exists(lock_path) and time.time() < deadline:
                    time.sleep(0.02)

                self.assertFalse(os.path.exists(lock_path), '失败后每集锁必须释放')
                self.assertFalse(os.path.exists(slot), '失败后全局转码槽位必须释放')
                status = transcode.job_status(series, ep, width)
                self.assertEqual(status.get('state'), 'failed')
                self.assertIn('模拟', status.get('error') or '')

        with transcode._JOBS_LOCK:
            transcode._JOBS.pop(key, None)


class EmailTaskRetryTests(TestCase):
    """发送失败不应让任务消失"""

    def _make_task(self, **overrides):
        now = timezone.now()
        data = {
            'recipients': 'a@example.com',
            'subject': '测试',
            'body': '正文',
            'interval_minutes': 0,
            'enabled': True,
            'next_run_at': now,
        }
        data.update(overrides)
        return EmailTask.objects.create(**data)

    def test_one_off_failure_retries_then_disables(self):
        task = self._make_task()
        with mock.patch.object(email_task_utils, 'send_email',
                               return_value=(False, 'SMTP 不可达')):
            for expected_attempt in (1, 2):
                task.refresh_from_db()
                email_task_utils._claim_and_send(task, timezone.now())
                task.refresh_from_db()
                self.assertTrue(task.enabled)
                self.assertEqual(task.fail_count, expected_attempt)
                self.assertEqual(task.sent_count, 0)
                self.assertGreater(task.next_run_at, timezone.now())
                task.next_run_at = timezone.now()
                task.save(update_fields=['next_run_at'])

            task.refresh_from_db()
            email_task_utils._claim_and_send(task, timezone.now())
            task.refresh_from_db()

        self.assertFalse(task.enabled)
        self.assertIsNone(task.next_run_at)
        self.assertEqual(task.fail_count, email_task_utils.MAX_SEND_ATTEMPTS)
        self.assertEqual(task.sent_count, 0)

    def test_one_off_success_disables_and_counts_once(self):
        task = self._make_task()
        with mock.patch.object(email_task_utils, 'send_email', return_value=(True, 'ok')):
            email_task_utils._claim_and_send(task, timezone.now())

        task.refresh_from_db()
        self.assertFalse(task.enabled)
        self.assertIsNone(task.next_run_at)
        self.assertEqual(task.fail_count, 0)
        self.assertEqual(task.sent_count, 1)

    def test_repeat_failure_waits_next_interval(self):
        task = self._make_task(interval_minutes=10)
        with mock.patch.object(email_task_utils, 'send_email',
                               return_value=(False, 'SMTP 不可达')):
            email_task_utils._claim_and_send(task, timezone.now())

        task.refresh_from_db()
        self.assertTrue(task.enabled)
        self.assertEqual(task.fail_count, 1)
        delta = task.next_run_at - timezone.now()
        self.assertGreaterEqual(delta, timedelta(minutes=9))

    def test_claim_is_exclusive(self):
        task = self._make_task()
        with mock.patch.object(email_task_utils, 'send_email', return_value=(True, 'ok')) as send:
            first = email_task_utils._claim_and_send(task, timezone.now())
            second = email_task_utils._claim_and_send(task, timezone.now())
        self.assertTrue(first)
        self.assertFalse(second, '同一游标只能被抢一次')
        self.assertEqual(send.call_count, 1)


class AdminLoginLockoutTests(TestCase):
    """超管账号连续失败必须锁定"""

    def setUp(self):
        self.admin = AuthUser.objects.create_superuser(
            'hp_admin', 'hp_admin@example.com', 'correct-pass-123')
        self.client = Client()

    def _post(self, password):
        with mock.patch.object(website_views.captcha, 'verify', return_value=(True, None)):
            response = self.client.post('/login/', {
                'login_type': 'account',
                'account': 'hp_admin',
                'password': password,
            })
        return json.loads(response.content.decode())

    def test_locks_after_threshold_and_rejects_correct_password(self):
        for _ in range(4):
            self.assertNotEqual(self._post('wrong-pass')['code'], StatusCode.SUCCESS)

        fifth = self._post('wrong-pass')
        self.assertEqual(fifth['code'], StatusCode.RATE_LIMITED)
        self.assertIn('锁定', fifth['msg'])

        locked = self._post('correct-pass-123')
        self.assertEqual(locked['code'], StatusCode.RATE_LIMITED,
                         '锁定期间即使密码正确也必须拒绝')

    def test_success_before_threshold_clears_counter(self):
        for _ in range(3):
            self._post('wrong-pass')
        ok = self._post('correct-pass-123')
        self.assertEqual(ok['code'], StatusCode.SUCCESS)
        # 成功后计数清零：再错一次不应直接触发锁定
        after = self._post('wrong-pass')
        self.assertNotEqual(after['code'], StatusCode.RATE_LIMITED)


class WorkerLeaderRetryTests(SimpleTestCase):
    """落选 leader 的进程必须能自动补位"""

    def setUp(self):
        api_apps._LEADER_RETRY_STARTED = False

    def tearDown(self):
        api_apps._LEADER_RETRY_STARTED = False

    def test_retry_until_acquired(self):
        attempts = []

        def fake_acquire(quiet=False):
            attempts.append(quiet)
            return len(attempts) >= 2

        with mock.patch.object(api_apps, '_acquire_background_worker_lock',
                               side_effect=fake_acquire), \
                mock.patch.object(api_apps, '_start_background_workers') as start, \
                mock.patch.object(api_apps.time, 'sleep', return_value=None):
            api_apps._start_leader_retry()
            deadline = time.time() + 2
            while not start.called and time.time() < deadline:
                time.sleep(0.01)

        self.assertTrue(start.called, '抢到锁后必须启动常驻线程')
        self.assertGreaterEqual(len(attempts), 2)
        # 重试期间不应反复刷 info 日志
        self.assertTrue(all(quiet for quiet in attempts))

    def test_retry_thread_is_singleton(self):
        with mock.patch.object(api_apps.threading, 'Thread') as thread_cls:
            api_apps._start_leader_retry()
            api_apps._start_leader_retry()
        self.assertEqual(thread_cls.call_count, 1, '只允许起一个重试线程')
