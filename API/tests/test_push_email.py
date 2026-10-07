"""消息推送 push · 邮件线路 单元测试

覆盖：参数校验、收件人解析、发送成功/失败、以及「邮件写入推送日志」。
发信本身被 mock，不真实外发。
"""
import json
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.push.email import request as push_email_request
from API.apis.push.email import utils as email_utils
from API.models import PushLog

SEND_TARGET = 'API.apis.push.email.utils.send_email'


def _post(**data):
    request = RequestFactory().post('/api/push/email/send', data)
    return request


def _body(response):
    return json.loads(response.content)


class PushEmailSendTests(TestCase):
    def test_missing_subject(self):
        body = _body(push_email_request.send_view(_post(body='x', recipients='a@b.com')))
        self.assertEqual(body['code'], 20001)

    def test_missing_body(self):
        body = _body(push_email_request.send_view(_post(subject='s', recipients='a@b.com')))
        self.assertEqual(body['code'], 20001)

    def test_missing_recipients(self):
        body = _body(push_email_request.send_view(_post(subject='s', body='x')))
        self.assertEqual(body['code'], 20001)

    def test_invalid_email(self):
        body = _body(push_email_request.send_view(_post(subject='s', body='x', recipients='bad')))
        self.assertEqual(body['code'], 20002)

    @mock.patch(SEND_TARGET, return_value=(True, 'ok'))
    def test_success_parses_and_dedups_recipients(self, send):
        request = _post(subject='标题', body='正文', recipients='a@b.com,b@b.com')
        request.auth_app = SimpleNamespace(app_id='app_1')
        body = _body(push_email_request.send_view(request))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data'], {'subject': '标题', 'recipients': ['a@b.com', 'b@b.com'],
                                        'count': 2})
        self.assertEqual(send.call_args[0], ('标题', '正文', ['a@b.com', 'b@b.com']))
        self.assertEqual(send.call_args.kwargs['app_id'], 'app_1')

    @mock.patch(SEND_TARGET, return_value=(False, 'SMTP 连接失败'))
    def test_send_failure_maps_to_external_error(self, send):
        body = _body(push_email_request.send_view(_post(
            subject='s', body='x', recipients='a@b.com')))
        self.assertEqual(body['code'], 40001)
        self.assertIn('SMTP', body['msg'])


class EmailPushLogTests(TestCase):
    """邮件发送都会写进「推送日志」（channel=email），成功与失败都记"""

    @mock.patch('django.core.mail.EmailMessage.send', return_value=1)
    def test_success_writes_log(self, _send):
        ok, _msg = email_utils.send_email('标题', '正文', ['a@b.com', 'c@d.com'], app_id='app_x')
        self.assertTrue(ok)
        log = PushLog.objects.get()
        self.assertEqual(log.channel, 'email')
        self.assertEqual(log.title, '标题')
        self.assertEqual(log.content, '正文')
        self.assertEqual(log.recipients, 'a@b.com,c@d.com')
        self.assertEqual(log.app_id, 'app_x')
        self.assertTrue(log.ok)

    @mock.patch('django.core.mail.EmailMessage.send', side_effect=Exception('SMTP down'))
    def test_failure_writes_log(self, _send):
        ok, _msg = email_utils.send_email('s', 'b', ['a@b.com'])
        self.assertFalse(ok)
        log = PushLog.objects.get()
        self.assertFalse(log.ok)
        self.assertIn('SMTP down', log.message)
        self.assertEqual(log.recipients, 'a@b.com')
