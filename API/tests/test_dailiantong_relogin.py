"""代练通 Token 失效「自动重登」兜底单元测试

覆盖：
- 签名错误识别
- _call 在带凭据调用遇到「签名错误」时用新 Token 重试一次
- _relogin 用账号表里的 login_id + password 重登并写回新凭据
"""
import json
from unittest import mock

from django.test import TestCase

from API.apis.DaiLianTong import utils as dlt_utils
from API.models.Accounts.account import AccountStatus, PlatformAccount


def _account(**overrides):
    fields = dict(platform='dlt', account='acc1',
                  credential=json.dumps({'user_id': '1', 'uid': 'USR0', 'token': 'OLD',
                                         'login_id': '15608758048', 'pay_pass': '128524'}),
                  password='pw')
    fields.update(overrides)
    return PlatformAccount.objects.create(**fields)


class SignatureErrorTests(TestCase):
    def test_detection(self):
        self.assertTrue(dlt_utils._is_signature_error({'code': 1, 'message': '签名错误.'}))
        self.assertFalse(dlt_utils._is_signature_error({'code': 0, 'message': 'ok'}))
        self.assertFalse(dlt_utils._is_signature_error('签名错误'))
        self.assertFalse(dlt_utils._is_signature_error(None))


class CallRetryTests(TestCase):
    @mock.patch('API.apis.DaiLianTong.utils._relogin',
                return_value={'user_id': '9', 'token': 'NEW'})
    @mock.patch('API.apis.DaiLianTong.utils._invoke')
    def test_retries_with_fresh_token(self, invoke, relogin):
        invoke.side_effect = [
            (True, {'code': 1, 'message': '签名错误.'}),
            (True, {'code': 0, 'message': 'ok', 'data': {'x': 1}}),
        ]
        ok, data = dlt_utils._call('get_user_info', user_id='1', token='OLD')
        self.assertTrue(ok)
        self.assertEqual(data.get('code'), 0)
        self.assertEqual(invoke.call_count, 2)
        # 第二次调用用的是重登后的新凭据
        retried = invoke.call_args_list[1][0][1]
        self.assertEqual(retried['token'], 'NEW')
        self.assertEqual(retried['user_id'], '9')

    @mock.patch('API.apis.DaiLianTong.utils._relogin')
    @mock.patch('API.apis.DaiLianTong.utils._invoke')
    def test_no_retry_without_token(self, invoke, relogin):
        # 匿名调用（无 token）遇到签名错误不触发重登
        invoke.return_value = (True, {'code': 1, 'message': '签名错误.'})
        ok, _data = dlt_utils._call('get_games')
        self.assertTrue(ok)
        relogin.assert_not_called()
        self.assertEqual(invoke.call_count, 1)

    @mock.patch('API.apis.DaiLianTong.utils._relogin', return_value=None)
    @mock.patch('API.apis.DaiLianTong.utils._invoke')
    def test_keeps_error_when_relogin_fails(self, invoke, relogin):
        invoke.return_value = (True, {'code': 1, 'message': '签名错误.'})
        _ok, data = dlt_utils._call('get_user_info', user_id='1', token='OLD')
        self.assertEqual(data.get('message'), '签名错误.')
        relogin.assert_called_once()
        self.assertEqual(invoke.call_count, 1)


class ReloginTests(TestCase):
    @mock.patch('API.apis.DaiLianTong.utils.login')
    def test_updates_credential(self, login):
        login.return_value = (True, {'code': 0, 'message': '登录成功',
                                     'data': {'UserID': 24479174, 'UID': 'USR1', 'Token': 'NEWTOKEN'}})
        _account()
        fresh = dlt_utils._relogin()
        self.assertEqual(fresh, {'user_id': '24479174', 'token': 'NEWTOKEN'})
        login.assert_called_once_with('15608758048', 'pw', code_type='Password')

        acc = PlatformAccount.objects.get(platform='dlt', account='acc1')
        data = json.loads(acc.credential)
        self.assertEqual(data['token'], 'NEWTOKEN')
        self.assertEqual(data['uid'], 'USR1')
        self.assertEqual(data['login_id'], '15608758048')   # 其它字段保留
        self.assertEqual(acc.status, AccountStatus.VALID)
        self.assertIsNotNone(acc.last_login_time)

    def test_returns_none_without_login_config(self):
        # 缺 login_id → 无法重登
        _account(account='acc2', credential=json.dumps({'user_id': '1', 'token': 'OLD'}))
        self.assertIsNone(dlt_utils._relogin())

    @mock.patch('API.apis.DaiLianTong.utils.login')
    def test_returns_none_when_login_fails(self, login):
        login.return_value = (True, {'code': 1, 'message': '密码错误'})
        _account()
        self.assertIsNone(dlt_utils._relogin())
