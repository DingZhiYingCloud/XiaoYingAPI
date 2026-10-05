"""代练通全部接口的参数契约测试

重点保证（防止「默认账号」上线后仍被视图层判为缺参）：
1. user_id / token 一律「选填」—— 未传时**不得返回 20001**（改由 utils 回落到后台默认账号）；
2. 各接口自身的业务必填参数仍必须校验（缺失返回 20001，且不调用业务层）；
3. 各接口只接受声明的 HTTP 方法（否则 405）。
"""
import json
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request

# (用例名, HTTP方法, 路径, 视图, 业务层函数名, 最小业务参数)
_ENDPOINTS = [
    ('send_code', 'post', '/api/dlt/auth/send-code',
     dlt_request.send_code_view, 'send_code', {'phone': '13800138000'}),
    ('register', 'post', '/api/dlt/auth/register',
     dlt_request.register_view, 'register', {'phone': '13800138000', 'code': '1234'}),
    ('login', 'post', '/api/dlt/auth/login',
     dlt_request.login_view, 'login', {'phone': '13800138000', 'code': '1234'}),
    ('user_info', 'get', '/api/dlt/user/info',
     dlt_request.user_info_view, 'get_user_info', {}),
    ('set_contact', 'post', '/api/dlt/user/set-contact',
     dlt_request.set_contact_view, 'set_contact', {'contact': '12345'}),
    ('set_mysign', 'post', '/api/dlt/user/set-mysign',
     dlt_request.set_mysign_view, 'set_mysign', {'mysign': 'hi'}),
    ('change_password', 'post', '/api/dlt/user/change-password',
     dlt_request.change_password_view, 'change_password',
     {'new_password': 'n', 'login_id': 'l', 'uid': 'u'}),
    ('sign_in', 'post', '/api/dlt/user/sign-in',
     dlt_request.sign_in_view, 'sign_in', {}),
    ('real_name_info', 'get', '/api/dlt/user/real-name-info',
     dlt_request.real_name_info_view, 'get_real_name_info', {}),
    ('games', 'get', '/api/dlt/games',
     dlt_request.games_view, 'get_games', {}),
    ('games_orders', 'get', '/api/dlt/games/orders',
     dlt_request.games_orders_view, 'get_game_orders', {'game_id': '107'}),
    ('search_orders', 'get', '/api/dlt/search/orders',
     dlt_request.search_orders_view, 'search_orders', {'game_id': '107'}),
    ('hot_search_words', 'get', '/api/dlt/search/hot-words',
     dlt_request.hot_search_words_view, 'get_hot_search_words', {'game_id': '107'}),
    ('receive_order', 'post', '/api/dlt/orders/receive',
     dlt_request.receive_order_view, 'receive_order',
     {'order_id': 'o', 'pay_pass': 'p', 'uid': 'u'}),
    ('publish_order', 'post', '/api/dlt/orders/publish',
     dlt_request.publish_order_view, 'publish_order',
     {'title': 't', 'price': '2', 'time_limit': '3', 'game_mobile': 'm', 'game_account': 'a',
      'game_password': 'p', 'game_author_name': 'r', 'requirements': 'q'}),
    ('delete_order', 'post', '/api/dlt/orders/delete',
     dlt_request.delete_order_view, 'delete_order', {'order_id': 'o'}),
    ('apply_cancel', 'post', '/api/dlt/orders/apply-cancel',
     dlt_request.apply_cancel_view, 'apply_cancel_order',
     {'order_id': 'o', 'pay_pass': 'p', 'uid': 'u'}),
    ('handle_cancel', 'post', '/api/dlt/orders/handle-cancel',
     dlt_request.handle_cancel_view, 'handle_cancel',
     {'order_id': 'o', 'pay_pass': 'p', 'uid': 'u'}),
    ('my_orders', 'get', '/api/dlt/orders/my',
     dlt_request.my_orders_view, 'get_my_order', {}),
    ('upload_image', 'post', '/api/dlt/orders/upload-image',
     dlt_request.upload_image_view, 'upload_image_in_comment',
     {'image_path': 'x', 'order_id': 'o'}),
    ('upload_avatar', 'post', '/api/dlt/avatar/upload',
     dlt_request.upload_avatar_view, 'upload_avatar', {'image_path': 'x'}),
]


def _ok_result():
    """业务层成功返回（视图应映射为 code 10000）"""
    return True, {'code': 0, 'message': 'ok', 'data': {}}


class CredentialOptionalTests(TestCase):
    """不传 user_id / token 时，各接口都不应因缺凭据而返回 20001"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_all_endpoints_accept_missing_credentials(self):
        for name, method, path, view, func, params in _ENDPOINTS:
            with self.subTest(endpoint=name):
                with mock.patch.object(dlt_request.utils, func, return_value=_ok_result()) as mocked:
                    request = getattr(self.factory, method)(path, params)
                    body = json.loads(view(request).content)
                    self.assertEqual(body['code'], 10000,
                                     f'{name} 未传 user_id/token 时不应报 20001：{body}')
                    mocked.assert_called_once()

    def test_user_info_forwards_empty_credentials(self):
        # 直接复现用户上报的场景：/api/dlt/user/info 不带任何凭据
        with mock.patch.object(dlt_request.utils, 'get_user_info', return_value=_ok_result()) as mocked:
            resp = dlt_request.user_info_view(self.factory.get('/api/dlt/user/info'))
            self.assertEqual(json.loads(resp.content)['code'], 10000)
            mocked.assert_called_once_with('', '')

    def test_my_orders_forwards_empty_credentials(self):
        with mock.patch.object(dlt_request.utils, 'get_my_order', return_value=_ok_result()) as mocked:
            dlt_request.my_orders_view(self.factory.get('/api/dlt/orders/my'))
            kwargs = mocked.call_args.kwargs
            self.assertEqual(kwargs['token'], '')
            self.assertEqual(kwargs['user_id'], 0)


class BusinessRequiredParamTests(TestCase):
    """各接口的业务必填参数仍必须校验（缺失返回 20001，且不调用业务层）"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_business_params_returns_20001(self):
        for name, method, path, view, func, params in _ENDPOINTS:
            if not params:
                continue  # 无业务必填参数（仅凭据，而凭据已选填）
            with self.subTest(endpoint=name):
                with mock.patch.object(dlt_request.utils, func, return_value=_ok_result()) as mocked:
                    request = getattr(self.factory, method)(path, {})
                    body = json.loads(view(request).content)
                    self.assertEqual(body['code'], 20001,
                                     f'{name} 缺业务必填参数应报 20001：{body}')
                    mocked.assert_not_called()


class MethodRestrictionTests(TestCase):
    """各接口只接受声明的 HTTP 方法"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_wrong_method_returns_405(self):
        for name, method, path, view, func, params in _ENDPOINTS:
            wrong = 'get' if method == 'post' else 'post'
            with self.subTest(endpoint=name):
                request = getattr(self.factory, wrong)(path, {})
                self.assertEqual(view(request).status_code, 405, name)
