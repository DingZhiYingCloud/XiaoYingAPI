"""代练通「发布订单」接口单元测试

覆盖场景：
- 爬虫：字段映射、Actors 的 Base64 组装、支付密码哈希、ExtStr
- 爬虫异常：上游返回结构异常时返回失败
- 视图契约：必填校验、数值校验、默认值
"""
import base64
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

REQUIRED = {'title': '指定单测试', 'price': '2', 'time_limit': '3', 'game_mobile': '13712992621',
            'game_account': '13712992620', 'game_password': 'qwe12345',
            'game_author_name': '小影', 'requirements': '指定单，私接扣除全部保证金'}


def _fake_response(payload):
    resp = mock.Mock()
    resp.json.return_value = payload
    return resp


def _pwd_hash(pwd, uid):
    """前端 get_pwd_hash：md5(md5(pwd) + uid)"""
    inner = hashlib.md5(pwd.encode()).hexdigest()
    return hashlib.md5((inner + uid).encode()).hexdigest()


class PublishOrderCrawlerTests(TestCase):
    def _service_with_response(self, payload):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        session = mock.Mock()
        session.post.return_value = _fake_response(payload)
        service.session = session
        return service

    def test_params_actors_and_paypass(self):
        service = self._service_with_response({'Result': '1', 'UID': 'USR1'})
        result = service.publish_order(
            title='指定单测试', price=2, time_limit=3, ensure1=10, ensure2=10,
            game_mobile='13712992621', pay_pass='128524', uid='USR2025111906640',
            game_account='13712992620', game_password='qwe12345', game_author_name='小影',
            requirements='指定单，私接扣除全部保证金', mobile='13712992721', user_id=24479174,
            game_extra='150',   # 爬虫层不做游戏判断，由业务层按游戏解析后传入（王者荣耀=铭文等级150）
        )
        self.assertEqual(result['code'], 0)
        sent = service.session.post.call_args.kwargs['data']
        self.assertEqual(sent['Title'], '指定单测试')
        self.assertEqual(sent['Price'], '2')
        self.assertEqual(sent['TimeLimit'], '3')
        self.assertEqual(sent['Ensure1'], '10')
        self.assertEqual(sent['Ensure2'], '10')
        self.assertEqual(sent['GameMobile'], '13712992621')
        self.assertEqual(sent['Mobile'], '13712992721')
        self.assertEqual(sent['ZoneServerID'], '107103017095500')
        self.assertEqual(sent['LevelType2'], '14')
        self.assertEqual(sent['UserID'], '24479174')
        self.assertEqual(sent['PayPass'], _pwd_hash('128524', 'USR2025111906640'))
        # Actors = base64(游戏账号|*|密码|*|角色名|*|铭文等级150|*|要求)
        decoded = base64.b64decode(sent['Actors']).decode('utf-8')
        self.assertEqual(
            decoded,
            '13712992620|*|qwe12345|*|小影|*|150|*|指定单，私接扣除全部保证金')
        # ExtStr 内嵌要求文案
        self.assertIn('指定单，私接扣除全部保证金', sent['ExtStr'])

    def test_empty_pay_pass_sends_empty(self):
        service = self._service_with_response({'Result': '1'})
        service.publish_order(
            title='t', price=2, time_limit=3, ensure1=0, ensure2=0, game_mobile='m',
            pay_pass='', uid='USR1', game_account='a', game_password='p',
            game_author_name='r', requirements='q', user_id=1,
        )
        self.assertEqual(service.session.post.call_args.kwargs['data']['PayPass'], '')

    def test_bad_response_returns_error(self):
        service = self._service_with_response({'unexpected': True})
        result = service.publish_order(
            title='t', price=2, time_limit=3, ensure1=0, ensure2=0, game_mobile='m',
            pay_pass='', uid='USR1', game_account='a', game_password='p',
            game_author_name='r', requirements='q', user_id=1,
        )
        self.assertEqual(result['code'], 1)


class PublishOrderViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/orders/publish'

    def _post(self, **data):
        return dlt_request.publish_order_view(self.factory.post(self.url, data))

    @mock.patch('API.apis.DaiLianTong.utils.publish_order')
    def test_success_and_defaults(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'ok', 'data': {'SerialNo': 'X'}})
        body = json.loads(self._post(**REQUIRED, ensure1='10', ensure2='10',
                                     mobile='13712992721', pay_pass='128524').content)
        self.assertEqual(body['code'], 10000)
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['title'], '指定单测试')
        self.assertEqual(kwargs['price'], 2)
        self.assertEqual(kwargs['time_limit'], 3)
        self.assertEqual(kwargs['ensure1'], 10)
        self.assertEqual(kwargs['ensure2'], 10)
        self.assertEqual(kwargs['mobile'], '13712992721')
        self.assertEqual(kwargs['game_id'], 0)
        self.assertEqual(kwargs['zone_server_id'], '')   # 由业务层按 game_id 解析
        self.assertEqual(kwargs['level_type2'], '')      # 由业务层按游戏取默认
        self.assertEqual(kwargs['game_extra'], '')       # 由业务层按游戏取默认

    def test_missing_title(self):
        body = json.loads(self._post(price='2', time_limit='3').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('title', body['msg'])

    def test_missing_price(self):
        params = dict(REQUIRED)
        params.pop('price')
        self.assertEqual(json.loads(self._post(**params).content)['code'], 20001)

    def test_invalid_price(self):
        params = dict(REQUIRED, price='abc')
        self.assertEqual(json.loads(self._post(**params).content)['code'], 20002)

    def test_invalid_ensure(self):
        params = dict(REQUIRED, ensure1='x')
        self.assertEqual(json.loads(self._post(**params).content)['code'], 20002)

    def test_invalid_user_id(self):
        params = dict(REQUIRED, user_id='abc')
        self.assertEqual(json.loads(self._post(**params).content)['code'], 20002)

    @mock.patch('API.apis.DaiLianTong.utils.publish_order')
    def test_upstream_failure(self, mocked):
        mocked.return_value = (False, '余额不足')
        body = json.loads(self._post(**REQUIRED).content)
        self.assertEqual(body['code'], 40001)
        self.assertEqual(body['msg'], '余额不足')


class SupportedGameTests(TestCase):
    """游戏表单声明（games/ 包）：启用清单、按游戏默认值、未支持游戏拒绝"""

    def test_enabled_games(self):
        # 王者荣耀 + 三角洲行动（自定义发布已真机验证）
        self.assertEqual([p.name for p in dlt_utils.enabled_games()], ['王者荣耀', '三角洲行动'])
        self.assertEqual(dlt_utils.supported_game_options(),
                         [{'value': '107', 'label': '王者荣耀'},
                          {'value': '394', 'label': '三角洲行动'}])

    def test_unsupported_game_rejected(self):
        ok, msg = dlt_utils.publish_order(
            title='t', price=2, time_limit=3, ensure1=0, ensure2=0, game_mobile='m',
            game_account='a', game_password='p', game_author_name='r', requirements='q',
            game_id=999)
        self.assertFalse(ok)
        self.assertIn('暂不支持该游戏', msg)

    def test_defaults_per_game(self):
        self.assertEqual(dlt_utils.game_profile(107)['game_extra'], '150')
        self.assertEqual(dlt_utils.game_profile(999)['name'], '王者荣耀')   # 未支持 → 回落默认

    def test_zone_server_default(self):
        # 只选游戏时直接用该游戏声明里的默认区服（不请求上游）
        self.assertEqual(dlt_utils._resolve_zone_server_id(107, ''),
                         dlt_utils.DEFAULT_ZONE_SERVER_ID)


class ZoneServerResolveTests(TestCase):
    """zone_server_id 解析：显式优先 → 按 game_id 取该游戏首个区服 → 默认"""

    def test_explicit_wins(self):
        self.assertEqual(dlt_utils._resolve_zone_server_id(0, '156147517726600'),
                         '156147517726600')

    @mock.patch('API.apis.DaiLianTong.utils._game_zone_server_list')
    def test_by_game_id(self, mocked):
        mocked.return_value = [{
            'GameID': 156, 'GameName': '英雄联盟手游',
            'ZoneList': [{'ZoneName': '安卓QQ',
                          'ServerList': [{'ServerName': '默认服', 'Code': '156147517726600'}]}],
        }]
        self.assertEqual(dlt_utils._resolve_zone_server_id(156, ''), '156147517726600')

    @mock.patch('API.apis.DaiLianTong.utils._game_zone_server_list')
    def test_by_game_and_zone_type(self, mocked):
        mocked.return_value = [{
            'GameID': 107, 'GameName': '王者荣耀',
            'ZoneList': [
                {'ZoneName': '安卓QQ', 'ServerList': [{'ServerName': '默认服', 'Code': '107103017095500'}]},
                {'ZoneName': '苹果微信', 'ServerList': [{'ServerName': '默认服', 'Code': '107205018569600'}]},
            ],
        }]
        self.assertEqual(dlt_utils._resolve_zone_server_id(107, '', '苹果微信'), '107205018569600')

    @mock.patch('API.apis.DaiLianTong.utils._game_zone_server_list')
    def test_fallback_default(self, mocked):
        mocked.return_value = []
        self.assertEqual(dlt_utils._resolve_zone_server_id(0, ''),
                         dlt_utils.DEFAULT_ZONE_SERVER_ID)
