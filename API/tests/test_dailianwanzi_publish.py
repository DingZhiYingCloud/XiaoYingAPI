"""代练丸子「发布订单」单元测试

用假的上游响应驱动完整链路（不触网、不产生真实订单），校验：
- multiTaskInfo 按字段类型拼装（段位 / 下拉 / 数字）
- 标题默认后缀（私单勿接，指定单，接了扣除双金）
- 创建订单参数（区服三元组、账密上号、不加急服务包、档位字段）
- 必填项缺失时的拦截
"""
from unittest import mock

from django.test import TestCase

from API.apis.DaiLianWanZi import utils as dlwz_utils

Service = dlwz_utils._dlwz_business_class


def _resp(data):
    return {"code": 10000, "data": data}


_GAMES = {"hotGame": [{"id": 1, "name": "王者", "icon": "https://x/icon.png"}], "gridAllList": []}
_REGIONS = {"region": [{"regionId": 2, "regionName": "安卓QQ"}],
            "regionServer": [{"regionId": 2, "children": [{"serverId": 122, "serverName": "默认服"}]}]}
_TYPES = {"typeList": [{"id": 1, "name": "排位"}]}
_SUB_TYPES = {"list": [{
    "id": 398, "name": "起止段位", "type": 6, "isMust": 1, "code": "C1", "sort": 1, "useType": 2,
    "levelList": [
        {"text": "青铜", "children": [
            {"text": "青铜3段", "children": [{"id": 56034, "text": "0星", "startNum": 1}]}]},
        {"text": "王者", "children": [{"id": 56208, "text": "50星", "startNum": 151}]},
    ],
}]}


class PublishOrderTests(TestCase):
    def _service(self):
        service = Service()
        service.partner_device = "12345678901234567890"
        return service

    def _fake_post(self, captured, sub_types=_SUB_TYPES):
        def fake_post(path, data_params=None, authorization=None, parse=True):
            if path == "/game/v3/all":
                return _resp(_GAMES)
            if path == "/game/regionServer":
                return _resp(_REGIONS)
            if path == "/game/v3/levelingType":
                return _resp(_TYPES)
            if path == "/gameLevelSubTypes/v3/list":
                return _resp(sub_types)
            if path == "/merchant/transPriceCal":
                captured["_transPriceCal"] = data_params or {}
                return _resp({"hasTrans": 1, "gameId": 1, "multiTaskInfo": [], "tempType": 6})
            if path == "/merchant/genTitle":
                return _resp({"title": "【排位】青铜3段0星-王者50星"})
            if path == "/merchant/slicePriceCal":
                return _resp({"categoryPriceList": [{"merchantTranslateId": 3, "type": 7}]})
            if path == "/game/order/explain":
                return _resp({"explain": "默认说明", "requirement": "默认要求"})
            if path == "/order/action/merchant/store":
                captured.update(data_params or {})
                return _resp({"tradeNo": "T1", "status": 2})
            raise AssertionError("unexpected path " + path)
        return fake_post

    def test_publish_builds_expected_body(self):
        service = self._service()
        captured = {}
        with mock.patch.object(service, "_post", side_effect=self._fake_post(captured)):
            result = service.publish_order(
                "token", game_id=1,
                tasks=[{"name": "起止段位", "start": "青铜3段0星", "end": "王者50星"}],
                amount=2, hour=3, security_deposit=2, efficiency_deposit=2,
                region_name="安卓QQ", leveling_type_name="排位",
                title_suffix="私单勿接，指定单，接了扣除双金",
                login_method=2, game_account="13712992620", game_password="qwe12345",
                game_role="小影", player_phone="13712992781",
                contact_phone="13712992611", contact_qq="13712991205",
            )

        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["trade_no"], "T1")
        # 标题后缀 + 区服三元组 + 段位选项（multiTaskInfo 发给 transPriceCal）
        self.assertEqual(captured["title"], "【排位】青铜3段0星-王者50星 私单勿接，指定单，接了扣除双金")
        self.assertEqual(captured["gameRegionServer"], [1, 2, 122])
        self.assertEqual(captured["_transPriceCal"]["multiTaskInfo"][0]["options"],
                         [{"id": 56034, "startNum": 1, "name": "青铜3段0星"},
                          {"id": 56208, "startNum": 151, "name": "王者50星"}])
        # 账密上号 + 无加急服务包 + 档位字段
        self.assertEqual(captured["gameAccount"], "13712992620")
        self.assertEqual(captured["gamePassword"], "qwe12345")
        self.assertNotIn("insuranceProductId", captured)
        self.assertEqual(captured["merchantTranslateId"], 3)
        self.assertEqual(captured["channelConfigType"], 7)

    def test_scan_login_uses_placeholder_account(self):
        service = self._service()
        captured = {}
        with mock.patch.object(service, "_post", side_effect=self._fake_post(captured)):
            service.publish_order(
                "token", game_id=1,
                tasks=[{"name": "起止段位", "start": "青铜3段0星", "end": "王者50星"}],
                amount=2, hour=3, security_deposit=2, efficiency_deposit=2,
                region_name="安卓QQ", leveling_type_name="排位", login_method=1,
            )
        self.assertEqual(captured["gameAccount"], "扫码上号")
        self.assertEqual(captured["gameRole"], "扫码上号")

    def test_missing_required_task_is_rejected(self):
        service = self._service()
        captured = {}
        with mock.patch.object(service, "_post", side_effect=self._fake_post(captured)):
            result = service.publish_order(
                "token", game_id=1, tasks=[], amount=2, hour=3,
                security_deposit=2, efficiency_deposit=2)
        self.assertEqual(result["code"], 1)
        self.assertIn("起止段位", result["message"])
        self.assertEqual(captured, {})   # 未走到创建订单

    def test_unknown_region_is_rejected(self):
        service = self._service()
        captured = {}
        with mock.patch.object(service, "_post", side_effect=self._fake_post(captured)):
            result = service.publish_order(
                "token", game_id=1,
                tasks=[{"name": "起止段位", "start": "青铜3段0星", "end": "王者50星"}],
                amount=2, hour=3, security_deposit=2, efficiency_deposit=2,
                region_name="不存在的大区", leveling_type_name="排位")
        self.assertEqual(result["code"], 1)
        self.assertIn("区服", result["message"])


class CancelOrderTests(TestCase):
    def test_cancel_sends_trade_no_to_upstream(self):
        service = Service()
        captured = {}

        def fake_post(path, data_params=None, authorization=None, parse=True):
            captured["path"] = path
            captured["data"] = data_params or {}
            return {"code": 0, "message": "Success", "data": {"tradeNo": "T1"}}

        with mock.patch.object(service, "_post", side_effect=fake_post):
            result = service.cancel_order("token", "T1")

        self.assertEqual(captured["path"], "/order/action/cancel")
        self.assertEqual(captured["data"], {"tradeNo": "T1"})
        self.assertEqual(result["code"], 0)
