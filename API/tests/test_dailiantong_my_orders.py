"""代练通「我的订单」接口（升级版）单元测试

覆盖场景：
- 爬虫：筛选参数透传到上游字段、服务端分页（不本地切片）、返回分页对象
- 爬虫异常：上游返回结构异常时返回失败
- 视图契约：默认值、显式筛选参数透传、game_id/page_size 校验
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


def _fake_response(payload):
    """构造一个只提供 .json() 的假 HTTP 响应"""
    resp = mock.Mock()
    resp.json.return_value = payload
    return resp


class MyOrdersCrawlerTests(TestCase):
    """爬虫层：筛选参数映射 + 服务端分页"""

    def _service_with_response(self, payload):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        session = mock.Mock()
        session.post.return_value = _fake_response(payload)
        service.session = session
        return service

    def test_filters_mapped_and_server_pagination(self):
        payload = {'RecordCount': 3, 'LevelOrderList': [{'SerialNo': 'A1'}], 'NextPageWithTG': 0}
        service = self._service_with_response(payload)

        result = service.get_my_order(
            token='tok', user_id=24544092, publish=0, over_days=99, status=12,
            cancel_status=10, game_id=107, search_str='丁丁', game_mobile='15346607104',
            with_tg=0, page_index=2, page_size=1,
        )

        self.assertEqual(result['code'], 0)
        # 服务端分页：items 原样透传（不本地切片），total 取 RecordCount
        self.assertEqual(result['data'], {
            'items': [{'SerialNo': 'A1'}], 'total': 3, 'page': 2, 'page_size': 1, 'total_pages': 3,
        })
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['Publish'], '0')
        self.assertEqual(sent['OverDays'], '99')
        self.assertEqual(sent['Status'], '12')
        self.assertEqual(sent['CancelStatus'], '10')
        self.assertEqual(sent['GameID'], '107')
        self.assertEqual(sent['SearchStr'], '丁丁')
        self.assertEqual(sent['GameMobile'], '15346607104')
        self.assertEqual(sent['WithTG'], '0')
        self.assertEqual(sent['PageIndex'], '2')
        self.assertEqual(sent['PageSize'], '1')
        self.assertEqual(sent['UserID'], '24544092')

    def test_defaults(self):
        service = self._service_with_response({'RecordCount': 0, 'LevelOrderList': []})
        result = service.get_my_order(token='tok', user_id=1)
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['Publish'], '1')       # 默认我发布的
        self.assertEqual(sent['OverDays'], '-99')    # 默认进行中
        self.assertEqual(sent['Status'], '0')
        self.assertEqual(sent['CancelStatus'], '0')
        self.assertEqual(sent['GameID'], '0')
        self.assertEqual(sent['WithTG'], '1')
        self.assertEqual(result['data']['total'], 0)

    def test_bad_response_returns_error(self):
        service = self._service_with_response({'unexpected': True})
        self.assertEqual(service.get_my_order(token='tok', user_id=1)['code'], 1)


class MyOrdersViewTests(TestCase):
    """视图层：契约"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/orders/my'

    @mock.patch('API.apis.DaiLianTong.utils.get_my_order')
    def test_defaults_passed(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        resp = dlt_request.my_orders_view(self.factory.get(self.url))
        self.assertEqual(json.loads(resp.content)['code'], 10000)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['publish'], 1)
        self.assertEqual(kwargs['over_days'], -99)
        self.assertEqual(kwargs['status'], 0)
        self.assertEqual(kwargs['cancel_status'], 0)
        self.assertEqual(kwargs['game_id'], 0)
        self.assertEqual(kwargs['with_tg'], 1)
        self.assertEqual(kwargs['page'], 1)
        self.assertEqual(kwargs['page_size'], 20)

    @mock.patch('API.apis.DaiLianTong.utils.get_my_order')
    def test_explicit_filters_passed(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        dlt_request.my_orders_view(self.factory.get(self.url, {
            'user_id': '24544092', 'token': 'tok', 'publish': '0', 'over_days': '99',
            'status': '12', 'game_id': '107', 'search_str': '丁丁', 'with_tg': '0',
            'page': '2', 'page_size': '5'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['user_id'], 24544092)
        self.assertEqual(kwargs['publish'], 0)
        self.assertEqual(kwargs['over_days'], 99)
        self.assertEqual(kwargs['status'], 12)
        self.assertEqual(kwargs['game_id'], 107)
        self.assertEqual(kwargs['search_str'], '丁丁')
        self.assertEqual(kwargs['with_tg'], 0)
        self.assertEqual(kwargs['page'], 2)
        self.assertEqual(kwargs['page_size'], 5)

    def test_invalid_user_id(self):
        resp = dlt_request.my_orders_view(self.factory.get(self.url, {'user_id': 'abc'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)

    def test_invalid_int_param(self):
        resp = dlt_request.my_orders_view(self.factory.get(self.url, {'publish': 'x'}))
        self.assertEqual(json.loads(resp.content)['code'], 20002)

    def test_page_size_out_of_range(self):
        resp = dlt_request.my_orders_view(self.factory.get(self.url, {'page_size': '101'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)

    @mock.patch('API.apis.DaiLianTong.utils.get_my_order')
    def test_state_preset_in_progress(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        dlt_request.my_orders_view(self.factory.get(self.url, {'state': '等待验收'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['status'], 13)
        self.assertEqual(kwargs['cancel_status'], 0)
        self.assertEqual(kwargs['over_days'], -99)

    @mock.patch('API.apis.DaiLianTong.utils.get_my_order')
    def test_state_preset_ended(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        dlt_request.my_orders_view(self.factory.get(self.url, {'state': '已结算'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['status'], 17)
        self.assertEqual(kwargs['over_days'], 99)

    @mock.patch('API.apis.DaiLianTong.utils.get_my_order')
    def test_state_cancel_combo(self, mocked):
        # 申请撤销中 = Status16 + CancelStatus11
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        dlt_request.my_orders_view(self.factory.get(self.url, {'state': '申请撤销中'}))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['status'], 16)
        self.assertEqual(kwargs['cancel_status'], 11)

    @mock.patch('API.apis.DaiLianTong.utils.get_my_order')
    def test_explicit_param_overrides_state(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        dlt_request.my_orders_view(self.factory.get(self.url, {'state': '等待验收', 'status': '0'}))
        self.assertEqual(mocked.call_args.kwargs['status'], 0)

    def test_invalid_state(self):
        resp = dlt_request.my_orders_view(self.factory.get(self.url, {'state': '不存在的状态'}))
        self.assertEqual(json.loads(resp.content)['code'], 20003)
