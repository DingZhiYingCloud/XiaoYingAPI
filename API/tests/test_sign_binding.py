"""签名契约测试：签名必须绑定「请求方法 + 请求路径」

防止回归：历史上 `build_sign` 只对参数签名，不覆盖请求目标，
于是同一条签名可被搬到另一个「参数名兼容」的端点复用（截获一次有效请求即可触发
非预期动作）。现在待签串为 `方法(大写)\n路径\n参数串`，本测试锁住该口径。
"""
import secrets
import time

from django.test import TestCase

from API.apis.user_center.sign import build_sign, verify_sign
from API.models.Projects.app import UserApp


class SignBindingTests(TestCase):
    """签名对「方法 + 路径」敏感，且只对当初签的那个端点有效"""

    def setUp(self):
        self.app = UserApp.objects.create(name='签名契约测试项目')

    def _signed(self, method, path, **extra):
        """按给定方法/路径生成一组合法签名参数"""
        params = {
            'app_id': self.app.app_id,
            'timestamp': str(int(time.time())),
            'nonce': secrets.token_hex(8),
            **extra,
        }
        params['sign'] = build_sign(params, self.app.app_secret, method, path)
        return params

    def test_sign_differs_by_method_and_path(self):
        """同样的参数与密钥，方法与路径不同则签名不同"""
        params = {'app_id': 'app_x', 'keyword': 'v'}
        base = build_sign(params, 'sk_k', 'POST', '/api/a/')
        self.assertNotEqual(base, build_sign(params, 'sk_k', 'POST', '/api/b/'))
        self.assertNotEqual(base, build_sign(params, 'sk_k', 'GET', '/api/a/'))

    def test_sign_for_other_path_is_rejected(self):
        """把签名搬到另一个端点上必须被拒（跨端点重放）"""
        params = self._signed('POST', '/api/a/')
        ok, _ = verify_sign(params, 'POST', '/api/b/')
        self.assertFalse(ok)

    def test_sign_for_other_method_is_rejected(self):
        """换一个方法使用同一签名必须被拒"""
        params = self._signed('POST', '/api/a/')
        ok, _ = verify_sign(params, 'GET', '/api/a/')
        self.assertFalse(ok)

    def test_matching_method_and_path_passes(self):
        """方法与路径一致时校验通过"""
        params = self._signed('POST', '/api/a/', keyword='x')
        ok, app = verify_sign(params, 'POST', '/api/a/')
        self.assertTrue(ok)
        self.assertEqual(app.app_id, self.app.app_id)
