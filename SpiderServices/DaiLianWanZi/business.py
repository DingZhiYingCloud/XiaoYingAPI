"""代练丸子「商家版」爬虫（bd1.llwanzi.com）

与打手版（home.py，m.llwanzi.com）**分开维护**：商家版的基址与公共参数
（partnerChannel）都不同，独立成模块后两条线路互不影响。

对外能力：
- 我的订单：订单分类（tab）、订单列表、取消订单
- 发单：全部游戏、发单选项（代练类型 / 区服 / 段位等子类型）、发布订单

发单链路（与网页端一致）：
    gameLevelSubTypes → transPriceCal → genTitle → slicePriceCal/specialPrice → storeOrder
其中 transPriceCal 的响应会被上游「规整」成下发参数（currentLevel/targetLevel/multiTaskInfo 等），
后续 genTitle / slicePriceCal / storeOrder 都基于它。

通用工具（请求头 / 设备ID / 响应解析）复用同目录 utils.py，仅公共参数单独构造。
"""
import time

import requests

from .utils import (
    generate_device_id,
    get_mobile_headers,
    parse_response,
    response_dict,
)

# 商家版基址与公共参数（注意与打手版 m.llwanzi.com 不同）
BASE_URL = "https://bd1.llwanzi.com/api"
PARTNER_CHANNEL = "bd1.llwanzi.com"
PARTNER_VERSION = "4.0.0-4.9.47"

# 商家版固定参数（与网页端一致）
CHANNEL_TYPE = 2   # 渠道类型：2 = 商家版
TEMP_TYPE = 6      # 发单模板类型（上游固定值）
ORDER_TYPE_TRAIN = 1   # 订单类型：代练
ORDER_TYPE_PLAY = 2    # 订单类型：陪玩

# 凭证图片用途（sendImage 的 actionType）
IMAGE_ACTION_REVOCATION = 2   # 撤销凭证
IMAGE_ACTION_ARBITRATION = 4  # 仲裁凭证

_REQ_TIMEOUT = 15


# ==================== 子类型字段拼装（对齐网页端 getDopInputParamsList） ====================


def _iter_level_leaves(level_list):
    """遍历段位 levelList（大段 → 小段 → 星），产出 (显示名, 叶子节点)

    网页端层级不统一：多数大段（青铜/白银…）是三级（青铜 → 青铜3段 → 0星），
    王者等则是两级（王者 → 50星）。显示名统一为「去掉重复前缀后的拼接名」，
    例如 青铜3段 + 0星 = 青铜3段0星，王者 + 50星 = 王者50星。
    """
    for big in (level_list or []):
        big_text = (big.get('text') or '').strip()
        children = big.get('children') or []
        has_grand = any((child.get('children') or []) for child in children)
        if has_grand:
            for mid in children:
                mid_text = (mid.get('text') or '').strip()
                for star in (mid.get('children') or []):
                    yield f"{mid_text}{star.get('text') or ''}", star
        else:
            for star in children:
                yield f"{big_text}{star.get('text') or ''}", star


def _find_level(item, want):
    """按中文段位名（如「青铜3段0星」「王者50星」）解析出上游叶子节点"""
    want = (want or '').strip().replace(' ', '')
    for name, node in _iter_level_leaves(item.get('levelList')):
        if name.replace(' ', '') == want:
            return {'id': node.get('id'), 'startNum': node.get('startNum'), 'name': name}
    return None


def _find_option(item, want):
    """按中文选项名（如「代肝」「2格」）解析出上游选项对象（原样透传给上游）"""
    want = (want or '').strip()
    for option in (item.get('options') or []):
        if (option.get('name') or '').strip() == want:
            return option
    return None


def build_task_item(item, spec):
    """把一条「任务声明」并进上游子类型项，产出 multiTaskInfo 元素

    :param item: 上游子类型项（含 id/name/type/code/sort/useType/levelList/options）
    :param spec: 声明，形如 {'name': '起止段位', 'start': '青铜3段0星', 'end': '王者50星'}
                 或 {'name': '哈夫币(万)', 'value': 100} / {'name': '保险箱', 'value': '2格'}
    :return: multiTaskInfo 元素；字段不匹配 / 取值解析失败返回 None
    """
    out = {
        'id': item.get('id'), 'childId': item.get('childId'), 'code': item.get('code'),
        'gameLevelingTypeId': item.get('gameLevelingTypeId'), 'isChild': item.get('isChild'),
        'isMust': item.get('isMust'), 'name': item.get('name'), 'type': item.get('type'),
        'sort': item.get('sort'), 'useType': item.get('useType'),
    }
    item_type = item.get('type')
    if item_type == 6:                       # 6 = 段位区间（起止段位）
        start = _find_level(item, spec.get('start'))
        end = _find_level(item, spec.get('end'))
        if not start or not end:
            return None
        out['options'] = [start, end]
    elif item_type == 1:                     # 1 = 单选
        option = _find_option(item, spec.get('value'))
        if not option:
            return None
        out['options'] = [option]
    elif item_type == 5:                     # 5 = 数字
        value = spec.get('value')
        if value in (None, ''):
            return None
        out['selectVal'] = value
    else:
        return None
    return out


class DaiLianWanZiBusinessService:
    """代练丸子商家版（发单 / 商家侧）接口封装"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_mobile_headers())
        self.partner_device = generate_device_id()

    # ==================== 基础请求 ====================

    def _public_data(self, data_params=None, authorization=None):
        """构建商家版请求体：业务参数置顶层 + common 公共参数

        authorization 未带 "Bearer " 前缀时自动补齐（与打手版口径一致）。
        """
        common = {
            "partnerChannel": PARTNER_CHANNEL,
            "partner": "h5",
            "partnerVersion": PARTNER_VERSION,
            "partnerDevice": self.partner_device,
            "authorization": authorization,
            "timestamp": str(int(time.time() * 1000)),
        }
        if authorization and "Bearer" not in authorization:
            common["authorization"] = "Bearer " + authorization

        result = {"common": common}
        if data_params:
            data_params.update(result)
            return data_params
        return result

    def _post(self, path, data_params=None, authorization=None, parse=True):
        """POST 上游接口

        :param parse: True 走统一解析（返回 {code,message,data}）；False 返回原始 JSON
        """
        json_data = self._public_data(dict(data_params or {}), authorization=authorization)
        resp = self.session.post(f"{BASE_URL}{path}", json=json_data, timeout=_REQ_TIMEOUT)
        if parse:
            return parse_response(resp)
        try:
            return resp.json()
        except ValueError:
            return {}

    # ==================== 我的订单 ====================

    def get_order_tabs(self, authorization):
        """订单分类列表（我的订单页顶部 tab，含各分类订单数量）

        返回统一响应字典，成功时 data 为上游完整响应对象（分类在 data.tableList）。
        """
        return self._post("/order/user/orderTable", {"userType": 1},
                          authorization=authorization)

    def get_my_orders(self, authorization, table_type=0, keyword="", page=1, page_size=20):
        """我的订单列表（按分类筛选 + 关键词搜索 + 分页）

        :param table_type: 订单分类，取自 get_order_tabs（0=全部 / 101=待付待接 …）
        :param keyword: 搜索关键词（标题 / 角色名 / 订单号 / 号主手机）
        """
        return self._post("/order/user/list", {
            "pageNo": page, "pageSize": page_size, "userType": 1,
            "tableType": table_type, "keyWord": keyword,
        }, authorization=authorization)

    def get_order_images(self, authorization, trade_no):
        """订单图片列表（商家侧查看打手 / 发单方上传的图）

        每张图含 url / remark（如「首图」「申请验收」）/ initiator（1=发单方 2=接单方）。
        返回统一响应字典，成功时图片在 data.data.imagesList。
        """
        return self._post("/order/user/imgList", {"tradeNo": trade_no, "userType": 1},
                          authorization=authorization)

    def cancel_order(self, authorization, trade_no):
        """取消订单

        仅「待付待接」等可取消状态下可取消；取消后订单金额原路退回商家余额。
        返回统一响应字典，成功时 data 为上游完整响应对象。
        """
        return self._post("/order/action/cancel", {"tradeNo": trade_no},
                          authorization=authorization)

    # ==================== 接单大厅 ====================

    def search_orders(self, authorization, keyword="", game_id="", page=1, page_size=20):
        """接单大厅：订单搜索 / 列表

        :param keyword: 搜索关键词（标题 / 角色名 / 段位等；热搜词见 get_search_words）
        :param game_id: 选填，按游戏筛选
        注意：大厅分页参数是 pageNo / pageSize（不是 page / pageSize）。
        """
        params = {"pageNo": page, "pageSize": page_size}
        if keyword:
            params["keyword"] = keyword
        if game_id:
            params["gameId"] = game_id
        return self._post("/order/hall/searchList", params, authorization=authorization)

    def get_hall_order(self, authorization, trade_no):
        """大厅订单详情（接单前查看：金额 / 双金 / 区服 / 代练要求等）"""
        return self._post("/order/hall/detail", {"tradeNo": trade_no},
                          authorization=authorization)

    def get_search_words(self, authorization):
        """大厅热搜词（搜索框推荐词）"""
        return self._post("/order/hall/getSearchWordList", {}, authorization=authorization)

    def take_order(self, authorization, trade_no, take_password="", pay_password=""):
        """接单（真机接单：校验通过后立即接手，并从接单方余额冻结双金）

        :param take_password: 接单密码（指定单才需要，可先用 take_password_check 校验）
        :param pay_password: 支付密码（必填，用于冻结双金）
        上游 v2 接口「先校验后接手」，成功后订单进入「代练中」。
        """
        params = {"tradeNo": trade_no, "payPassword": pay_password}
        if take_password:
            params["takePassword"] = take_password
        return self._post("/order/action/v2/takeOrder", params, authorization=authorization)

    def take_password_check(self, authorization, trade_no, take_password):
        """接单密码校验（指定单接单前先校验）"""
        return self._post("/order/action/takePasswordCheck",
                          {"tradeNo": trade_no, "takePassword": take_password},
                          authorization=authorization)

    # ==================== 撤销 / 仲裁 ====================

    def send_order_images(self, authorization, trade_no, image_urls, action_type):
        """上传订单凭证图片（关联到订单，供撤销 / 仲裁使用）

        :param image_urls: 图片URL列表
        :param action_type: 用途：IMAGE_ACTION_REVOCATION(2)=撤销 / IMAGE_ACTION_ARBITRATION(4)=仲裁
        上游要求撤销 / 仲裁前先关联凭证图片，否则申请会被拒（「请补充传图」）。
        """
        return self._post("/order/action/sendImage", {
            "tradeNo": trade_no,
            "images": [{"url": url} for url in image_urls],
            "actionType": action_type,
        }, authorization=authorization)

    def apply_revocation(self, authorization, *, trade_no, initiator, reason, image_urls,
                         deposit=0, pay_amount=0, if_auto_arbitrate=0):
        """申请撤销（提前终止代练）

        :param initiator: 发起方：1=发单方 / 2=接单方
        :param image_urls: 凭证图片URL列表（上游要求至少一张，否则拒绝申请）
        :param deposit: 对方需赔付的保证金（对方无违规填 0）
        :param pay_amount: 我愿支付的代练费（打手未开始代练时填 0）
        :param reason: 订单进度 + 撤销理由（必填，客服据此处理）
        :param if_auto_arbitrate: 对方超时未处理是否自动转仲裁（接单方发起时可用，默认 0）
        申请后订单进入「撤销中」，需对方同意才生效。
        """
        self.send_order_images(authorization, trade_no, image_urls, IMAGE_ACTION_REVOCATION)
        return self._post("/order/action/applyRevocation", {
            "tradeNo": trade_no, "initiator": initiator, "deposit": deposit,
            "payAmount": pay_amount, "reason": reason, "ifAutoArbitrate": if_auto_arbitrate,
        }, authorization=authorization)

    def agree_revocation(self, authorization, trade_no, pay_password=""):
        """同意撤销（对方发起撤销后本方同意；生效后按申请单的资金分配方案结算）

        :param pay_password: 支付密码（发单方同意时上游要求必填；接单方可不填）
        """
        params = {"tradeNo": trade_no}
        if pay_password:
            params["payPassword"] = pay_password
        return self._post("/order/action/agreeRevocation", params,
                          authorization=authorization)

    def cancel_revocation(self, authorization, trade_no):
        """取消撤销（撤回已提交的撤销申请）"""
        return self._post("/order/action/cancelRevocation", {"tradeNo": trade_no},
                          authorization=authorization)

    def apply_arbitration(self, authorization, *, trade_no, initiator, reason, image_urls,
                          amount=0, deposit=0, opera_type=0):
        """申请平台仲裁

        :param initiator: 操作方：1=发单方 / 2=接单方
        :param image_urls: 举证图片URL列表（上游要求至少一张，否则拒绝申请）
        :param amount: 争议代练费
        :param deposit: 争议赔付保证金
        :param opera_type: 操作类型（上游传 0/1，对应页面是否二次确认）
        """
        self.send_order_images(authorization, trade_no, image_urls, IMAGE_ACTION_ARBITRATION)
        return self._post("/order/action/applyArbitration", {
            "tradeNo": trade_no, "initiator": initiator, "deposit": deposit,
            "amount": amount, "reason": reason, "operaType": opera_type,
        }, authorization=authorization)

    # ==================== 验收 / 结算 ====================

    def accept_completion(self, authorization, trade_no, pay_password):
        """同意验收（发单方同意打手的完单申请 → 订单结算，款项放给打手）

        :param pay_password: 支付密码（上游必填，明文下发，与接单一致）
        返回统一响应字典，成功时 data 为上游完整响应对象。
        """
        return self._post("/order/action/acceptCompletion", {
            "tradeNo": trade_no, "payPassword": pay_password,
        }, authorization=authorization)

    # ==================== 发单：选项查询 ====================

    def get_games(self, authorization):
        """全部游戏（仅 id + 名称；代练丸子没有「每个游戏的订单数」）

        返回 data 为扁平数组 [{game_id, game_name}]，顺序：热门在前，其余按首字母分组展开。
        """
        raw = self._post("/game/v3/all", {"channelType": CHANNEL_TYPE},
                         authorization=authorization, parse=False)
        if raw.get("code") != 10000:
            return response_dict(code=1, message=raw.get("message") or "获取游戏列表失败")

        data = raw.get("data") or {}
        games, seen = [], set()

        def _add(item):
            game_id = item.get("id")
            name = item.get("name")
            if game_id is None or not name or game_id in seen:
                return
            seen.add(game_id)
            games.append({"game_id": game_id, "game_name": name})

        for item in (data.get("hotGame") or []):
            _add(item)
        for group in (data.get("gridAllList") or []):
            for item in (group.get("detail") or []):
                _add(item)
        return response_dict(code=0, message="成功", data=games)

    def get_regions(self, authorization, game_id):
        """大区 / 服务器清单（每个大区取其「默认服」）

        返回 [{region_id, region_name, server_id, server_name}]（与发单页「游戏区服」一致）。
        """
        raw = self._post("/game/regionServer", {"gameId": game_id, "channelType": CHANNEL_TYPE},
                         authorization=authorization, parse=False)
        if raw.get("code") != 10000:
            return []
        data = raw.get("data") or {}
        servers_by_region = {}
        for group in (data.get("regionServer") or []):
            servers_by_region[group.get("regionId")] = group.get("children") or []

        regions = []
        for region in (data.get("region") or []):
            region_id = region.get("regionId")
            children = servers_by_region.get(region_id) or []
            if not children:
                continue
            default = next((c for c in children if c.get("serverName") == "默认服"), children[0])
            regions.append({
                "region_id": region_id,
                "region_name": region.get("regionName"),
                "server_id": default.get("serverId"),
                "server_name": default.get("serverName"),
            })
        return regions

    def get_leveling_types(self, authorization, game_id):
        """代练类型清单 [{leveling_type_id, leveling_type_name}]（如 排位 / 巅峰赛 / 哈夫币代刷）"""
        raw = self._post("/game/v3/levelingType",
                         {"gameId": str(game_id), "channelType": CHANNEL_TYPE},
                         authorization=authorization, parse=False)
        if raw.get("code") != 10000:
            return []
        data = raw.get("data") or {}
        return [{"leveling_type_id": t.get("id"), "leveling_type_name": t.get("name")}
                for t in (data.get("typeList") or [])]

    def get_level_sub_types(self, authorization, leveling_type_id):
        """某代练类型的「子类型字段」原始清单（上游 data.list）"""
        raw = self._post("/gameLevelSubTypes/v3/list",
                         {"gameLevelingTypeId": leveling_type_id, "channelType": CHANNEL_TYPE},
                         authorization=authorization, parse=False)
        if raw.get("code") != 10000:
            return []
        data = raw.get("data") or {}
        return data.get("list") or []

    def get_order_options(self, authorization, game_id, leveling_type_id=""):
        """发单可选项：大区 + 代练类型 +（指定代练类型时）其子类型字段

        子类型字段按「开发者可直接填」的形式给出：
            {sub_type_id, name, type, is_must, options:[{id,name}]（下拉类）, level_groups(段位类)}
        """
        result = {
            "game_id": game_id,
            "regions": self.get_regions(authorization, game_id),
            "leveling_types": self.get_leveling_types(authorization, game_id),
            "fields": [],
        }
        if not leveling_type_id:
            return response_dict(code=0, message="成功", data=result)

        for item in self.get_level_sub_types(authorization, leveling_type_id):
            field = {
                "sub_type_id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "is_must": item.get("isMust"),
                "use_type": item.get("useType"),
            }
            if item.get("type") in (1, 2):
                field["options"] = [{"id": o.get("id"), "name": o.get("name")}
                                    for o in (item.get("options") or [])]
            elif item.get("type") in (6, 7):
                field["levels"] = [{"name": name, "id": node.get("id")}
                                   for name, node in _iter_level_leaves(item.get("levelList"))]
            elif item.get("type") == 5:
                field["min_val"] = item.get("minVal")
                field["max_val"] = item.get("maxVal")
            result["fields"].append(field)
        return response_dict(code=0, message="成功", data=result)

    # ==================== 发单：内部解析 ====================

    def _find_game(self, authorization, game_id):
        """按 game_id 取上游游戏对象（含 name / icon；发单链路用）"""
        raw = self._post("/game/v3/all", {"channelType": CHANNEL_TYPE},
                         authorization=authorization, parse=False)
        data = raw.get("data") or {}
        groups = [data.get("hotGame") or []]
        groups += [group.get("detail") or [] for group in (data.get("gridAllList") or [])]
        for items in groups:
            for item in items:
                if str(item.get("id")) == str(game_id):
                    return item
        return None

    def _resolve_region(self, authorization, game_id, region_name):
        """按大区中文名解析区服；region_name 为空时取第一个大区"""
        regions = self.get_regions(authorization, game_id)
        if not regions:
            return None
        if not region_name:
            return regions[0]
        for region in regions:
            if region.get("region_name") == region_name:
                return region
        return None

    def _resolve_leveling_type(self, authorization, game_id, leveling_type_name):
        """按代练类型中文名解析；为空时取第一个"""
        types = self.get_leveling_types(authorization, game_id)
        if not types:
            return None
        if not leveling_type_name:
            return types[0]
        for item in types:
            if item.get("leveling_type_name") == leveling_type_name:
                return item
        return None

    # ==================== 发单：发布订单 ====================

    def publish_order(self, authorization, *, game_id, tasks, amount, hour,
                      security_deposit, efficiency_deposit,
                      region_name="", leveling_type_name="",
                      login_method=2, game_account="", game_password="", game_role="",
                      player_phone="", contact_phone="", contact_qq="",
                      title="", title_suffix="", subtitle="", explain="", requirement="",
                      take_password="", hero_name="", price_index=0, take_level=None,
                      perf_rate=0, take_count=0, use_tier=True):
        """发布订单（商家版）

        :param tasks: 子类型字段取值声明，形如
            [{'name': '起止段位', 'start': '青铜3段0星', 'end': '王者50星'}]（王者）
            [{'name': '哈夫币(万)', 'value': 100}, {'name': '保险箱', 'value': '2格'}]（三角洲）
        :param region_name: 大区中文名（如「安卓QQ」「手机QQ」），为空取该游戏第一个大区
        :param leveling_type_name: 代练类型中文名（如「排位」「哈夫币代刷」），为空取第一个
        :param login_method: 1=扫码上号 / 2=账密上号
        :param price_index: 报价档位下标（取自 slicePriceCal 返回的 categoryPriceList）
        :return: 统一响应字典，成功时 data = {'trade_no': ..., 'status': ...}
        """
        game = self._find_game(authorization, game_id)
        if not game:
            return response_dict(code=1, message=f"未知游戏（game_id={game_id}）")
        region = self._resolve_region(authorization, game_id, region_name)
        if not region:
            return response_dict(code=1, message=f"无法定位区服: {region_name or '(默认)'}")
        leveling = self._resolve_leveling_type(authorization, game_id, leveling_type_name)
        if not leveling:
            return response_dict(code=1, message=f"无法定位代练类型: {leveling_type_name or '(默认)'}")

        game_name, game_icon = game.get("name"), game.get("icon")
        leveling_type_id = leveling.get("leveling_type_id")
        leveling_type_full = leveling.get("leveling_type_name")

        # 1) 子类型字段 → multiTaskInfo
        sub_types = self.get_level_sub_types(authorization, leveling_type_id)
        by_name = {item.get("name"): item for item in sub_types}
        multi_task_info = []
        for spec in (tasks or []):
            item = by_name.get(spec.get("name"))
            if item is None:
                continue
            built = build_task_item(item, spec)
            if built:
                multi_task_info.append(built)
        # 必填字段校验（避免把不完整参数发给上游）
        for item in sub_types:
            if not item.get("isMust"):
                continue
            if not any(t.get("id") == item.get("id") for t in multi_task_info):
                return response_dict(code=1, message=f"缺少必填项: {item.get('name')}")

        # 2) 价格计算参数 → transPriceCal（响应即后续下发的规整参数）
        price_params = {
            "tempType": TEMP_TYPE, "orderType": ORDER_TYPE_TRAIN,
            "gameId": game_id, "gameName": game_name, "gameIcon": game_icon,
            "gameLevelingTypeId": leveling_type_id, "gameLevelingTypeName": leveling_type_full,
            "gameRegionId": region.get("region_id"), "gameRegionName": region.get("region_name"),
            "gameServerId": region.get("server_id"), "gameServerName": region.get("server_name"),
            "multiTaskInfo": multi_task_info, "heroName": hero_name,
        }
        trans_raw = self._post("/merchant/transPriceCal", price_params,
                               authorization=authorization, parse=False)
        if trans_raw.get("code") != 10000:
            return response_dict(code=1, message=trans_raw.get("message") or "价格计算失败")
        release = dict(trans_raw.get("data") or {})
        release.pop("common", None)
        release["orderType"] = ORDER_TYPE_TRAIN
        release["gameRegionServer"] = [game_id, region.get("region_id"), region.get("server_id")]
        release["merchantInvoiceEntry"] = 1

        # 3) 标题：调用方没给就按上游规则生成，并追加默认提示（如「私单勿接，指定单，接了扣除双金」）
        if not title:
            gen = self._post("/merchant/genTitle", dict(release),
                             authorization=authorization, parse=False)
            title = ((gen.get("data") or {}).get("title") or "").strip()
            if title_suffix.strip():
                title = f"{title} {title_suffix.strip()}"

        # 4) 档位价格 → merchantTranslateId / channelConfigType
        price_body = dict(release)
        price_body.update({"title": title, "orderType": ORDER_TYPE_TRAIN})
        price_path = ("/merchant/special/price"
                      if str(game_id) in ("107", "226") else "/merchant/slicePriceCal")
        price_raw = self._post(price_path, price_body, authorization=authorization, parse=False)
        price_list = ((price_raw.get("data") or {}).get("categoryPriceList") or [])

        # 5) 组装创建订单参数
        if not explain or not requirement:
            # 代练说明 / 要求留空时取上游默认文案（与网页端一致）
            oe = self._post("/game/order/explain",
                            {"gameId": game_id, "channelType": CHANNEL_TYPE},
                            authorization=authorization, parse=False)
            oe_data = oe.get("data") or {}
            explain = explain or oe_data.get("explain") or ""
            requirement = requirement or oe_data.get("requirement") or ""

        full_title = title
        if subtitle and subtitle.strip():
            full_title = f"{title} 备注：{subtitle.strip()}"

        body = dict(release)
        body.update({
            "title": full_title, "amount": str(amount), "hour": str(hour),
            "securityDeposit": str(security_deposit), "efficiencyDeposit": str(efficiency_deposit),
            "takePassword": take_password, "playerPhone": player_phone,
            "contactPhone": contact_phone, "contactQq": contact_qq,
            "requirement": requirement, "explain": explain,
            "type": 2, "time": "", "sourceAmount": "0", "cardCouponId": "", "operation": "2",
            "category": "1", "masterId": "", "orderSource": "1", "payType": 1,
            "channelConfigId": "0", "channelConfigType": "0", "platformProfit": "",
            "platformId": "", "storeType": 3, "orderType": ORDER_TYPE_TRAIN,
        })
        # 服务档位（决定 category：12=严选 / 11=悬赏）。use_tier=False 时不带档位，
        # category 保持默认 "1"（=标准，与 App 默认发单一致，低等级打手可接）。
        if price_list and use_tier:
            picked = price_list[price_index] if 0 <= price_index < len(price_list) else price_list[0]
            body["category"] = "0"
            body["merchantTranslateId"] = picked.get("merchantTranslateId")
            body["channelConfigType"] = picked.get("type")

        # 接单门槛（代练师等级等）：只在 take_level 非 None 时下发。
        # 不传 = 沿用平台默认（商家单默认「严选」，要求打手 Lv2+）；takeLevel=-1 表示不限。
        if take_level is not None:
            body["takeLevel"] = take_level
            body["perfRate"] = perf_rate or 0
            body["takeCount"] = take_count or 0

        if login_method == 2:
            body["gameAccount"] = game_account
            body["gamePassword"] = game_password
            body["gameRole"] = game_role
        else:
            body["gameAccount"] = "扫码上号"
            body["gamePassword"] = "扫码上号"
            body["gameRole"] = game_role or "扫码上号"

        # 下单接口用 /merchant/store（丸子 App 实际调用的接口：创建并支付/扣款）；
        # 不要用 /merchant/storeOrder —— 它只创建订单（待付款），App 里无人调用。
        store_raw = self._post("/order/action/merchant/store", body,
                               authorization=authorization, parse=False)
        if store_raw.get("code") != 10000:
            return response_dict(code=1, message=store_raw.get("message") or "发布订单失败")
        store_data = store_raw.get("data") or {}
        return response_dict(code=0, message=store_raw.get("message") or "发布成功", data={
            "trade_no": store_data.get("tradeNo"),
            "status": store_data.get("status"),
        })
