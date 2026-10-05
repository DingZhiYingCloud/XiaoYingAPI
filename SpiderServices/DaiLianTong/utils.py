# 代练通 - 辅助工具模块（常量配置 + 工具函数）

import base64
import hashlib
import random
import json
import os
import time
import requests

from dotenv import load_dotenv


# ==================== 常量配置 ====================

# 移动端 User-Agent 列表
MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
]

API_URL = "https://server.dailiantong.com.cn/API/AppService.ashx"
# 平台签名密钥从 .env 读取（DAILIAN_SIGN_KEY），禁止硬编码进代码库
load_dotenv()
SIGN_KEY = os.getenv("DAILIAN_SIGN_KEY", "") or ""


# ==================== 辅助函数 ====================

def get_mobile_headers() -> dict:
    """返回一个包含随机移动端 User-Agent 的 HTTP 头字典"""
    return {
        'Accept': '*/*',
        'Content-Type': 'application/x-www-form-urlencoded',
        'user-agent': random.choice(MOBILE_UAS),
    }


def md5_encrypt(data: str) -> str:
    """
    对输入字符串进行 MD5 加密，返回小写的 32 位十六进制结果
    :param data: 待加密的字符串
    :return: MD5 十六进制摘要
    """
    md5_obj = hashlib.md5()
    if isinstance(data, str):
        data = data.encode('utf-8')
    md5_obj.update(data)
    return md5_obj.hexdigest()


def base64_encrypt(content, encoding='utf-8'):
    """
    对字符串做 Base64 编码（发单 Actors 字段要求）
    :param content: 待编码字符串
    :return: Base64 字符串
    """
    if isinstance(content, str):
        content = content.encode(encoding)
    return base64.b64encode(content).decode(encoding)


def response_dict(code: int = 0, message: str = "", data: dict | list = None, is_return_response: bool = True):
    """统一的响应字典/JSON 返回"""
    return {"code": code, "message": message, "data": data}


def get_dict_values(input_dict):
    """
    从字典中提取所有值并返回一个列表
    :param input_dict: 输入的字典
    :return: list — 包含字典中所有值的列表
    """
    try:
        if not isinstance(input_dict, dict):
            raise TypeError("输入必须是一个字典")
        return list(input_dict.values())
    except Exception as e:
        return {"code": 1, "message": f"获取字典值异常: {e}"}


def sign_params(params, sign_key, e="LevelOrderList", token=""):
    """
    对参数字典进行签名（SignKey + action + 参数值拼接 + token → MD5）
    :param params: 参数字典
    :param sign_key: 签名密钥
    :param e: 动作名称
    :param token: 登录令牌
    :return: MD5 签名字符串
    """
    try:
        input_str = "".join(sign_key + e + "".join(get_dict_values(params)) + token)
        md5_obj = hashlib.md5()
        if isinstance(input_str, str):
            input_str = input_str.encode('utf-8')
        md5_obj.update(input_str)
        return md5_obj.hexdigest()
    except Exception as e:
        return {"code": 1, "message": f"MD5加密异常: {e}"}


def get_public_data(data_params, action, sign_key, token=""):
    """
    获取公共请求参数（添加时间戳/版本信息，并生成签名）
    :param data_params: 业务参数字典
    :param action: 接口动作名称
    :param sign_key: 签名密钥
    :param token: 登录令牌
    :return: (data, params) — (完整请求数据, URL 参数)
    """
    data = {
        'TimeStamp': str(int(time.time())),
        'Ver': '1.0',
        'AppVer': '5.2.4',
        'AppOS': 'WebApp IOS',
        'AppID': 'webapp',
    }
    data_params.update(data)
    data_params["Sign"] = sign_params(data_params, sign_key, e=action, token=token)
    return data_params, {"Action": action}


def parse_response(response):
    """
    统一解析 HTTP 响应，转换为统一格式字典
    :param response: requests.Response 对象
    :return: 统一格式的响应字典
    """
    try:
        response = response.json()
        result = response.get("Result")
        # 兼容 Result 为字符串 "1"/"0" 或整数 1/0 的情况
        if result is not None and str(result) == "1":
            return response_dict(code=0, message=response.get("Err", "成功"), data=response)
        elif result is not None:
            return response_dict(code=1, message=response.get("Err", "请求失败"), data=response)
        elif response.get("UID"):
            return response_dict(code=0, message="成功", data=response)
        else:
            return response_dict(code=1, message=response.get("Err", "未知错误"))
    except requests.exceptions.JSONDecodeError:
        return response_dict(code=1, message="请求太快了!忙不过来")
    except Exception as e:
        return response_dict(code=1, message=f"解析响应异常: {e}")


# ==================== 凭据校验（供后台「账号管理」调用） ====================

def check_credential(credential: str):
    """校验代练通登录凭据是否有效（调 UserInfoList）

    credential 为平台账号的「登录凭据」原文，约定 JSON：
        {"user_id": "24479174", "token": "..."}

    :return: (True, 说明) 表示凭据有效；(False, 原因) 表示已失效 / 无法校验
    """
    try:
        data = json.loads(credential or '')
        user_id = str(data.get('user_id') or '').strip()
        token = str(data.get('token') or '').strip()
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False, '凭据格式错误：应为 JSON {"user_id": "...", "token": "..."}'
    if not user_id or not token:
        return False, '凭据缺少 user_id 或 token'
    if not SIGN_KEY:
        return False, 'DAILIAN_SIGN_KEY 未配置，无法校验'

    try:
        params, query = get_public_data({'UserID': user_id}, 'UserInfoList',
                                        sign_key=SIGN_KEY, token=token)
        response = requests.post(API_URL, params=query, data=params,
                                 headers=get_mobile_headers(), timeout=15)
    except requests.exceptions.RequestException as e:
        return False, f'校验请求异常：{e}'

    result = parse_response(response)
    if result['code'] == 0:
        info = result.get('data') if isinstance(result.get('data'), dict) else {}
        return True, f"有效（{info.get('NickName') or user_id}）"
    return False, result.get('message') or '凭据已失效'
