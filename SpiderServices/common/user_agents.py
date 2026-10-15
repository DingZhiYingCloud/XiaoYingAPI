"""SpiderServices 通用请求头 / 统一响应工具（全站唯一实现）

原先 `SpiderServices/ProxyIp/utils.py` 与 `SpiderServices/ImageHosting/utils.py`
各有一份逐字相同的 `DESKTOP_UAS` / `get_desktop_headers()` / `response_dict()`
（两份互为副本），此处收敛为唯一实现；上述两个模块改为从本模块导入并继续对外透出同名对象，
各线路子模块对这两个 utils 的导入与调用点保持不变。
"""

import random


# ==================== 常量 ====================

# 桌面端 User-Agent 列表
DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


# ==================== 工具函数 ====================


def get_desktop_headers() -> dict:
    """返回包含随机桌面端 User-Agent 的 HTTP 头字典"""
    return {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": random.choice(DESKTOP_UAS),
    }


def response_dict(code: int = 0, message: str = "", data: dict | list = None) -> dict:
    """统一的响应字典返回"""
    return {"code": code, "message": message, "data": data}
