"""代练通「申请撤销订单」单元测试

覆盖场景：
- 爬虫 apply_cancel_order：请求参数拼装（ODSerialNo / Flag / PayPass 哈希 / RevokePrice / Comment）
- 业务层 utils.apply_cancel_order：撤销说明（Comment）拼装、成功后凭证图片上传、上传失败仅提示
- 视图契约：必填校验、desire / progress 枚举校验、默认值
"""
import hashlib
import json
import sys
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request
from API.apis.DaiLianTong import utils as dlt_utils

# 导入 utils 时已把爬虫目录注入 sys.path 并导入 home 模块
_home = sys.modules['home']
DaiLianTongService = dlt_utils.DaiLianTongService


def _pwd_hash(pwd, uid):
    """前端 get_pwd_hash：md5(md5(pwd) + uid)"""
    inner = hashlib.md5(pwd.encode()).hexdigest()
    return hashlib.md5((inner + uid).encode()).hexdigest()


def _fake_response(payload):
    resp = mock.Mock()
    resp.json.return_value = payload
    return resp


class ApplyCancelCrawlerTests(TestCase):
    """爬虫层：请求参数拼装"""

    def _service_with_response(self, payload):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        session = mock.Mock()
        session.post.return_value = _fake_response(payload)
        service.session = session
        return service

    def test_params_payload(self):
        service = self._service_with_response({'Result': '1'})
        result = service.apply_cancel_order(
            order_id='10717695025313439830', pay_pass='128524',
            uid='USR2025112802644', token='tok', user_id=24544092,
            flag=0, pay_level_bal=0, rep_ensure_bal=0,
            comment='撤销说明', revoke_price=2)
        self.assertEqual(result['code'], 0)
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['ODSerialNo'], '10717695025313439830')
        self.assertEqual(sent['Flag'], '0')
        self.assertEqual(sent['PayLevelBal'], '0')
        self.assertEqual(sent['RepEnsureBal'], '0')
        self.assertEqual(sent['Comment'], '撤销说明')
        self.assertEqual(sent['RevokePrice'], '2')
        self.assertEqual(sent['UserID'], '24544092')
        self.assertEqual(sent['PayPass'], _pwd_hash('128524', 'USR2025112802644'))

    def test_upstream_failure(self):
        service = self._service_with_response({'Result': '0', 'Err': '订单状态不允许撤销'})
        result = service.apply_cancel_order(order_id='o', pay_pass='p', uid='u',
                                            token='t', user_id=1)
        self.assertEqual(result['code'], 1)
        self.assertEqual(result['message'], '订单状态不允许撤销')


class ApplyCancelUtilsTests(TestCase):
    """业务层：撤销说明拼装 + 凭证图片上传"""

    def test_comment_and_image_upload(self):
        calls = []

        def fake_call(method, **kwargs):
            calls.append((method, kwargs))
            return True, {'code': 0, 'message': 'ok', 'data': {}}

        with mock.patch.object(dlt_utils, '_call', side_effect=fake_call):
            ok, _ = dlt_utils.apply_cancel_order(
                'o', '128524', 'USR1', 'tok', '24544092',
                desire='0', progress='有进度', comment='打手一直不上号',
                pay_level_bal=2, image='https://img/x.png')
        self.assertTrue(ok)
        method, kwargs = calls[0]
        self.assertEqual(method, 'apply_cancel_order')
        self.assertIn('目前进度:有进度', kwargs['comment'])
        self.assertIn('发单者愿意支付代练费2元', kwargs['comment'])
        self.assertIn('补充描述:打手一直不上号', kwargs['comment'])
        self.assertEqual(kwargs['pay_level_bal'], 2)
        # 图片以「撤销」留言上传
        self.assertEqual(calls[1][0], 'upload_image_in_order_comment')
        self.assertEqual(calls[1][1]['msg'], '撤销')
        self.assertEqual(calls[1][1]['image_path'], 'https://img/x.png')

    def test_image_upload_failure_only_warns(self):
        results = [(True, {'code': 0, 'message': 'ok', 'data': {}}),
                   (True, {'code': 1, 'message': '图片过大'})]
        with mock.patch.object(dlt_utils, '_call', side_effect=results):
            ok, res = dlt_utils.apply_cancel_order('o', 'p', 'USR1', 'tok', '1',
                                                   image='x.png')
        self.assertTrue(ok)                      # 撤销已成功，不因图片失败而报错
        self.assertIn('图片上传失败', res['message'])


class ApplyCancelViewTests(TestCase):
    """视图契约：必填校验 / 枚举校验 / 默认值"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/orders/apply-cancel'

    def _post(self, **data):
        return dlt_request.apply_cancel_view(self.factory.post(self.url, data))

    @mock.patch.object(dlt_request.utils, 'apply_cancel_order',
                       return_value=(True, {'code': 0, 'message': 'ok', 'data': {}}))
    def test_success_and_defaults(self, mocked):
        body = json.loads(self._post(order_id='o', pay_pass='p', uid='u').content)
        self.assertEqual(body['code'], 10000)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['flag'], 0)
        self.assertEqual(kwargs['desire'], '2')
        self.assertEqual(kwargs['progress'], '无进度')

    def test_missing_order_id(self):
        body = json.loads(self._post(pay_pass='p', uid='u').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('order_id', body['msg'])

    def test_missing_uid(self):
        body = json.loads(self._post(order_id='o', pay_pass='p').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('uid', body['msg'])

    def test_invalid_desire(self):
        body = json.loads(self._post(order_id='o', pay_pass='p', uid='u', desire='9').content)
        self.assertEqual(body['code'], 20003)

    def test_invalid_progress(self):
        body = json.loads(self._post(order_id='o', pay_pass='p', uid='u', progress='乱写').content)
        self.assertEqual(body['code'], 20003)
