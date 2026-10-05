"""
代练丸子爬虫辅助工具模块

提供统一的响应处理、请求头生成、设备ID生成、公共参数构建、
验证码图片处理、AI流式响应解析等功能。

本模块不依赖任何业务逻辑，可被 home.py 及其他模块复用。
"""

import json
import time
import random
import base64
import requests


# ==================== 常量 ====================

API_URL = "https://m.llwanzi.com/api"
"""代练丸子 API 基础地址"""

MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Redmi K70) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; OnePlus 11) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


# ==================== 工具函数 ====================


def get_mobile_headers() -> dict:
    """返回包含随机移动端 User-Agent 及 JSON Content-Type 的请求头"""
    return {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "user-agent": random.choice(MOBILE_UAS),
    }


def generate_device_id() -> str:
    """生成20位纯数字的随机 Device ID"""
    return "".join([str(random.randint(0, 9)) for _ in range(20)])


def get_public_data(
    partner_device: str,
    data_params: dict = None,
    authorization: str = None,
) -> dict:
    """
    构建代练丸子 API 请求的公共参数

    Args:
        partner_device: 设备 ID（由 generate_device_id 生成）
        data_params: 业务请求参数，可选
        authorization: 认证 Token，可选

    Returns:
        包含 common 公共参数的完整请求字典
    """
    common = {
        "partnerChannel": "m.llwanzi.com",
        "partner": "h5",
        "partnerVersion": "4.0.0-4.9.30",
        "partnerDevice": partner_device,
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


def response_dict(
    code: int = 0,
    message: str = "",
    data: dict | list = None,
    is_return_response: bool = True,
) -> dict:
    """统一的响应字典返回"""
    return {"code": code, "message": message, "data": data}


def parse_response(response: requests.Response) -> dict:
    """
    统一解析代练丸子 API 的 HTTP 响应

    Args:
        response: requests.Response 对象

    Returns:
        统一格式的响应字典：{"code": int, "message": str, "data": ...}
    """
    try:
        resp_json = response.json()
        if resp_json.get("code") == 10000:
            return response_dict(code=0, message="Success", data=resp_json, is_return_response=False)
        else:
            return response_dict(code=1, message=resp_json.get("message", "未知错误"), is_return_response=False)
    except requests.exceptions.JSONDecodeError as j:
        return response_dict(code=1, message=f"目标端返回了错误的格式: {j}", is_return_response=False)
    except Exception as e:
        return response_dict(code=1, message=f"未知错误: {e}", is_return_response=False)


def parse_ai_stream(response: requests.Response) -> dict:
    """
    解析 AI 流式响应（SSE 格式），提取完整回复文本

    Args:
        response: requests.Response 对象（stream=True）

    Returns:
        统一格式的响应字典，成功时 data 为完整文本
    """
    text = ""
    try:
        for item in response.iter_lines():
            if item:
                item = item.decode("utf-8")
                item = item.replace("data: ", "")
                item = json.loads(item)
                if item.get("type") == "stop":
                    break
                elif item.get("type") == "text":
                    text += item.get("msg", "")
    except json.JSONDecodeError as e:
        print("JSON提取错误:::", e)
        return response_dict(code=1, message=f"JSON提取错误: {e}", is_return_response=False)
    except Exception as e:
        print("错误:::", e)
        return response_dict(code=1, message=f"提取错误: {e}", is_return_response=False)

    return response_dict(code=0, message="成功", data=text, is_return_response=False)


def base64_to_image(base64_str: str) -> bytes:
    """
    将 data:image/xxx;base64,... 格式的字符串解码为图片字节码

    Args:
        base64_str: 以 data:image/xxx;base64, 开头的 base64 编码字符串

    Returns:
        解码后的图片字节码；失败时返回 b""

    Raises:
        ValueError: 输入字符串格式不正确时抛出
    """
    try:
        if not base64_str:
            raise ValueError("base64字符串不能为空")

        prefixes = [
            "data:image/jpg;base64,",
            "data:image/jpeg;base64,",
            "data:image/png;base64,",
            "data:image/gif;base64,",
            "data:image/webp;base64,",
        ]

        content_start = -1
        for prefix in prefixes:
            if base64_str.startswith(prefix):
                content_start = len(prefix)
                break

        if content_start == -1:
            raise ValueError(
                "base64字符串格式不正确，必须以前缀开头:\n" + "\n".join(prefixes)
            )

        base64_content = base64_str[content_start:]

        # 补全 Base64 填充字符
        missing_padding = len(base64_content) % 4
        if missing_padding:
            base64_content += "=" * (4 - missing_padding)

        return base64.b64decode(base64_content)

    except (ValueError, Exception) as e:
        print(f"base64解码失败: {e}")
        return b""


# ==================== 凭据解析与校验（供 API 层 / 后台「账号管理」调用） ====================


def parse_credential(credential: str) -> dict:
    """解析平台托管凭据 → dict

    约定存「登录接口返回的 JSON」（含 accessToken / uuid / id 等），也兼容
    直接存纯令牌字符串（如 "Bearer xxx" 或裸 token）。

    :return: 解析后的 dict；无法识别时返回 {}
    """
    text = (credential or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"accessToken": text}
    return data if isinstance(data, dict) else {"accessToken": text}


def credential_authorization(credential: str) -> str:
    """从托管凭据中取可用于请求的 authorization 令牌

    优先 accessToken（登录接口字段名），其次 token；都没有则返回空串。
    返回的是原始令牌（不带 "Bearer " 前缀），由 get_public_data 按需补前缀。
    """
    data = parse_credential(credential)
    return str(data.get("accessToken") or data.get("token") or "").strip()


def check_credential(credential: str):
    """校验代练丸子登录凭据是否有效（调「我的信息」/mine/main）

    :param credential: 账号管理里托管的登录凭据（JSON 或纯令牌）
    :return: (True, 说明) 表示凭据有效；(False, 原因) 表示已失效 / 无法校验
    """
    token = credential_authorization(credential)
    if not token:
        return False, "凭据缺少 accessToken"

    try:
        json_data = get_public_data(generate_device_id(), {}, authorization=token)
        resp = requests.post(
            f"{API_URL}/mine/main",
            json=json_data,
            headers=get_mobile_headers(),
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        return False, f"校验请求异常：{e}"

    result = parse_response(resp)
    if result["code"] == 0:
        # parse_response 成功时 data 为上游完整响应对象，用户信息在其 data 字段下
        info = (result.get("data") or {}).get("data") or {}
        return True, f"有效（{info.get('username') or info.get('uuid') or '已登录'}）"
    return False, result.get("message") or "凭据已失效"
