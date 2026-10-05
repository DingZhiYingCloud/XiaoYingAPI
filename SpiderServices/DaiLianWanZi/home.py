import os
import sys
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
