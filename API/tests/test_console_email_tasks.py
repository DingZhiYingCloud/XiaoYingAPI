"""超管控制台「邮件定时推送」页 单元测试

覆盖：页面渲染、新增 / 启停 / 删除、参数校验与鉴权（非超管不可见）。
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from API.models import EmailTask

URL_NAME = 'website:console_email_tasks'


class ConsoleEmailTasksTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('sh_admin', 'a@example.com', 'pw12345678')
        self.client = Client()
        self.client.force_login(self.admin)
        self.url = reverse(URL_NAME)

    def _create(self, **overrides):
        data = {
            'action': 'task_create', 'app_id': '', 'recipients': 'a@b.com',
            'subject': '标题', 'body': '正文', 'interval_minutes': '30',
            'first_send_at': '', 'enabled': 'on',
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_requires_superadmin(self):
        """未登录访问后台入口 → 返回 404（后台入口隐身）或跳登录页"""
        response = Client().get(self.url)
        self.assertIn(response.status_code, (302, 404))

    def test_list_renders(self):
        EmailTask.objects.create(app_id='', recipients='a@b.com', subject='日报',
                                 body='正文', interval_minutes=0, next_run_at=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('日报', response.content.decode())

    def test_create_task(self):
        response = self._create(recipients='a@b.com, c@d.com', interval_minutes='30')
        self.assertEqual(response.status_code, 302)
        task = EmailTask.objects.get()
        self.assertEqual(task.recipients, 'a@b.com,c@d.com')
        self.assertEqual(task.interval_minutes, 30)
        self.assertTrue(task.enabled)

    def test_create_rejects_bad_email(self):
        self._create(recipients='not-an-email')
        self.assertEqual(EmailTask.objects.count(), 0)

    def test_create_rejects_unknown_app(self):
        self._create(app_id='app_not_exist')
        self.assertEqual(EmailTask.objects.count(), 0)

    def test_toggle(self):
        task = EmailTask.objects.create(app_id='', recipients='a@b.com', subject='t',
                                        body='b', interval_minutes=0)
        self.client.post(self.url, {'action': 'task_toggle', 'id': str(task.pk)})
        task.refresh_from_db()
        self.assertFalse(task.enabled)

    def test_delete(self):
        task = EmailTask.objects.create(app_id='', recipients='a@b.com', subject='t',
                                        body='b', interval_minutes=0)
        self.client.post(self.url, {'action': 'task_delete', 'id': str(task.pk)})
        self.assertEqual(EmailTask.objects.count(), 0)
