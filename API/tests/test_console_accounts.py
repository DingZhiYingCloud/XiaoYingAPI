"""超管控制台「账号管理」按平台切换字段 回归测试

覆盖：
- 页面下发 platform_profiles（字段档案），不同平台显示不同凭据字段；
- Cookie / SendKey 走单字段保存；
- 代练通把「用户 ID + Token」合并成 JSON，缺一个则拒绝；
- 编辑时凭据留空保持原值；切换平台未重填凭据则拒绝；
- 非超管不可访问。
"""
import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from API.models import PlatformAccount

URL_NAME = 'website:console_accounts'


class ConsoleAccountsProfileTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('acc_admin', 'a@example.com', 'pw12345678')
        self.client = Client()
        self.client.force_login(self.admin)
        self.url = reverse(URL_NAME)

    def _post(self, **overrides):
        data = {
            'action': 'save', 'id': '', 'platform': 'zhihu', 'account': 'acc1',
            'password': '', 'credential': '', 'credential_single': '',
            'cred_user_id': '', 'cred_token': '', 'remark': '',
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_page_renders_profiles(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('account-profiles', body)
        self.assertIn('credential_mode', body)
        self.assertIn('"dlt"', body)

        # 英文界面下档案文案已翻译（JSON 里的中文会被转义，英文可直接匹配）
        english = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE='en')
        self.assertIn('Zhihu Cookie', english.content.decode())
        self.assertIn('SendKey', english.content.decode())

    def test_cookie_platform_saves_credential(self):
        self._post(platform='zhihu', credential='z_c0=abc; d_c0=def')
        record = PlatformAccount.objects.get(platform='zhihu', account='acc1')
        self.assertEqual(record.credential, 'z_c0=abc; d_c0=def')
        self.assertEqual(record.status, 'unknown')
        self.assertIsNotNone(record.last_login_time)

    def test_sendkey_platform_uses_single_field(self):
        self._post(platform='serverchan', account='主号', credential_single='SCT123abc')
        record = PlatformAccount.objects.get(platform='serverchan')
        self.assertEqual(record.credential, 'SCT123abc')

    def test_dlt_combines_user_id_and_token(self):
        self._post(platform='dlt', account='主号', cred_user_id='24479174', cred_token='tok-1')
        record = PlatformAccount.objects.get(platform='dlt')
        self.assertEqual(json.loads(record.credential),
                         {'user_id': '24479174', 'token': 'tok-1'})

    def test_dlt_requires_both_fields(self):
        self._post(platform='dlt', account='主号', cred_user_id='24479174')
        self.assertFalse(PlatformAccount.objects.filter(platform='dlt').exists())

    def test_dlt_partial_edit_keeps_other_half(self):
        record = PlatformAccount.objects.create(
            platform='dlt', account='主号',
            credential=json.dumps({'user_id': '24479174', 'token': 'old'}))
        self._post(id=str(record.pk), platform='dlt', account='主号', cred_token='new-token')
        record.refresh_from_db()
        self.assertEqual(json.loads(record.credential),
                         {'user_id': '24479174', 'token': 'new-token'})

    def test_blank_credential_keeps_original(self):
        record = PlatformAccount.objects.create(
            platform='zhihu', account='acc1', credential='old-cookie')
        self._post(id=str(record.pk), platform='zhihu', account='acc1', remark='改了备注')
        record.refresh_from_db()
        self.assertEqual(record.credential, 'old-cookie')
        self.assertEqual(record.remark, '改了备注')

    def test_platform_switch_requires_new_credential(self):
        record = PlatformAccount.objects.create(
            platform='zhihu', account='acc1', credential='old-cookie')
        self._post(id=str(record.pk), platform='serverchan', account='acc1')
        record.refresh_from_db()
        self.assertEqual(record.platform, 'zhihu')
        self.assertEqual(record.credential, 'old-cookie')

    def test_requires_superadmin(self):
        response = Client().get(self.url)
        self.assertIn(response.status_code, (302, 404))
