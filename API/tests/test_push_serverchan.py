"""消息推送 push（Server酱线路）单元测试

全程 mock 上游请求，不触网、不产生真实推送。
覆盖：请求地址拼装、参数校验、未配置 SendKey、成功、上游拒绝、落库留痕、
      隐藏 IP、端对端加密、推送状态查询。
"""
import base64
import hashlib
import json
from unittest import mock

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from django.test import RequestFactory, TestCase

from API.apis.push.serverchan import request as push_request
from API.apis.push.serverchan import utils as push_utils
from API.models import PushLog


def _post(**data):
    return RequestFactory().post('/api/push/serverchan/send', data)


def _get(**params):
    return RequestFactory().get('/api/push/serverchan/status', params)


def _body(response):
    return json.loads(response.content)


def _decrypt(ciphertext, password, key):
    """加密的逆运算（仅测试用）：还原 encrypt_desp 的明文，校验加密口径"""
    digest = lambda text: hashlib.md5(text.encode('utf-8')).hexdigest()[:16].encode('ascii')
    cipher = AES.new(digest(password), AES.MODE_CBC, digest('SCT' + push_utils.uid_of(key)))
    raw = unpad(cipher.decrypt(base64.b64decode(ciphertext)), AES.block_size)
    return base64.b64decode(raw).decode('utf-8')


class EndpointTests(TestCase):
    def test_sct_endpoint(self):
        self.assertEqual(push_utils._endpoint('SCT123abc'),
                         'https://sctapi.ftqq.com/SCT123abc.send')

    def test_sctp_endpoint(self):
        self.assertEqual(push_utils._endpoint('sctp9988tXXXX'),
                         'https://9988.push.ft07.com/send/sctp9988tXXXX.send')


class SendViewTests(TestCase):
    def test_missing_title(self):
        body = _body(push_request.send_view(_post(desp='x')))
        self.assertEqual(body['code'], 20001)

    def test_title_too_long(self):
        body = _body(push_request.send_view(_post(title='a' * (push_utils.TITLE_MAX_LEN + 1))))
        self.assertEqual(body['code'], 20003)

    def test_title_with_newline(self):
        body = _body(push_request.send_view(_post(title='a\nb')))
        self.assertEqual(body['code'], 20002)

    @mock.patch('API.apis.push.serverchan.utils.sendkey', return_value='')
    def test_not_configured(self, _key):
        body = _body(push_request.send_view(_post(title='测试', desp='正文')))
        self.assertEqual(body['code'], 40001)
        log = PushLog.objects.get()
        self.assertFalse(log.ok)
        self.assertEqual(log.title, '测试')

    @mock.patch('API.apis.push.serverchan.utils.sendkey', return_value='SCT1')
    @mock.patch('API.apis.push.serverchan.utils.requests.post')
    def test_success_logs_and_returns_pushid(self, post, _key):
        post.return_value = mock.Mock(json=lambda: {
            'code': 0, 'message': '',
            'data': {'pushid': 'P1', 'readkey': 'R1'}})
        body = _body(push_request.send_view(_post(title='告警', desp='磁盘 92%')))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data'], {'pushid': 'P1', 'readkey': 'R1', 'encrypted': False})
        log = PushLog.objects.get()
        self.assertTrue(log.ok)
        self.assertEqual(log.pushid, 'P1')
        self.assertEqual(log.code, 0)

    @mock.patch('API.apis.push.serverchan.utils.sendkey', return_value='SCT1')
    @mock.patch('API.apis.push.serverchan.utils.requests.post')
    def test_noip_and_channel_payload(self, post, _key):
        post.return_value = mock.Mock(json=lambda: {
            'code': 0, 'message': '', 'data': {'pushid': 'P1', 'readkey': 'R1'}})
        _body(push_request.send_view(_post(title='告警', desp='x', noip='1', channel='9')))
        sent = post.call_args.kwargs['data']
        self.assertEqual(sent['noip'], 1)
        self.assertEqual(sent['channel'], '9')

    @mock.patch('API.apis.push.serverchan.utils.sendkey', return_value='SCT433147abc')
    @mock.patch('API.apis.push.serverchan.utils.requests.post')
    def test_encrypt_round_trip_and_logs_ciphertext(self, post, _key):
        post.return_value = mock.Mock(json=lambda: {
            'code': 0, 'message': '', 'data': {'pushid': 'P1', 'readkey': 'R1'}})
        body = _body(push_request.send_view(_post(title='告警', desp='机密内容',
                                                  encrypt_password='pw123')))
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['encrypted'])
        sent = post.call_args.kwargs['data']
        self.assertEqual(sent['encoded'], 1)
        self.assertNotEqual(sent['desp'], '机密内容')
        self.assertEqual(_decrypt(sent['desp'], 'pw123', 'SCT433147abc'), '机密内容')
        # 日志记录的是实际发出的密文，不是明文
        self.assertEqual(PushLog.objects.get().content, sent['desp'])

    def test_encrypt_without_desp_rejected(self):
        body = _body(push_request.send_view(_post(title='告警', encrypt_password='pw')))
        self.assertEqual(body['code'], 20003)

    @mock.patch('API.apis.push.serverchan.utils.sendkey', return_value='SCT1')
    @mock.patch('API.apis.push.serverchan.utils.requests.post')
    def test_upstream_error(self, post, _key):
        post.return_value = mock.Mock(json=lambda: {
            'code': 40001, 'message': '超过每日发送上限',
            'data': {'error': 'DAILY_LIMIT', 'errno': 40001}})
        body = _body(push_request.send_view(_post(title='告警')))
        self.assertEqual(body['code'], 40001)
        self.assertIn('上限', body['msg'])
        log = PushLog.objects.get()
        self.assertFalse(log.ok)
        self.assertEqual(log.code, 40001)


class QueryStatusTests(TestCase):
    def test_missing_params(self):
        body = _body(push_request.status_view(_get(pushid='1')))
        self.assertEqual(body['code'], 20001)

    @mock.patch('API.apis.push.serverchan.utils.requests.get')
    def test_success(self, get):
        get.return_value = mock.Mock(json=lambda: {
            'code': 0, 'message': '',
            'data': {'id': '1', 'wxstatus': '{"errcode":0}'}})
        body = _body(push_request.status_view(_get(pushid='1', readkey='r')))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['wxstatus'], '{"errcode":0}')

    @mock.patch('API.apis.push.serverchan.utils.requests.get')
    def test_upstream_error(self, get):
        get.return_value = mock.Mock(json=lambda: {
            'code': 40001, 'message': 'readkey 无效', 'data': None})
        body = _body(push_request.status_view(_get(pushid='1', readkey='bad')))
        self.assertEqual(body['code'], 40001)
        self.assertIn('readkey', body['msg'])
