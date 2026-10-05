"""代练通「处理撤销申请」单元测试

覆盖场景：
- 爬虫 request_arbitration：请求参数拼装（ODSerialNo / UserID）
- 业务层 utils.handle_cancel：agree/cancel → LevelOrderCancel(Flag=2/1)、arbitration →
  LevelOrderRequestArbitration；成功后凭证图片上传
- 视图契约：action 默认/枚举校验、agree/cancel 的支付密码与 uid 校验、arbitration 免支付密码
"""
import json
import sys
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request
from API.apis.DaiLianTong import utils as dlt_utils

_home = sys.modules['home']
DaiLianTongService = dlt_utils.DaiLianTongService


def _fake_response(payload):
    resp = mock.Mock()
    resp.json.return_value = payload
    return resp


class ArbitrationCrawlerTests(TestCase):
    """爬虫层：申请平台介入"""

    def _service_with_response(self, payload):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        session = mock.Mock()
        session.post.return_value = _fake_response(payload)
        service.session = session
        return service

    def test_arbitration_payload(self):
        service = self._service_with_response({'Result': '1'})
        result = service.request_arbitration(order_id='10717695025313439830',
                                             token='tok', user_id=24479174)
        self.assertEqual(result['code'], 0)
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['ODSerialNo'], '10717695025313439830')
        self.assertEqual(sent['UserID'], '24479174')


class HandleCancelUtilsTests(TestCase):
    """业务层：动作分发"""

    def test_agree_calls_cancel_with_flag_2(self):
        with mock.patch.object(dlt_utils, '_call',
                               return_value=(True, {'code': 0, 'message': 'ok', 'data': {}})) as mocked:
            ok, _ = dlt_utils.handle_cancel('o', 'agree', pay_pass='p', uid='USR1',
                                            token='tok', user_id='24479174')
        self.assertTrue(ok)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(mocked.call_args.args[0], 'apply_cancel_order')
        self.assertEqual(kwargs['flag'], 2)
        self.assertEqual(kwargs['comment'], '')

    def test_cancel_calls_cancel_with_flag_1(self):
        with mock.patch.object(dlt_utils, '_call',
                               return_value=(True, {'code': 0, 'message': 'ok', 'data': {}})) as mocked:
            dlt_utils.handle_cancel('o', 'cancel', pay_pass='p', uid='USR1',
                                    token='tok', user_id='1')
        self.assertEqual(mocked.call_args.args[0], 'apply_cancel_order')
        self.assertEqual(mocked.call_args.kwargs['flag'], 1)

    def test_arbitration_calls_request_arbitration(self):
        with mock.patch.object(dlt_utils, '_call',
                               return_value=(True, {'code': 0, 'message': 'ok', 'data': {}})) as mocked:
            ok, _ = dlt_utils.handle_cancel('o', 'arbitration', token='tok', user_id='24479174')
        self.assertTrue(ok)
        self.assertEqual(mocked.call_args.args[0], 'request_arbitration')
        self.assertEqual(mocked.call_args.kwargs['order_id'], 'o')

    def test_agree_with_image_uploads_voucher(self):
        calls = []

        def fake_call(method, **kwargs):
            calls.append((method, kwargs))
            return True, {'code': 0, 'message': 'ok', 'data': {}}

        with mock.patch.object(dlt_utils, '_call', side_effect=fake_call):
            ok, _ = dlt_utils.handle_cancel('o', 'agree', pay_pass='p', uid='USR1',
                                            token='tok', user_id='1', image='x.png')
        self.assertTrue(ok)
        self.assertEqual(calls[0][0], 'apply_cancel_order')
        self.assertEqual(calls[1][0], 'upload_image_in_order_comment')
        self.assertEqual(calls[1][1]['msg'], '撤销')


class HandleCancelViewTests(TestCase):
    """视图契约"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/orders/handle-cancel'

    def _post(self, **data):
        return dlt_request.handle_cancel_view(self.factory.post(self.url, data))

    @mock.patch.object(dlt_request.utils, 'handle_cancel',
                       return_value=(True, {'code': 0, 'message': 'ok', 'data': {}}))
    def test_default_action_is_agree(self, mocked):
        body = json.loads(self._post(order_id='o', pay_pass='p', uid='u').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[1], 'agree')

    @mock.patch.object(dlt_request.utils, 'handle_cancel',
                       return_value=(True, {'code': 0, 'message': 'ok', 'data': {}}))
    def test_arbitration_needs_no_pay_pass(self, mocked):
        body = json.loads(self._post(order_id='o', action='arbitration').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[1], 'arbitration')

    def test_missing_order_id(self):
        body = json.loads(self._post(pay_pass='p', uid='u').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('order_id', body['msg'])

    def test_agree_missing_pay_pass(self):
        body = json.loads(self._post(order_id='o', uid='u').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('pay_pass', body['msg'])

    def test_invalid_action(self):
        body = json.loads(self._post(order_id='o', action='乱写').content)
        self.assertEqual(body['code'], 20003)
