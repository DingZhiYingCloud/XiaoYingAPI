"""消息推送 push · 邮件定时推送线路 单元测试

覆盖三块：
    1. 视图层 CRUD 与参数校验（含项目隔离）；
    2. 调度层到期发送 / 补发只一次 / 一次性任务 / 失败不重试 / CAS 不重复；
    3. 发送失败只记录不重试。
发信本身被 mock，不真实外发。
"""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, TestCase
from django.utils import timezone

from API.apis.push.email_task import request as task_request
from API.apis.push.email_task import utils as task_utils
from API.models import EmailTask

SEND_TARGET = 'API.apis.push.email_task.utils.send_email'


def _authed(request, app_id='app_a'):
    request.auth_app = SimpleNamespace(app_id=app_id)
    return request


def _post(view, app_id='app_a', **data):
    return view(_authed(RequestFactory().post('/api/push/email_task/', data), app_id))


def _get(view, app_id='app_a', **query):
    return view(_authed(RequestFactory().get('/api/push/email_task/', query), app_id))


def _body(response):
    return json.loads(response.content)


def _make_task(**overrides):
    """直接建任务（绕过视图），默认「立即到期的重复任务」"""
    now = timezone.now()
    fields = {
        'app_id': 'app_a', 'recipients': 'a@b.com', 'subject': '标题', 'body': '正文',
        'interval_minutes': 30, 'enabled': True, 'next_run_at': now - timedelta(minutes=5),
    }
    fields.update(overrides)
    return EmailTask.objects.create(**fields)


class CreateViewTests(TestCase):
    def test_missing_recipients(self):
        body = _body(_post(task_request.create_view, subject='s', body='b'))
        self.assertEqual(body['code'], 20001)

    def test_missing_subject(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com', body='b'))
        self.assertEqual(body['code'], 20001)

    def test_missing_body(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com', subject='s'))
        self.assertEqual(body['code'], 20001)

    def test_invalid_email(self):
        body = _body(_post(task_request.create_view, recipients='bad', subject='s', body='b'))
        self.assertEqual(body['code'], 20002)

    def test_too_many_recipients(self):
        many = ','.join(f'u{i}@b.com' for i in range(task_utils.MAX_RECIPIENTS + 1))
        body = _body(_post(task_request.create_view, recipients=many, subject='s', body='b'))
        self.assertEqual(body['code'], 20003)

    def test_repeat_false_with_interval_conflict(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com', subject='s', body='b',
                           repeat='false', interval_minutes='30'))
        self.assertEqual(body['code'], 20003)

    def test_repeat_true_requires_interval(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com', subject='s', body='b',
                           repeat='true'))
        self.assertEqual(body['code'], 20003)

    def test_interval_over_max(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com', subject='s', body='b',
                           interval_minutes=str(task_utils.MAX_INTERVAL_MINUTES + 1)))
        self.assertEqual(body['code'], 20003)

    def test_bad_first_send_at(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com', subject='s', body='b',
                           first_send_at='not-a-time'))
        self.assertEqual(body['code'], 20002)

    def test_create_once_success(self):
        body = _body(_post(task_request.create_view, recipients='a@b.com,b@b.com',
                           subject='标题', body='正文', repeat='false', interval_minutes='0'))
        self.assertEqual(body['code'], 10000)
        data = body['data']
        self.assertFalse(data['repeat'])
        self.assertEqual(data['interval_minutes'], 0)
        self.assertEqual(data['recipients'], ['a@b.com', 'b@b.com'])
        self.assertTrue(data['enabled'])
        self.assertIsNone(data['last_ok'])
        task = EmailTask.objects.get(pk=data['id'])
        self.assertEqual(task.app_id, 'app_a')

    def test_create_repeat_by_interval_only(self):
        """不传 repeat，仅传 interval>0 → 推导为重复"""
        body = _body(_post(task_request.create_view, recipients='a@b.com',
                           subject='s', body='b', interval_minutes='15'))
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['repeat'])
        self.assertEqual(body['data']['interval_minutes'], 15)

    def test_create_with_future_first_send_at(self):
        future = timezone.localtime(timezone.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')
        body = _body(_post(task_request.create_view, recipients='a@b.com',
                           subject='s', body='b', first_send_at=future))
        self.assertEqual(body['code'], 10000)
        task = EmailTask.objects.get(pk=body['data']['id'])
        self.assertGreater(task.next_run_at, timezone.now() + timedelta(minutes=50))


class CrudViewTests(TestCase):
    def test_list_and_isolation(self):
        _make_task(app_id='app_a', subject='A1')
        _make_task(app_id='app_a', subject='A2')
        _make_task(app_id='app_b', subject='B1')
        body = _body(_get(task_request.list_view, app_id='app_a'))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['total'], 2)
        self.assertEqual({i['subject'] for i in body['data']['items']}, {'A1', 'A2'})

    def test_list_enabled_filter(self):
        _make_task(app_id='app_a', subject='on', enabled=True)
        _make_task(app_id='app_a', subject='off', enabled=False)
        body = _body(_get(task_request.list_view, app_id='app_a', enabled='false'))
        self.assertEqual([i['subject'] for i in body['data']['items']], ['off'])

    def test_detail_other_app_not_found(self):
        task = _make_task(app_id='app_a')
        body = _body(_get(task_request.detail_view, app_id='app_b', id=str(task.id)))
        self.assertEqual(body['code'], 20030)

    def test_update_disable_and_change_interval(self):
        task = _make_task(app_id='app_a', interval_minutes=0, subject='old')
        body = _body(_post(task_request.update_view, app_id='app_a', id=str(task.id),
                           subject='new', repeat='true', interval_minutes='10'))
        self.assertEqual(body['code'], 10000)
        task.refresh_from_db()
        self.assertEqual(task.subject, 'new')
        self.assertEqual(task.interval_minutes, 10)
        self.assertGreater(task.next_run_at, timezone.now() + timedelta(minutes=5))

    def test_update_empty_changes(self):
        task = _make_task(app_id='app_a')
        body = _body(_post(task_request.update_view, app_id='app_a', id=str(task.id)))
        self.assertEqual(body['code'], 20001)

    def test_update_other_app_not_found(self):
        task = _make_task(app_id='app_a')
        body = _body(_post(task_request.update_view, app_id='app_b', id=str(task.id), subject='x'))
        self.assertEqual(body['code'], 20030)

    def test_delete_batch_and_isolation(self):
        t1 = _make_task(app_id='app_a')
        t2 = _make_task(app_id='app_a')
        t3 = _make_task(app_id='app_b')
        body = _body(_post(task_request.delete_view, app_id='app_a',
                           id=f'{t1.id},{t2.id},{t3.id}'))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['deleted'], 2)
        self.assertEqual(EmailTask.objects.filter(app_id='app_a').count(), 0)
        self.assertEqual(EmailTask.objects.filter(app_id='app_b').count(), 1)

    def test_delete_invalid_uuid_skipped(self):
        _make_task(app_id='app_a')
        body = _body(_post(task_request.delete_view, app_id='app_a', id='not-a-uuid'))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['deleted'], 0)


class SchedulerTests(TestCase):
    @mock.patch(SEND_TARGET, return_value=(True, '邮件发送成功'))
    def test_repeat_task_sends_and_advances(self, send):
        task = _make_task(interval_minutes=30, next_run_at=timezone.now() - timedelta(minutes=5))
        processed = task_utils.run_due_tasks()
        self.assertEqual(processed, 1)
        send.assert_called_once()
        task.refresh_from_db()
        self.assertEqual(task.sent_count, 1)
        self.assertTrue(task.last_ok)
        # 下一次 ≈ 当前时间 + 30 分钟
        self.assertGreater(task.next_run_at, timezone.now() + timedelta(minutes=25))
        self.assertLess(task.next_run_at, timezone.now() + timedelta(minutes=35))

    @mock.patch(SEND_TARGET, return_value=(True, 'ok'))
    def test_overdue_many_periods_only_catch_up_once(self, send):
        """停机 3 小时（间隔 30 分钟，欠 6 期）只补发一次"""
        task = _make_task(interval_minutes=30,
                          next_run_at=timezone.now() - timedelta(hours=3))
        task_utils.run_due_tasks()
        send.assert_called_once()
        task.refresh_from_db()
        self.assertEqual(task.sent_count, 1)
        self.assertLess(task.next_run_at, timezone.now() + timedelta(minutes=35))

    @mock.patch(SEND_TARGET, return_value=(True, 'ok'))
    def test_once_task_finishes(self, send):
        task = _make_task(interval_minutes=0, next_run_at=timezone.now() - timedelta(minutes=1))
        task_utils.run_due_tasks()
        send.assert_called_once()
        task.refresh_from_db()
        self.assertFalse(task.enabled)
        self.assertIsNone(task.next_run_at)
        self.assertEqual(task.sent_count, 1)

    @mock.patch(SEND_TARGET, return_value=(False, '邮件发送失败: SMTP down'))
    def test_failure_recorded_no_retry(self, send):
        task = _make_task(interval_minutes=30, next_run_at=timezone.now() - timedelta(minutes=1))
        task_utils.run_due_tasks()
        task.refresh_from_db()
        self.assertFalse(task.last_ok)
        self.assertIn('SMTP', task.last_message)
        self.assertEqual(task.sent_count, 1)
        # 失败也照常推进下一周期，第二轮不再命中
        self.assertEqual(task_utils.run_due_tasks(), 0)

    @mock.patch(SEND_TARGET, return_value=(True, 'ok'))
    def test_not_due_and_disabled_not_sent(self, send):
        _make_task(next_run_at=timezone.now() + timedelta(hours=1))            # 未到期
        _make_task(enabled=False, next_run_at=timezone.now() - timedelta(1))  # 已停用
        self.assertEqual(task_utils.run_due_tasks(), 0)
        send.assert_not_called()

    @mock.patch(SEND_TARGET, return_value=(True, 'ok'))
    def test_cas_no_duplicate_on_second_run(self, send):
        _make_task(interval_minutes=30, next_run_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(task_utils.run_due_tasks(), 1)
        # 游标已推进到未来，第二轮不再命中（模拟另一个 worker 的抢占结果）
        self.assertEqual(task_utils.run_due_tasks(), 0)
        self.assertEqual(send.call_count, 1)
