"""代练丸子「接单 / 搜索订单 / 撤销仲裁」单元测试

- 爬虫契约：断言发往上游的路径与参数名（pageNo/pageSize、payAmount、operaType 等）
- 视图校验：必填项缺失 / 取值非法时的拦截，以及参数透传
"""
import json
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianWanZi import request as dlwz_request
from API.apis.DaiLianWanZi import utils as dlwz_utils

Service = dlwz_utils._dlwz_business_class


class SpiderContractTests(TestCase):
    """爬虫层：上游路径 + 参数名契约（不触网）"""

    def _service(self, captured):
        service = Service()
        service.partner_device = "12345678901234567890"
        calls = []

        def fake_post(path, data_params=None, authorization=None, parse=True):
            calls.append({"path": path, "params": data_params or {}})
            captured["calls"] = calls
            captured["path"] = path
            captured["params"] = data_params or {}
            return {"code": 10000, "data": {}}

        service._post = fake_post
        return service

    def test_search_orders_params(self):
        captured = {}
        self._service(captured).search_orders('tok', keyword='王者', game_id='1', page=2, page_size=5)
        self.assertEqual(captured["path"], "/order/hall/searchList")
        self.assertEqual(captured["params"],
                         {"pageNo": 2, "pageSize": 5, "keyword": "王者", "gameId": "1"})

    def test_search_orders_omits_empty_filters(self):
        captured = {}
        self._service(captured).search_orders('tok')
        self.assertEqual(captured["params"], {"pageNo": 1, "pageSize": 20})

    def test_hall_detail_and_search_words(self):
        captured = {}
        svc = self._service(captured)
        svc.get_hall_order('tok', 'WZ1')
        self.assertEqual((captured["path"], captured["params"]),
                         ("/order/hall/detail", {"tradeNo": "WZ1"}))
        svc.get_search_words('tok')
        self.assertEqual(captured["path"], "/order/hall/getSearchWordList")

    def test_take_order_params(self):
        captured = {}
        self._service(captured).take_order('tok', 'WZ1', take_password='8888', pay_password='128524')
        self.assertEqual(captured["path"], "/order/action/v2/takeOrder")
        self.assertEqual(captured["params"],
                         {"tradeNo": "WZ1", "payPassword": "128524", "takePassword": "8888"})

    def test_take_order_without_take_password(self):
        captured = {}
        self._service(captured).take_order('tok', 'WZ1', pay_password='128524')
        self.assertEqual(captured["params"], {"tradeNo": "WZ1", "payPassword": "128524"})

    def test_take_password_check_params(self):
        captured = {}
        self._service(captured).take_password_check('tok', 'WZ1', '8888')
        self.assertEqual((captured["path"], captured["params"]),
                         ("/order/action/takePasswordCheck", {"tradeNo": "WZ1", "takePassword": "8888"}))

    def test_send_order_images_params(self):
        captured = {}
        self._service(captured).send_order_images('tok', 'WZ1', ['https://x/a.png'], 2)
        self.assertEqual(captured["path"], "/order/action/sendImage")
        self.assertEqual(captured["params"], {
            "tradeNo": "WZ1", "images": [{"url": "https://x/a.png"}], "actionType": 2})

    def test_apply_revocation_uploads_images_then_applies(self):
        captured = {}
        self._service(captured).apply_revocation(
            'tok', trade_no='WZ1', initiator=1, reason='未开始', image_urls=['https://x/a.png'])
        self.assertEqual([c["path"] for c in captured["calls"]],
                         ["/order/action/sendImage", "/order/action/applyRevocation"])
        self.assertEqual(captured["calls"][0]["params"],
                         {"tradeNo": "WZ1", "images": [{"url": "https://x/a.png"}], "actionType": 2})
        self.assertEqual(captured["params"], {
            "tradeNo": "WZ1", "initiator": 1, "deposit": 0,
            "payAmount": 0, "reason": "未开始", "ifAutoArbitrate": 0})

    def test_agree_revocation_params(self):
        captured = {}
        svc = self._service(captured)
        svc.agree_revocation('tok', 'WZ1')
        self.assertEqual((captured["path"], captured["params"]),
                         ("/order/action/agreeRevocation", {"tradeNo": "WZ1"}))
        svc.agree_revocation('tok', 'WZ1', pay_password='128524')
        self.assertEqual(captured["params"], {"tradeNo": "WZ1", "payPassword": "128524"})

    def test_cancel_revocation_params(self):
        captured = {}
        self._service(captured).cancel_revocation('tok', 'WZ1')
        self.assertEqual((captured["path"], captured["params"]),
                         ("/order/action/cancelRevocation", {"tradeNo": "WZ1"}))

    def test_accept_completion_params(self):
        captured = {}
        self._service(captured).accept_completion('tok', 'WZ1', '128524')
        self.assertEqual((captured["path"], captured["params"]),
                         ("/order/action/acceptCompletion",
                          {"tradeNo": "WZ1", "payPassword": "128524"}))

    def test_apply_arbitration_uploads_images_then_applies(self):
        captured = {}
        self._service(captured).apply_arbitration(
            'tok', trade_no='WZ1', initiator=2, reason='争议', image_urls=['https://x/b.png'],
            amount=2, deposit=1)
        self.assertEqual([c["path"] for c in captured["calls"]],
                         ["/order/action/sendImage", "/order/action/applyArbitration"])
        self.assertEqual(captured["calls"][0]["params"],
                         {"tradeNo": "WZ1", "images": [{"url": "https://x/b.png"}], "actionType": 4})
        self.assertEqual(captured["params"], {
            "tradeNo": "WZ1", "initiator": 2, "deposit": 1, "amount": 2,
            "reason": "争议", "operaType": 0})


class SearchOrdersViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _get(self, **params):
        return dlwz_request.business_search_orders_view(
            self.factory.get('/api/dlwz/business/hall/search', params))

    @mock.patch.object(dlwz_request.utils, 'search_orders',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {'page': {}}}))
    def test_defaults(self, mocked):
        body = json.loads(self._get().content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.kwargs['page'], 1)
        self.assertEqual(mocked.call_args.kwargs['page_size'], 20)

    def test_invalid_page(self):
        body = json.loads(self._get(page='x').content)
        self.assertEqual(body['code'], 20002)

    def test_page_size_out_of_range(self):
        body = json.loads(self._get(page_size='999').content)
        self.assertEqual(body['code'], 20003)

    def test_missing_trade_no(self):
        body = json.loads(dlwz_request.business_hall_detail_view(
            self.factory.get('/api/dlwz/business/hall/detail')).content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('trade_no', body['msg'])


class TakeOrderViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _post(self, **data):
        return dlwz_request.business_take_order_view(
            self.factory.post('/api/dlwz/business/orders/take', data))

    def test_missing_trade_no(self):
        body = json.loads(self._post(pay_password='p').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('trade_no', body['msg'])

    def test_missing_pay_password(self):
        body = json.loads(self._post(trade_no='WZ1').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('pay_password', body['msg'])

    def test_password_check_missing_params(self):
        body = json.loads(dlwz_request.business_take_password_check_view(
            self.factory.post('/api/dlwz/business/orders/take-password-check', {'trade_no': 'WZ1'})).content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('take_password', body['msg'])

    @mock.patch.object(dlwz_request.utils, 'take_order',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {}}))
    def test_success_passes_optional_take_password(self, mocked):
        body = json.loads(self._post(trade_no='WZ1', pay_password='128524',
                                     take_password='8888').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.kwargs['take_password'], '8888')
        self.assertEqual(mocked.call_args.args, ('WZ1', '128524'))


class RevocationViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _post(self, view, **data):
        return view(self.factory.post('/api/dlwz/business/orders/revoke', data))

    def test_apply_missing_reason(self):
        body = json.loads(self._post(dlwz_request.business_apply_revocation_view,
                                     trade_no='WZ1', initiator='1').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('reason', body['msg'])

    def test_apply_invalid_initiator(self):
        body = json.loads(self._post(dlwz_request.business_apply_revocation_view,
                                     trade_no='WZ1', initiator='9', reason='x').content)
        self.assertEqual(body['code'], 20003)

    def test_apply_negative_amount(self):
        body = json.loads(self._post(dlwz_request.business_apply_revocation_view,
                                     trade_no='WZ1', initiator='1', reason='x',
                                     images='["https://x/a.png"]', pay_amount='-1').content)
        self.assertEqual(body['code'], 20003)

    def test_apply_missing_images(self):
        body = json.loads(self._post(dlwz_request.business_apply_revocation_view,
                                     trade_no='WZ1', initiator='1', reason='x').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('images', body['msg'])

    def test_apply_invalid_images(self):
        body = json.loads(self._post(dlwz_request.business_apply_revocation_view,
                                     trade_no='WZ1', initiator='1', reason='x',
                                     images='[]').content)
        self.assertEqual(body['code'], 20002)

    @mock.patch.object(dlwz_request.utils, 'apply_revocation',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {}}))
    def test_apply_success_defaults_zero(self, mocked):
        body = json.loads(self._post(dlwz_request.business_apply_revocation_view,
                                     trade_no='WZ1', initiator='1', reason='未开始',
                                     images='["https://x/a.png", "https://x/b.png"]').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[3], ['https://x/a.png', 'https://x/b.png'])
        self.assertEqual(mocked.call_args.kwargs['deposit'], 0)
        self.assertEqual(mocked.call_args.kwargs['pay_amount'], 0)
        self.assertEqual(mocked.call_args.kwargs['if_auto_arbitrate'], 0)

    @mock.patch.object(dlwz_request.utils, 'agree_revocation',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {}}))
    def test_agree_passes_pay_password(self, mocked):
        body = json.loads(self._post(dlwz_request.business_agree_revocation_view,
                                     trade_no='WZ1', pay_password='128524').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[0], 'WZ1')
        self.assertEqual(mocked.call_args.kwargs['pay_password'], '128524')

    def test_cancel_missing_trade_no(self):
        body = json.loads(self._post(dlwz_request.business_cancel_revocation_view).content)
        self.assertEqual(body['code'], 20001)

    def test_arbitration_missing_images(self):
        body = json.loads(self._post(dlwz_request.business_apply_arbitration_view,
                                     trade_no='WZ1', initiator='2', reason='争议').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('images', body['msg'])

    @mock.patch.object(dlwz_request.utils, 'apply_arbitration',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {}}))
    def test_arbitration_success(self, mocked):
        body = json.loads(self._post(dlwz_request.business_apply_arbitration_view,
                                     trade_no='WZ1', initiator='2', reason='争议',
                                     images='["https://x/a.png"]', amount='2',
                                     opera_type='1').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.kwargs['amount'], 2.0)
        self.assertEqual(mocked.call_args.kwargs['opera_type'], 1)
        self.assertEqual(mocked.call_args.args[3], ['https://x/a.png'])


class AcceptCompletionViewTests(TestCase):
    """视图层：同意验收并结账的必填校验与参数透传"""

    def setUp(self):
        self.factory = RequestFactory()

    def _post(self, **data):
        return dlwz_request.business_accept_completion_view(
            self.factory.post('/api/dlwz/business/orders/accept-completion', data))

    def test_missing_trade_no(self):
        body = json.loads(self._post(pay_password='128524').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('trade_no', body['msg'])

    @mock.patch.object(dlwz_request.utils, 'accept_completion',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {}}))
    def test_pay_password_optional_forwarded_empty(self, mocked):
        # 选填：不传时视图原样透传空串，由 utils 回落到后台账号凭据里的 pay_password
        body = json.loads(self._post(trade_no='WZ1').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.kwargs['pay_password'], '')

    @mock.patch.object(dlwz_request.utils, 'accept_completion',
                       return_value=(True, {'code': 0, 'message': 'Success', 'data': {}}))
    def test_success_passes_params(self, mocked):
        body = json.loads(self._post(trade_no='WZ1', pay_password='128524').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[0], 'WZ1')
        self.assertEqual(mocked.call_args.kwargs['pay_password'], '128524')

    @mock.patch.object(dlwz_request.utils, 'accept_completion',
                       return_value=(False, '上游异常'))
    def test_upstream_failure_maps_to_40001(self, mocked):
        body = json.loads(self._post(trade_no='WZ1', pay_password='128524').content)
        self.assertEqual(body['code'], 40001)
        self.assertIn('上游异常', body['msg'])


class ResolvePayPasswordTests(TestCase):
    """支付密码回落：请求值 > 后台账号凭据 > 空"""

    def test_request_value_wins(self):
        self.assertEqual(dlwz_utils._resolve_pay_password('123456'), '123456')

    @mock.patch.object(dlwz_utils, '_default_credential_dict',
                       return_value={'accessToken': 't', 'pay_password': '128524'})
    def test_falls_back_to_credential(self, mocked):
        self.assertEqual(dlwz_utils._resolve_pay_password(''), '128524')

    @mock.patch.object(dlwz_utils, '_default_credential_dict', return_value={'accessToken': 't'})
    def test_empty_when_credential_has_none(self, mocked):
        self.assertEqual(dlwz_utils._resolve_pay_password(''), '')

    @mock.patch.object(dlwz_utils, '_default_credential_dict', return_value={})
    def test_empty_when_no_account(self, mocked):
        self.assertEqual(dlwz_utils._resolve_pay_password(''), '')

    @mock.patch.object(dlwz_utils, '_call_business')
    @mock.patch.object(dlwz_utils, '_default_credential_dict', return_value={})
    def test_accept_completion_without_any_password_errors(self, mocked_cred, mocked_call):
        ok, message = dlwz_utils.accept_completion('WZ1')
        self.assertFalse(ok)
        self.assertIn('支付密码', message)
        mocked_call.assert_not_called()
