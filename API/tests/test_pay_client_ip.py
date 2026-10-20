"""支付 client_ip 解析与入参校验 回归测试

背景：易支付会按付款人 IP 做风控，传入 127.0.0.1 / 内网 / 公共 DNS 时会返回
「系统异常无法完成付款」。这里锁定三件事：
- Cloudflare 场景优先取 CF-Connecting-IP，而不是 XFF 末段的 CF 边缘 IP；
- XFF 里混有内网 / 回环地址时，取从后往前第一个公网地址；
- /api/pay/create 允许显式传 client_ip，并拒绝非法 / 内网地址。
"""
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.pay.providers.base import PayError
from API.apis.pay.request import _public_ip, create_view
from API.common.ip_guard import client_ip
from API.models import User


class ClientIpTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_cloudflare_header_wins(self):
        request = self.rf.get('/', HTTP_CF_CONNECTING_IP='183.14.132.51',
                              HTTP_X_FORWARDED_FOR='183.14.132.51, 172.67.173.120',
                              REMOTE_ADDR='172.67.173.120')
        self.assertEqual(client_ip(request), '183.14.132.51')

    def test_skips_private_hop_in_xff(self):
        """CF 头是 127.0.0.1（隧道回源）时，XFF 从后往前找第一个公网 IP"""
        request = self.rf.get('/', HTTP_CF_CONNECTING_IP='127.0.0.1',
                              HTTP_X_FORWARDED_FOR='183.14.132.51, 172.67.173.120, 127.0.0.1',
                              REMOTE_ADDR='127.0.0.1')
        self.assertEqual(client_ip(request), '172.67.173.120')

    def test_falls_back_to_last_when_all_private(self):
        request = self.rf.get('/', HTTP_X_FORWARDED_FOR='10.0.0.1, 127.0.0.1',
                              REMOTE_ADDR='127.0.0.1')
        self.assertEqual(client_ip(request), '127.0.0.1')


class PublicIpValidationTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_public_ip_only(self):
        self.assertEqual(_public_ip('183.14.132.51'), '183.14.132.51')
        self.assertEqual(_public_ip('114.114.114.114'), '114.114.114.114')  # 公网地址本身合法
        self.assertIsNotNone(_public_ip('240e:3b0:1234:5678::1'))
        for bad in ('127.0.0.1', '10.0.0.1', '192.168.1.1', 'not-an-ip'):
            self.assertIsNone(_public_ip(bad), bad)

    def test_create_rejects_private_client_ip(self):
        user = User.objects.create(account='payer1', password='x')
        request = self.rf.post('/api/pay/create', {
            'pay_type': 'alipay', 'amount': '1.00', 'user_id': str(user.pk),
            'client_ip': '127.0.0.1',
        })
        response = create_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('"code": 20003', response.content.decode())

    def test_create_passes_valid_client_ip(self):
        user = User.objects.create(account='payer2', password='x')
        captured = {}

        def fake_create_order(**kwargs):
            captured.update(kwargs)
            raise PayError('stop-for-test')

        request = self.rf.post('/api/pay/create', {
            'pay_type': 'alipay', 'amount': '1.00', 'user_id': str(user.pk),
            'provider': 'ezfp', 'client_ip': '183.14.132.51',
        })
        request.auth_app = None      # 正常由 ApiAuthMiddleware 注入
        with mock.patch('API.apis.pay.request.service.create_order',
                        side_effect=fake_create_order):
            response = create_view(request)
        self.assertEqual(captured.get('client_ip'), '183.14.132.51')
        self.assertIn('stop-for-test', response.content.decode())
