import os
import sys
import time
import requests
from datetime import datetime

# ---------- 引入 ddddocr 本地验证码识别器 ----------
_DDDDOCR_PATH = os.path.join(os.path.dirname(__file__), "..", "DdddocrRecognizer")
if _DDDDOCR_PATH not in sys.path:
    sys.path.insert(0, _DDDDOCR_PATH)
from home import DdddocrRecognizer

from .utils import (
    API_URL,
    get_mobile_headers,
    generate_device_id,
    get_public_data,
    parse_response,
    base64_to_image,
    response_dict,
)

"""
开发者您好,目前发布订单的接口还需要持续完善,目前只是手动定义了2种发单方式,一个是王者荣耀、一个是三角洲行动,后续还需要等我找到这些模板的值后会进行公布,目前没有时间
"""

_REQ_TIMEOUT = 15


class DaiLianWanZiService:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_mobile_headers())
        self.partner_device = generate_device_id()
        # 全局共享一个识别器实例（首次调用时延迟初始化）
        self._recognizer = None

    @property
    def recognizer(self):
        if self._recognizer is None:
            self._recognizer = DdddocrRecognizer(show_ad=False)
        return self._recognizer

    # -------- 发送验证码 --------
    def send_code(self, phone):
        code = self.get_captcha_code(phone)
        if code["code"] != 0:
            return code

        captcha_str = (code.get("data") or {}).get("code")
        if not captcha_str:
            return {"code": 1, "message": "未能获取到验证码"}

        json_data = get_public_data(self.partner_device, {
            "phoneNumber": phone,
            "captchaCode": captcha_str,
        })
        resp = self.session.post(
            f"{API_URL}/user/sms/sendForLogin",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 获取安全验证图片（本地 ddddocr 识别）--------
    def get_captcha_code(self, phone):
        json_data = get_public_data(self.partner_device, {"phoneNumber": phone})
        try:
            resp = self.session.post(
                f"{API_URL}/user/login/getCaptchaCode",
                json=json_data,
                timeout=_REQ_TIMEOUT,
            )
            data = resp.json()
        except Exception as e:
            return {"code": 1, "message": f"获取验证码接口异常: {e}"}

        if data.get("code") != 10000:
            return data

        image_base64 = (data.get("data") or {}).get("imageBase64")
        if not image_base64:
            return {"code": 1, "message": "验证码图片数据为空"}

        # 本地 base64 → bytes（无需网络请求）
        image_bytes = base64_to_image(image_base64)
        if not image_bytes:
            return {"code": 1, "message": "验证码图片解码失败"}

        # 本地 ddddocr 识别
        ocr_result = self.recognizer.ocr(image_bytes)
        if ocr_result["code"] != 0:
            return ocr_result

        code_text = ocr_result.get("data", "")
        data["data"]["code"] = code_text.lower()
        return response_dict(code=0, data=data["data"], is_return_response=False)

    # -------- 登录 --------
    def login(self, phone, code, code_type="VerificationCode"):
        payload = {"phoneNumber": phone, "captchaCode": None}

        if code_type == "VerificationCode":
            payload.update({"captcha": code, "userRole": ""})
            url = f"{API_URL}/user/login/bysms"
        elif code_type == "Password":
            payload.update({"password": code, "userRole": 0})
            url = f"{API_URL}/user/login/bypwd"
        else:
            return {"code": 1, "message": f"不支持的登录类型: {code_type}"}

        json_data = get_public_data(self.partner_device, payload)
        resp = self.session.post(url, json=json_data, timeout=_REQ_TIMEOUT)
        return parse_response(resp)

    # -------- 获取用户信息 --------
    def get_user_info(self, authorization):
        json_data = get_public_data(self.partner_device, authorization=authorization)
        resp = self.session.post(f"{API_URL}/mine/main", json=json_data, timeout=_REQ_TIMEOUT)
        return parse_response(resp)

    # -------- 上传个人头像 --------
    def upload_own_avatar(self, image, authorization):
        json_data = get_public_data(self.partner_device, {"avatarUrl": image}, authorization=authorization)
        resp = self.session.post(
            f"{API_URL}/user/profile/modifyMyImgByUrl",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 设置个性信息 --------
    def set_mysign(self, authorization, username, **kwargs):
        json_data = get_public_data(self.partner_device, {"username": username, **kwargs}, authorization=authorization)
        resp = self.session.post(
            f"{API_URL}/user/profile/modify",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 获取实名认证信息 --------
    def get_my_real_name_info(self, authorization):
        json_data = get_public_data(self.partner_device, {"sceneType": "sm"}, authorization=authorization)
        resp = self.session.post(
            f"{API_URL}/user/tax/signInfo",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 签到 --------
    def sign_in(self, authorization):
        json_data = get_public_data(self.partner_device, {
            "signType": 1,
            "signDate": datetime.today().strftime("%Y-%m-%d"),
        }, authorization=authorization)
        resp = self.session.post(
            f"{API_URL}/integralAccount/userSign/addSign",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 获取公共订单列表 --------
    def get_public_order_list(self, authorization, price_gt=10, price_lt=50,
                              page_no=1, page_size=30, game_id=1):
        json_data = get_public_data(self.partner_device, {
            "orderType": 1,
            "gameId": game_id,
            "sort": 0,
            "priceLt": price_lt,
            "priceGt": price_gt,
            "scoreGt": "",
            "scoreLt": "",
            "category": 1,
            "searchType": 2,
            "pageNo": page_no,
            "pageSize": page_size,
            "excludeTradeNoList": [],
        }, authorization=authorization)
        resp = self.session.post(f"{API_URL}/order/hall/list", json=json_data, timeout=_REQ_TIMEOUT)
        return parse_response(resp)

    # -------- 搜索订单 --------
    def search_order(self, authorization, keyword, page_no=1, page_size=10):
        json_data = get_public_data(self.partner_device, {
            "orderType": 1,
            "sort": 0,
            "searchType": 2,
            "keyword": keyword,
            "pageNo": page_no,
            "pageSize": page_size,
        }, authorization=authorization)
        resp = self.session.post(
            f"{API_URL}/order/hall/searchList",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 获取订单详情 --------
    def get_order_detail(self, authorization, order_id):
        json_data = get_public_data(self.partner_device, {"tradeNo": order_id}, authorization=authorization)
        resp = self.session.post(
            f"{API_URL}/order/hall/detail",
            json=json_data,
            timeout=_REQ_TIMEOUT,
        )
        return parse_response(resp)

    # -------- 发布订单 --------
    def publish_order(self, authorization, title, amount, hour,
                      securityDeposit, efficiencyDeposit,
                      playerPhone="3837190115",
                      contactPhone="3837190115",
                      gameRegionName="安卓QQ",
                      heroNumber="",
                      requirement="代练要求",
                      explain="代练说明",
                      gameAccount="扫码上号",
                      gamePassword="扫码上号",
                      contactQq="扫码上号",
                      gameRole="扫码上号",
                      gameId=1,
                      gameServerId=122,
                      gameRegionId=2,
                      gameIcon="https://files.llwanzi.com/zympYphpKVhaHN1685523686230531.png",
                      gameName="王者",
                      gameLevelingTypeName="排位",
                      **kwargs):
        """
        发布订单

        Args:
            authorization: 授权信息
            title: 订单标题
            amount: 订单金额
            hour: 订单时长
            securityDeposit: 安全保证金
            efficiencyDeposit: 效率保证金
            playerPhone: 号主手机号
            contactPhone: 发单方联系方式
            gameRegionName: 游戏区域(安卓QQ/安卓微信/苹果QQ/苹果微信)
            heroNumber: 英雄数量
            requirement: 代练要求
            explain: 订单说明
            gameAccount: 游戏账号
            gamePassword: 游戏密码
            contactQq: 其他联系方式
            gameRole: 游戏角色
            gameId: 游戏ID
            gameServerId: 游戏服务器ID
            gameRegionId: 游戏区域ID
            gameIcon: 游戏图标URL
            gameName: 游戏名称
            gameLevelingTypeName: 代练类型
        """
        try:
            json_data = get_public_data(self.partner_device, {
                "hasTrans": 1,
                "gameId": gameId,
                "gameServerId": gameServerId,
                "gameServerName": "默认服",
                "gameName": gameName,
                "gameIcon": gameIcon,
                "gameLevelingTypeId": 1,
                "gameLevelingTypeName": gameLevelingTypeName,
                "gameRegionId": gameRegionId,
                "gameRegionName": gameRegionName,
                "tempType": 6,
                "heroName": "",
                "heroNumber": heroNumber,
                "inscriptionNumber": "",
                "currentLevel": "",
                "targetLevel": "",
                "multiTaskInfo": [],
                "orderType": 1,
                "gameRegionServer": [gameId, gameRegionId, gameServerId],
                "merchantInvoiceEntry": 1,
                "title": title,
                "amount": amount,
                "hour": hour,
                "securityDeposit": securityDeposit,
                "efficiencyDeposit": efficiencyDeposit,
                "takePassword": "",
                "playerPhone": playerPhone,
                "contactPhone": contactPhone,
                "contactQq": contactQq,
                "requirement": requirement,
                "explain": explain,
                "type": 2,
                "time": "",
                "sourceAmount": "0",
                "cardCouponId": "",
                "operation": "2",
                "category": "0",
                "masterId": "",
                "orderSource": "1",
                "payType": 1,
                "channelConfigId": "0",
                "channelConfigType": "0",
                "platformProfit": "",
                "platformId": "",
                "storeType": 3,
                "gameAccount": gameAccount,
                "gamePassword": gamePassword,
                "gameRole": gameRole,
                "insureName": "无",
            }, authorization=authorization)

            json_data["common"]["timestamp"] = str(int(time.time()))

            region_map = {
                "苹果微信": [1, 3, 523],
                "苹果WX":   [1, 3, 523],
                "安卓微信": [1, 4, 639],
                "安卓WX":   [1, 4, 639],
                "苹果QQ":   [1, 1, 1],
                "安卓QQ":   [1, 2, 122],
            }
            mapped = region_map.get(gameRegionName)
            if mapped:
                json_data["gameRegionServer"] = mapped
                json_data["gameRegionName"] = gameRegionName.replace("WX", "微信")
                json_data["gameServerId"] = mapped[-1]

            resp = self.session.post(
                f"{API_URL}/order/action/merchant/store",
                json=json_data,
                timeout=_REQ_TIMEOUT,
            )
            return parse_response(resp)
        except Exception as e:
            return {"code": 1, "message": f"发布订单异常: {e}"}

    # -------- 取消订单 --------
    def cancel_order(self, orderId, authorization=None):
        try:
            json_data = get_public_data(self.partner_device, {"tradeNo": orderId}, authorization=authorization)
            resp = self.session.post(
                f"{API_URL}/order/action/cancel",
                json=json_data,
                timeout=_REQ_TIMEOUT,
            )
            return parse_response(resp)
        except Exception as e:
            return {"code": 1, "message": f"取消订单异常: {e}"}

    # -------- 获取我的余额 --------
    def get_my_balance(self, authorization=None):
        try:
            json_data = get_public_data(self.partner_device, {}, authorization=authorization)
            resp = self.session.post(
                f"{API_URL}/user/balance",
                json=json_data,
                timeout=_REQ_TIMEOUT,
            )
            return parse_response(resp)
        except Exception as e:
            return {"code": 1, "message": f"获取我的余额异常: {e}"}


if __name__ == "__main__":
    dailianwanzi_service = DaiLianWanZiService()
    phone = "18171759943"
    # a = dailianwanzi_service.get_captcha_code(phone)
    # print(dailianwanzi_service.send_code(phone))
    account_token = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    print(dailianwanzi_service.get_my_balance(authorization=account_token))
