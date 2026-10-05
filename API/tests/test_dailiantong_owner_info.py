"""代练通「号主信息」接口单元测试

- 业务层：把订单详情重组成约定的中文键字段
- 视图契约：必填缺失 20001、成功 10000、上游失败 40001
"""
import json
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request
from API.apis.DaiLianTong import utils as dlt_utils


class OwnerInfoUtilsTests(TestCase):
    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_reshape(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {
            'Game': '王者荣耀', 'Zone': '苹果QQ', 'GameAcc': 'acc', 'GamePass': 'pwd',
            'Actor': '角色A', 'GameMobile': '13800000000', 'LeaveTime': '2', 'TimeLimit': 3}})
        ok, data = dlt_utils.get_owner_info('S1')
        self.assertTrue(ok)
        self.assertEqual(data, {'游戏名称': '王者荣耀', '客户端': '苹果QQ', '游戏账号': 'acc',
                                '密码': 'pwd', '角色名': '角色A', '号主联系方式': '13800000000',
                                '剩余时间': '2'})

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_fallback_to_time_limit(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {'TimeLimit': 3}})
        ok, data = dlt_utils.get_owner_info('S1')
        self.assertTrue(ok)
        self.assertEqual(data['剩余时间'], 3)

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_upstream_error(self, mocked):
        mocked.return_value = (True, {'code': 1, 'message': '没有找到该订单'})
        ok, msg = dlt_utils.get_owner_info('S1')
        self.assertFalse(ok)
        self.assertEqual(msg, '没有找到该订单')


class OwnerInfoViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/orders/owner-info'

    def test_missing_order_id(self):
        resp = dlt_request.owner_info_view(self.factory.get(self.url))
        body = json.loads(resp.content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('order_id', body['msg'])

    @mock.patch('API.apis.DaiLianTong.utils.get_owner_info')
    def test_success(self, mocked):
        mocked.return_value = (True, {'游戏名称': '王者荣耀', '游戏账号': 'acc'})
        resp = dlt_request.owner_info_view(self.factory.get(self.url, {'order_id': 'S1'}))
        body = json.loads(resp.content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['游戏账号'], 'acc')

    @mock.patch('API.apis.DaiLianTong.utils.get_owner_info')
    def test_upstream_failure(self, mocked):
        mocked.return_value = (False, '没有找到该订单')
        resp = dlt_request.owner_info_view(self.factory.get(self.url, {'order_id': 'S1'}))
        self.assertEqual(json.loads(resp.content)['code'], 40001)

    def test_method_not_allowed(self):
        resp = dlt_request.owner_info_view(self.factory.post(self.url))
        self.assertEqual(resp.status_code, 405)
