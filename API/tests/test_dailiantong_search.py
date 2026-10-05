"""代练通「搜索订单」「热门搜索词」接口单元测试

覆盖场景：
- 搜索订单爬虫：默认对齐官网搜索页（IsPub=9/PGType=2/FilterType=0）、自定义参数透传、本层分页切片
- 热词爬虫：成功 / 上游失败
- 视图契约：game_id 必填、整数参数校验、分页范围、默认值透传
"""
import json
import sys
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request
from API.apis.DaiLianTong import utils as dlt_utils

# 导入 utils 时已把爬虫目录注入 sys.path 并导入 home 模块
_home = sys.modules['home']
DaiLianTongService = dlt_utils.DaiLianTongService


def _fake_json_response(payload):
    """构造一个只提供 .json() 的假 HTTP 响应"""
    resp = mock.Mock()
    resp.json.return_value = payload
    return resp


class _ServiceMixin:
    def _service(self):
        # 独立于 .env：构造实例时临时提供签名密钥
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        service.session = mock.Mock()
        return service


class SearchOrdersCrawlerTests(_ServiceMixin, TestCase):
    """搜索订单：默认口径 + 自定义参数 + 分页切片"""

    def test_defaults_and_slicing(self):
        payload = {'LevelOrderList': [{'SerialNo': f'S{i}'} for i in range(5)]}
        service = self._service()
        service.session.post.return_value = _fake_json_response(payload)

        result = service.search_orders(game_id=107, search_str='马可波罗', page=2, page_size=2)

        self.assertEqual(result['code'], 0)
        self.assertEqual(result['data']['items'], [{'SerialNo': 'S2'}, {'SerialNo': 'S3'}])
        self.assertEqual(result['data']['total'], 5)
        self.assertEqual(result['data']['total_pages'], 3)
        sent = service.session.post.call_args.kwargs['data']
        # 默认对齐官网搜索页
        self.assertEqual(sent['IsPub'], '9')
        self.assertEqual(sent['PGType'], '2')
        self.assertEqual(sent['FilterType'], '0')
        self.assertEqual(sent['SearchStr'], '马可波罗')
        self.assertEqual(sent['GameID'], '107')
        # 订单类型为空时不下发 LevelType2（上游对空值返回异常）
        self.assertNotIn('LevelType2', sent)

    def test_custom_params_mapped(self):
        service = self._service()
        service.session.post.return_value = _fake_json_response({'LevelOrderList': []})
        service.search_orders(
            game_id=107, is_pub=1, pg_type=0, zone_id=1, server_id=2, level_type2='13',
            stier='钻石', etier='王者', price_str='1_20', pub_cancel=20, settle_hour=12,
            filter_type=1, sort_str='Price_DESC', focused=0, order_type=2,
            pub_recommend=1, score1=5, score2=6,
        )
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['IsPub'], '1')
        self.assertEqual(sent['PGType'], '0')
        self.assertEqual(sent['ZoneID'], '1')
        self.assertEqual(sent['ServerID'], '2')
        self.assertEqual(sent['LevelType2'], '13')
        self.assertEqual(sent['STier'], '钻石')
        self.assertEqual(sent['ETier'], '王者')
        self.assertEqual(sent['Price_Str'], '1_20')
        self.assertEqual(sent['PubCancel'], '20')
        self.assertEqual(sent['SettleHour'], '12')
        self.assertEqual(sent['FilterType'], '1')
        self.assertEqual(sent['Sort_Str'], 'Price_DESC')
        self.assertEqual(sent['Focused'], '0')
        self.assertEqual(sent['OrderType'], '2')
        self.assertEqual(sent['PubRecommend'], '1')
        self.assertEqual(sent['Score1'], '5')
        self.assertEqual(sent['Score2'], '6')

    def test_bad_response_returns_error(self):
        service = self._service()
        service.session.post.return_value = _fake_json_response({'unexpected': True})
        self.assertEqual(service.search_orders(game_id=107)['code'], 1)


class HotSearchWordsCrawlerTests(_ServiceMixin, TestCase):
    """热门搜索词"""

    def test_success(self):
        service = self._service()
        service.session.get.return_value = _fake_json_response(
            {'ReturnCode': 1, 'Result': ['马可波罗', '安琪拉'], 'Result1': '说明'})
        result = service.get_hot_search_words(107)
        self.assertEqual(result['code'], 0)
        self.assertEqual(result['data'], {'words': ['马可波罗', '安琪拉'], 'tip': '说明'})

    def test_upstream_failure(self):
        service = self._service()
        service.session.get.return_value = _fake_json_response(
            {'ReturnCode': 0, 'Message': '获取失败'})
        result = service.get_hot_search_words(107)
        self.assertEqual(result['code'], 1)
        self.assertEqual(result['message'], '获取失败')


class SearchOrdersViewTests(TestCase):
    """搜索订单：视图契约"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/search/orders'

    @mock.patch('API.apis.DaiLianTong.utils.search_orders')
    def test_defaults_passed(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        resp = dlt_request.search_orders_view(self.factory.get(self.url, {'game_id': '107'}))
        self.assertEqual(json.loads(resp.content)['code'], 10000)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['game_id'], 107)
        self.assertEqual(kwargs['is_pub'], 9)      # 对齐官网搜索
        self.assertEqual(kwargs['pg_type'], 2)
        self.assertEqual(kwargs['filter_type'], 0)
        self.assertEqual(kwargs['focused'], -1)
        self.assertEqual(kwargs['page'], 1)
        self.assertEqual(kwargs['page_size'], 20)

    @mock.patch('API.apis.DaiLianTong.utils.search_orders')
    def test_explicit_params_passed(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        dlt_request.search_orders_view(self.factory.get(self.url, {
            'game_id': '107', 'search_str': '马可波罗', 'is_pub': '1', 'pg_type': '0',
            'level_type2': '13', 'stier': '钻石', 'page_size': '5'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['search_str'], '马可波罗')
        self.assertEqual(kwargs['is_pub'], 1)
        self.assertEqual(kwargs['pg_type'], 0)
        self.assertEqual(kwargs['level_type2'], '13')
        self.assertEqual(kwargs['stier'], '钻石')
        self.assertEqual(kwargs['page_size'], 5)

    def test_missing_game_id(self):
        resp = dlt_request.search_orders_view(self.factory.get(self.url))
        self.assertEqual(json.loads(resp.content)['code'], 20001)

    def test_invalid_game_id(self):
        resp = dlt_request.search_orders_view(self.factory.get(self.url, {'game_id': 'x'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)

    def test_invalid_int_param(self):
        resp = dlt_request.search_orders_view(self.factory.get(self.url, {'game_id': '107', 'is_pub': 'x'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)

    def test_page_size_out_of_range(self):
        resp = dlt_request.search_orders_view(self.factory.get(self.url, {'game_id': '107', 'page_size': '101'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)


class HotSearchWordsViewTests(TestCase):
    """热门搜索词：视图契约"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/search/hot-words'

    @mock.patch('API.apis.DaiLianTong.utils.get_hot_search_words')
    def test_success(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok',
                                      'data': {'words': ['马可波罗'], 'tip': ''}})
        resp = dlt_request.hot_search_words_view(self.factory.get(self.url, {'game_id': '107'}))
        body = json.loads(resp.content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['words'], ['马可波罗'])
        mocked.assert_called_once_with(107)

    def test_missing_game_id(self):
        resp = dlt_request.hot_search_words_view(self.factory.get(self.url))
        self.assertEqual(json.loads(resp.content)['code'], 20001)

    def test_invalid_game_id(self):
        resp = dlt_request.hot_search_words_view(self.factory.get(self.url, {'game_id': 'x'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)
