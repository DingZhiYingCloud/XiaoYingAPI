"""Bing IndexNow URL 提交服务封装

本模块封装了向 IndexNow API 提交 URL 更新的逻辑：
- 生成 API Key
- 提交单个/批量 URL 到 IndexNow
"""
import uuid
import requests

# IndexNow API 基础地址
INDEXNOW_API = "https://api.indexnow.org/IndexNow"
# 请求超时时间（秒）
TIMEOUT = 15


def generate_key():
    """生成 IndexNow API Key（UUID 格式）

    :return: 32 位小写十六进制字符串（不含连字符）
    """
    return uuid.uuid4().hex


def submit_urls(host, key, url_list, key_location=None):
    """提交 URL 列表到 IndexNow

    :param host: 域名, 如 "www.example.com"
    :param key: API Key
    :param url_list: URL 列表, 如 ["https://www.example.com/page1", "https://www.example.com/page2"]
    :param key_location: Key 文件位置（可选）, 默认自动拼接为 https://{host}/{key}.txt
    :return: tuple[bool, Any]  (是否成功, 成功时为 dict{http_code, response_text, result}, 失败时为错误信息)
    """
    if key_location is None:
        key_location = f"https://{host}/{key}.txt"

    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": url_list,
    }

    try:
        resp = requests.post(
            INDEXNOW_API,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=TIMEOUT,
        )
        # IndexNow 返回的 HTTP 状态码代表不同结果
        status_code = resp.status_code
        response_text = resp.text.strip()

        # 成功状态码（200=已处理, 202=已接受排队处理）
        if status_code in (200, 202):
            return True, {
                "http_code": status_code,
                "result": "提交成功" if status_code == 200 else "必应已接收成功,但是无法确认是否已处理,请检测参数或者Key是否正确,一般200状态码才算成功",
            }

        # 各种错误状态码
        error_map = {
            400: "请求格式错误 (Bad Request)",
            403: "Key 验证失败 (Forbidden)，请检查 key 和 keyLocation 是否有效",
            422: "URL 不属于该域名或 Key 格式不匹配 (Unprocessable Entity)",
            429: "请求过于频繁 (Too Many Requests)",
        }
        error_msg = error_map.get(status_code, f"未知错误 (HTTP {status_code})")
        return True, {
            "http_code": status_code,
            "result": error_msg,
            "response_text": response_text,
        }

    except requests.Timeout:
        return False, "请求 IndexNow API 超时"
    except requests.RequestException as e:
        return False, f"请求 IndexNow API 失败: {e}"
    except Exception as e:
        return False, f"提交失败: {e}"
