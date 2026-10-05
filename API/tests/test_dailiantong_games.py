"""代练通「获取全部游戏」接口单元测试

覆盖场景：
- 爬虫合并逻辑：游戏清单 + 各游戏订单数按 GameID 合并、名称映射、按订单数降序
- 爬虫异常：上游返回结构异常 / 无订单时返回失败
- 视图契约：成功返回 10000、上游失败返回 40001、非 GET 方法返回 405
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


class GamesCrawlerTests(TestCase):
    """爬虫层：两接口合并逻辑"""

    def _service_with_responses(self, *responses):
        # 独立于 .env：构造实例时临时提供签名密钥
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            service = DaiLianTongService()
        session = mock.Mock()
        session.post.side_effect = list(responses)
        service.session = session
        return service

    def test_merge_and_sort(self):
        games = [
            {'GameID': 107, 'GameName': '王者荣耀'},
            {'GameID': 394, 'GameName': '三角洲行动'},
            {'GameID': 999, 'GameName': '无订单游戏'},
        ]
        counts = {'LevelOrderCountGame': [
            {'GameID': 107, 'iCount': 5},
            {'GameID': 394, 'iCount': 10},
        ]}
        service = self._service_with_responses(_fake_response(games), _fake_response(counts))

        result = service.get_games()

        self.assertEqual(result['code'], 0)
        # 仅保留有订单的游戏，按订单数降序
        self.assertEqual(result['data'], [
            {'game_id': 394, 'game_name': '三角洲行动', 'order_count': 10},
            {'game_id': 107, 'game_name': '王者荣耀', 'order_count': 5},
        ])

    def test_unknown_game_name_is_empty(self):
        games = [{'GameID': 107, 'GameName': '王者荣耀'}]
        counts = {'LevelOrderCountGame': [{'GameID': 888, 'iCount': 3}]}
        service = self._service_with_responses(_fake_response(games), _fake_response(counts))

        result = service.get_games()

        self.assertEqual(result['code'], 0)
        self.assertEqual(result['data'][0]['game_name'], '')

    def test_bad_games_response_returns_error(self):
        service = self._service_with_responses(_fake_response({'unexpected': True}))
        result = service.get_games()
        self.assertEqual(result['code'], 1)

    def test_empty_counts_returns_error(self):
        service = self._service_with_responses(
            _fake_response([{'GameID': 107, 'GameName': '王者荣耀'}]),
            _fake_response({'LevelOrderCountGame': []}),
        )
        result = service.get_games()
        self.assertEqual(result['code'], 1)


class GamesViewTests(TestCase):
    """视图层：响应契约"""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/dlt/games'

    @mock.patch('API.apis.DaiLianTong.utils.get_games')
    def test_success(self, mocked):
        mocked.return_value = (True, {
            'code': 0, 'message': '获取成功',
            'data': [{'game_id': 107, 'game_name': '王者荣耀', 'order_count': 5}],
        })
        resp = dlt_request.games_view(self.factory.get(self.url))
        body = json.loads(resp.content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data'][0]['game_name'], '王者荣耀')

    @mock.patch('API.apis.DaiLianTong.utils.get_games')
    def test_upstream_failure(self, mocked):
        mocked.return_value = (False, '获取游戏列表失败')
        resp = dlt_request.games_view(self.factory.get(self.url))
        body = json.loads(resp.content)
        self.assertEqual(body['code'], 40001)
        self.assertEqual(body['msg'], '获取游戏列表失败')

    def test_method_not_allowed(self):
        resp = dlt_request.games_view(self.factory.post(self.url))
        self.assertEqual(resp.status_code, 405)
