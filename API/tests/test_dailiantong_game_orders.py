"""代练通「按游戏获取订单列表」接口单元测试

覆盖场景：
- 爬虫逻辑：按 GameID 调 LevelOrderList，筛选参数透传到上游字段，并组装分页对象
  （items / total / page / page_size / total_pages）；分页由本层按 page/page_size 切片实现
- 爬虫异常：上游返回结构异常时返回失败
- 视图契约：成功 10000、game_id 缺失 20001、game_id 非法 20002、
  枚举/分页取值非法 20003、上游失败 40001、非 GET 返回 405
"""
import importlib
import json
import sys
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request
from API.apis.DaiLianTong import utils as dlt_utils

# 导入 utils 时已把爬虫目录注入 sys.path 并导入 home 模块
_home = sys.modules['home']
DaiLianTongService = dlt_utils.DaiLianTongService


def _fake_response(payload):
    """构造一个只提供 .json() 的假 HTTP 响应"""
    resp = mock.Mock()
    resp.json.return_value = payload
    return resp


class GameOrdersCrawlerTests(TestCase):
    """爬虫层：筛选参数透传 + 分页切片"""

    def _service_with_response(self, payload):
        # 独立于 .env：构造实例时临时提供签名密钥
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        session = mock.Mock()
        session.post.return_value = _fake_response(payload)
        service.session = session
        return service

    def test_local_pagination_and_filters(self):
        # 上游一次性返回全部（本例 5 条），本层按 page/page_size 切片
        payload = {
            'RecordCount': 5,
            'LevelOrderList': [{'SerialNo': f'A{i}'} for i in range(5)],
        }
        service = self._service_with_response(payload)

        result = service.get_game_orders(
            game_id=107, page=2, page_size=2, pg_type=2,
            order_type='13', start_tier='钻石', end_tier='王者',
            price_str='1_20', pub_cancel=20, settle_hour=12,
            filter_type=1, sort_str='Price_DESC', search_str='澜',
        )

        self.assertEqual(result['code'], 0)
        self.assertEqual(result['data'], {
            'items': [{'SerialNo': 'A2'}, {'SerialNo': 'A3'}],
            'total': 5, 'page': 2, 'page_size': 2, 'total_pages': 3,
        })
        # 校验筛选参数映射到上游字段
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['IsPub'], '1')
        self.assertEqual(sent['GameID'], '107')
        self.assertEqual(sent['PGType'], '2')
        self.assertEqual(sent['LevelType2'], '13')
        self.assertEqual(sent['STier'], '钻石')
        self.assertEqual(sent['ETier'], '王者')
        self.assertEqual(sent['Price_Str'], '1_20')
        self.assertEqual(sent['PubCancel'], '20')
        self.assertEqual(sent['SettleHour'], '12')
        self.assertEqual(sent['FilterType'], '1')
        self.assertEqual(sent['Sort_Str'], 'Price_DESC')
        self.assertEqual(sent['SearchStr'], '澜')

    def test_default_filter_type_is_one(self):
        service = self._service_with_response({'RecordCount': 0, 'LevelOrderList': []})
        service.get_game_orders(game_id=107)
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['FilterType'], '1')
        # 订单类型为空时不下发 LevelType2（上游对空值返回异常）
        self.assertNotIn('LevelType2', sent)

    def test_account_context_passthrough(self):
        # 传登录态时 UserID 用真实账号；token 参与签名（不入表单）
        service = self._service_with_response({'RecordCount': 0, 'LevelOrderList': []})
        service.get_game_orders(game_id=107, user_id=24479174, token='tok123')
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['UserID'], '24479174')

    def test_bad_response_returns_error(self):
        service = self._service_with_response({'unexpected': True})
        result = service.get_game_orders(game_id=107)
        self.assertEqual(result['code'], 1)


class GameOrdersViewTests(TestCase):
    """视图层：筛选参数校验与响应契约"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/games/orders'

    @mock.patch('API.apis.DaiLianTong.utils.get_game_orders')
    def test_success_passes_filters(self, mocked):
        mocked.return_value = (True, {
            'code': 0, 'message': '获取订单列表成功',
            'data': {'items': [], 'total': 0, 'page': 1, 'page_size': 20, 'total_pages': 0},
        })
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {
            'game_id': '107', 'filter_type': '0', 'order_type': '13',
            'start_tier': '钻石', 'search_str': '澜',
        }))
        self.assertEqual(json.loads(resp.content)['code'], 10000)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['game_id'], 107)
        self.assertEqual(kwargs['filter_type'], 0)
        self.assertEqual(kwargs['order_type'], '13')
        self.assertEqual(kwargs['start_tier'], '钻石')
        self.assertEqual(kwargs['search_str'], '澜')

    @mock.patch('API.apis.DaiLianTong.utils.get_game_orders')
    def test_default_filter_type_is_one(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': '', 'data': {}})
        dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['filter_type'], 1)
        self.assertEqual(kwargs['user_id'], 0)
        self.assertEqual(kwargs['token'], '')

    @mock.patch('API.apis.DaiLianTong.utils.get_game_orders')
    def test_account_context_passthrough(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': '', 'data': {}})
        dlt_request.games_orders_view(self.factory.get(self.url, {
            'game_id': '107', 'user_id': '24479174', 'token': 'tok'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['user_id'], 24479174)
        self.assertEqual(kwargs['token'], 'tok')

    def test_invalid_user_id(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107', 'user_id': 'abc'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)

    @mock.patch('API.apis.DaiLianTong.utils.get_game_orders')
    def test_tier_buxian_normalized_to_empty(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': '', 'data': {}})
        dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107', 'start_tier': '不限'}))
        self.assertEqual(mocked.call_args.kwargs['start_tier'], '')

    def test_missing_game_id(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url))
        self.assertEqual(json.loads(resp.content)['code'], 20001)

    def test_invalid_game_id(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': 'abc'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)

    def test_page_size_out_of_range(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107', 'page_size': '101'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)

    def test_invalid_pg_type(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107', 'pg_type': '9'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)

    def test_invalid_order_type(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107', 'order_type': '99'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)

    def test_invalid_tier(self):
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107', 'start_tier': '王者荣耀'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)

    @mock.patch('API.apis.DaiLianTong.utils.get_game_orders')
    def test_upstream_failure(self, mocked):
        mocked.return_value = (False, '获取订单列表失败')
        resp = dlt_request.games_orders_view(self.factory.get(self.url, {'game_id': '107'}))
        self.assertEqual(json.loads(resp.content)['code'], 40001)

    def test_method_not_allowed(self):
        resp = dlt_request.games_orders_view(self.factory.post(self.url, {'game_id': '107'}))
        self.assertEqual(resp.status_code, 405)


class CredentialFallbackTests(TestCase):
    """未传 user_id/token 时回落到平台托管的默认代练通账号

    平台账号的「登录凭据」约定为 JSON：{"user_id": "...", "token": "..."}
    """

    def test_explicit_credentials_win(self):
        with mock.patch('API.apis.DaiLianTong.utils.platform_accounts.get_available_account') as mocked:
            self.assertEqual(dlt_utils._resolve_credentials(123, 'tok'), (123, 'tok'))
            mocked.assert_not_called()

    @mock.patch('API.apis.DaiLianTong.utils.platform_accounts.get_available_account')
    def test_fallback_to_default_account(self, mocked):
        mocked.return_value = mock.Mock(credential='{"user_id": "24479174", "token": "tok_default"}')
        self.assertEqual(dlt_utils._resolve_credentials(0, ''), ('24479174', 'tok_default'))

    @mock.patch('API.apis.DaiLianTong.utils.platform_accounts.get_available_account')
    def test_only_one_provided_still_falls_back(self, mocked):
        # 只传 user_id、没传 token → 回落取默认账号
        mocked.return_value = mock.Mock(credential='{"user_id": "24479174", "token": "tok_default"}')
        self.assertEqual(dlt_utils._resolve_credentials(999, ''), ('24479174', 'tok_default'))

    @mock.patch('API.apis.DaiLianTong.utils.platform_accounts.get_available_account')
    def test_resolve_user_id_helper(self, mocked):
        # 无需 token 的接口只回落 user_id；已传则原样
        self.assertEqual(dlt_utils._resolve_user_id(55), 55)
        mocked.return_value = mock.Mock(credential='{"user_id": "24479174", "token": "tok_default"}')
        self.assertEqual(dlt_utils._resolve_user_id(0), '24479174')

    @mock.patch('API.apis.DaiLianTong.utils.platform_accounts.get_available_account')
    def test_no_default_account_keeps_anonymous(self, mocked):
        mocked.return_value = None
        self.assertEqual(dlt_utils._resolve_credentials(0, ''), (0, ''))

    @mock.patch('API.apis.DaiLianTong.utils.platform_accounts.get_available_account')
    def test_malformed_credential_keeps_anonymous(self, mocked):
        # 凭据不是 JSON（格式不符）→ 视为无可用默认账号
        mocked.return_value = mock.Mock(credential='D026464D800347ADAE554D77B3F6B81B')
        self.assertEqual(dlt_utils._resolve_credentials(0, ''), (0, ''))


class DltCredentialCheckerTests(TestCase):
    """凭据校验器（SpiderServices.DaiLianTong.utils.check_credential）"""

    def _module(self):
        return importlib.import_module('SpiderServices.DaiLianTong.utils')

    def test_malformed_credential(self):
        module = self._module()
        ok, msg = module.check_credential('not-a-json')
        self.assertFalse(ok)
        self.assertIn('JSON', msg)

    def test_missing_token(self):
        module = self._module()
        ok, msg = module.check_credential('{"user_id": "24479174"}')
        self.assertFalse(ok)
        self.assertIn('token', msg)

    def test_valid_credential(self):
        module = self._module()
        resp = mock.Mock()
        resp.json.return_value = {'Result': '1', 'UID': 'USR1', 'NickName': '阿三'}
        with mock.patch.object(module, 'SIGN_KEY', 'test_key'), \
                mock.patch.object(module.requests, 'post', return_value=resp):
            ok, msg = module.check_credential('{"user_id": "24479174", "token": "tok"}')
        self.assertTrue(ok)
        self.assertIn('阿三', msg)

    def test_expired_credential(self):
        module = self._module()
        resp = mock.Mock()
        resp.json.return_value = {'Result': '0', 'Err': '登录已失效'}
        with mock.patch.object(module, 'SIGN_KEY', 'test_key'), \
                mock.patch.object(module.requests, 'post', return_value=resp):
            ok, msg = module.check_credential('{"user_id": "24479174", "token": "tok"}')
        self.assertFalse(ok)
        self.assertIn('登录已失效', msg)
